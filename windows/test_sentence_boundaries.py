"""Common boundary contract plus Windows adapter/desktop acceptance.

--contract runs the pure, shared semantics without importing Qt/WinRT/models.
"""
import json
from pathlib import Path
import sys
import unittest

from context_boundary import Line, analyze, editor_lines, complete_capture

CORPUS = Path(__file__).resolve().parent.parent / 'Tests' / 'Fixtures' / 'sentence-boundaries.json'


def marked(text):
    if '⟦' not in text: return text,None
    a=text.index('⟦'); b=text.index('⟧')
    return text[:a]+text[a+1:b]+text[b+1:],(a,b-1)


def run_contract():
    corpus=json.loads(CORPUS.read_text(encoding='utf-8'))
    failures=[]; count=0
    def check(sample,text=None,scale=1,dx=0,dy=0,reverse=False):
        nonlocal count
        count+=1
        name=f"{sample['id']} [{sample['category']}, reflow={text is not None}, scale={scale}, shift={dx},{dy}, reverse={reverse}]"
        try:
            if sample['mode']=='editor':
                original,hit=marked(text if text is not None else sample['input'])
                lines=editor_lines(original,*hit); capture=None
            else:
                lines=[Line((parts:=marked(row['text']))[0],(row['x']*scale+dx,row['y']*scale+dy,row['width']*scale,row['height']*scale),parts[1]) for row in sample['lines']]
                if reverse: lines.reverse()
                raw=sample.get('capture')
                capture=(raw[0]*scale+dx,raw[1]*scale+dy,raw[2]*scale,raw[3]*scale) if raw else None
            actual=analyze(lines,source=sample['mode'],code=sample['language'],capture=capture)
            expected,hit=marked(sample['expected']); query=sample.get('query',expected[slice(*hit)])
            # This contract flag includes independent word lookup, as on Mac.
            # The Windows card's automatic_context excludes standalone words;
            # adapter tests separately require no redundant bilingual source.
            automatic=actual.extent=='complete' and actual.structure in ('sentence','list') and not sample['language'].startswith('zh')
            got=(actual.text,actual.selection,actual.text[slice(*actual.selection)],actual.structure,actual.extent,automatic)
            wanted=(expected,hit,query,sample['structure'],sample['extent'],sample['automatic'])
            if got!=wanted: failures.append(name+f': actual={got!r}, expected={wanted!r}')
            if not all(0<=s.start<s.end<=len(actual.text) for s in actual.sources): failures.append(name+': invalid source spans')
        except Exception as error: failures.append(name+': '+repr(error))
    for sample in corpus['cases']:
        check(sample)
        if sample['mode']=='ocr':
            for scale in (1.5,2): check(sample,scale=scale,dx=-600,dy=240,reverse=True)
        if sample.get('reflow'):
            words=sample['expected'].split(' ')
            for width in (3,5,7):
                check(sample,text=''.join(('\n' if i and i%width==0 else ' ' if i else '')+word for i,word in enumerate(words)))
    report={'baseCases':len(corpus['cases']),'checks':count,'passed':count-len(failures),'failures':failures,'categories':sorted({x['category'] for x in corpus['cases']})}
    return report


class SentenceBoundaryContractTests(unittest.TestCase):
    def test_shared_contract(self):
        report=run_contract()
        self.assertEqual(report['failures'],[], '\n'.join(report['failures']))
        self.assertGreater(report['checks'],report['baseCases'])


@unittest.skipUnless(sys.platform == 'win32', 'Windows application adapters and native libraries')
class WindowsBoundaryTests(unittest.TestCase):
    def test_editor_and_ocr_adapters(self):
        from PySide6.QtCore import QPointF, QRectF
        from reader import sentence_at, passage_from_lines, Word
        corpus=json.loads(CORPUS.read_text(encoding='utf-8'))
        for sample in corpus['cases']:
            with self.subTest(case=sample['id']):
                expected,selection=marked(sample['expected'])
                if sample['mode']=='editor':
                    source,hit=marked(sample['input'])
                    passage=sentence_at(source,*hit,source_code=sample['language'])
                else:
                    lines=[]; point=None
                    for row in sample['lines']:
                        text,hit=marked(row['text'])
                        rect=QRectF(row['x'],row['y'],row['width'],row['height'])
                        edges=tuple(rect.left()+i*rect.width()/len(text) for i in range(len(text)+1))
                        lines.append([Word(text,rect,edges)])
                        if hit: point=QPointF((edges[hit[0]]+edges[hit[1]])/2,rect.center().y())
                    bounds=sample.get('capture')
                    passage=passage_from_lines(lines,point,sample['language'],is_crop=bool(bounds),capture_bounds=bounds)
                self.assertEqual((passage.text,passage.word,passage.structure,passage.extent),
                                 (expected,sample.get('query',expected[slice(*selection)]),sample['structure'],sample['extent']))
                self.assertEqual(passage.selection,selection)
                self.assertEqual(passage.local_context[passage.local_context_offset:passage.local_context_offset+len(passage.word)],passage.word)

    def test_partial_provider_and_card_scope(self):
        from unittest.mock import patch
        from PySide6.QtCore import QPoint, QUrl
        from reader import Passage
        from card_policy import automatic_context
        from lookup import explain
        from popup import Card
        from translation import translate_lookup
        for extent in ('missingStart','missingEnd','missingBoth','uncertain'):
            passage=Passage('The API returns data and', (4,7),source_code='en',extent=extent)
            with self.subTest(extent=extent), patch('lookup.sentence_translation',side_effect=AssertionError('partial sentence MT')):
                result,excerpt,language,pos=explain(passage)
                self.assertIn('应用程序',result[1]); self.assertEqual(result[2],''); self.assertIsNone(excerpt)
                self.assertFalse(automatic_context(passage,confirmed=True))
            with patch('translation.translate_leg',return_value=Passage('接口')) as mt:
                result,excerpt=translate_lookup(passage)
                self.assertIsNone(excerpt); self.assertEqual(result[2],'')
                self.assertEqual([call.args[0].text for call in mt.call_args_list],['API'])
            card=Card(); requests=[]; card.context_requested.connect(requests.append)
            try:
                card.show_result(passage,'术语参考','应用程序编程接口','',QPoint(10,10),language='英语')
                self.assertIn('原文片段',card.text.toPlainText()); self.assertIn('翻译可见片段',card.text.toPlainText())
                self.assertEqual(card.listen.read.text(),'朗读可见片段')
                card.open_reference(QUrl('waxcard://translate')); request,part=requests[-1]
                self.assertEqual((part.text,part.extent),(passage.text,extent))
                card.open_reference(QUrl('waxcard://translate'))
                self.assertFalse(card.finish_context(request,'stale output'))
                self.assertNotIn('stale output',card.text.toPlainText())
            finally: card.close()
        standalone=Passage('sensor',(0,6),source_code='en')
        self.assertFalse(automatic_context(standalone))
        card=Card()
        try:
            card.show_result(standalone,'单词参考','传感器','',QPoint(10,10))
            self.assertNotIn('原文片段',card.text.toPlainText())
        finally: card.close()

    def test_bounded_retry_cancel_and_changed_anchor(self):
        import asyncio
        from concurrent.futures import CancelledError
        from unittest.mock import patch, AsyncMock
        from app import analyze as analyze_lookup
        from reader import Passage
        first=Passage('the sensor and',(4,10),extent='missingBoth')
        full=Passage('The sensor is ready.',(4,10))
        self.assertIs(complete_capture(first,lambda:full),full)
        self.assertIs(complete_capture(first,lambda:Passage('Another term.',(8,12))),first)
        def fail(): raise ValueError('capture unavailable')
        self.assertIs(complete_capture(first,fail),first)
        with self.assertRaises(CancelledError): complete_capture(first,lambda:full,cancelled=lambda:True)
        explanation=(('单词参考','传感器',''),None,'英语','')
        with patch('app.recognize',new=AsyncMock(return_value=first)), patch('app.explain') as explain:
            deferred=analyze_lookup(object(),object(),None,is_crop=True,defer_expansion=True)
            self.assertIsNone(deferred[1]); explain.assert_not_called()
        with patch('app.recognize',new=AsyncMock(return_value=full)), patch('app.explain',return_value=explanation):
            self.assertIs(analyze_lookup(object(),object(),None,is_crop=True,original=first)[0],full)
        with patch('app.recognize',new=AsyncMock(side_effect=ValueError('capture unavailable'))), patch('app.explain',return_value=explanation):
            self.assertIs(analyze_lookup(object(),object(),None,is_crop=True,original=first)[0],first)
        cancelled=[False]
        async def late(*args,**kwargs): cancelled[0]=True; return full
        with patch('app.recognize',new=late), patch('app.explain') as explain:
            with self.assertRaises(CancelledError):
                analyze_lookup(object(),object(),None,is_crop=True,original=first,cancelled=lambda:cancelled[0])
            explain.assert_not_called()

    def test_saved_fragment_migration_and_review(self):
        from tempfile import TemporaryDirectory
        from contextlib import closing
        import sqlite3
        from notebook import Notebook, ENTRIES_SCHEMA
        from reader import Passage
        from library import Library
        from theme import result_html
        with TemporaryDirectory() as temp:
            path=Path(temp)/'old.sqlite3'
            with closing(sqlite3.connect(path)) as db, db:
                db.execute(ENTRIES_SCHEMA)
                db.execute("INSERT INTO entries VALUES(1,'sensor','The sensor is ready.',4,'词典','传感器','完整译文',12345,2,'en')")
            book=Notebook(path)
            old=book.entries()[0]
            self.assertEqual((old['extent'],old['source_kind'],old['due'],old['streak']),('complete','',12345,2))
            passage=Passage('The sensor and',(4,10),source_code='en',extent='missingEnd')
            book.save(passage,('单词参考','传感器','显式片段译文'))
            row=next(row for row in book.entries() if row['context']==passage.text)
            book.review(row['id'],True,now=50000)
            schedule=next(r for r in book.entries() if r['id']==row['id'])
            book.save(passage,('单词参考','传感器更新','显式片段译文'))
            row=next(r for r in book.entries() if r['id']==row['id'])
            self.assertEqual((row['extent'],row['due'],row['streak']),('missingEnd',schedule['due'],schedule['streak']))
            self.assertIn('原文片段',result_html(passage,row['gloss'],row['translation'],'参考'))
            from speech import SpeechPlayer
            library=Library(book,SpeechPlayer())
            try:
                library.refresh()
                index=next(i for i,r in enumerate(library.rows) if r['id']==row['id'])
                library.list.setCurrentRow(index)
                self.assertIn('原文片段',library.detail.toPlainText())
                self.assertEqual(library.listen.read.text(),'朗读可见片段')
                library.testing=True; library.revealed=False; library.display()
                self.assertIn('原文片段',library.detail.toPlainText())
                library.revealed=True; library.display()
                self.assertIn('显式片段译文',library.detail.toPlainText())
            finally: library.close()
            code=Passage('return sensor;', (7,13),source_code='en',structure='code')
            book.save(code,('词典','传感器',''))
            row=next(r for r in book.entries() if r['context']==code.text)
            self.assertEqual((row['structure'],row['source_kind']),('fragment','code'))
            # The old-column reader can still consume every record.
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(len(db.execute('SELECT word,context,position,language,structure FROM entries').fetchall()),3)

    def test_real_multiline_native_and_offline_ocr(self):
        import asyncio
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtGui import QFont, QImage, QPainter
        from reader import recognize, read_from_pack
        rows=['The inspection team checked every panel and',
              'confirmed that the sensor was not disconnected',
              'before the machine was restarted.']
        image=QImage(760,190,QImage.Format_RGB32); image.fill(Qt.white)
        with QPainter(image) as painter:
            font=QFont('Segoe UI'); font.setPixelSize(22); painter.setFont(font)
            for i,row in enumerate(rows): painter.drawText(40,60+i*30,row)
            metrics=painter.fontMetrics()
            hit=QPointF(40+metrics.horizontalAdvance('confirmed that the sen'),90-metrics.capHeight()/2)
        for name,read in [('native',lambda:asyncio.run(recognize(image,hit,'en',is_crop=True))),
                          ('offline',lambda:read_from_pack(image,hit,'en',is_crop=True)[0])]:
            with self.subTest(engine=name):
                passage=read()
                self.assertEqual(passage.word,'sensor')
                self.assertEqual(passage.text,' '.join(rows))
                self.assertEqual(passage.extent,'complete')

    def test_desktop_bounded_context_expansion(self):
        import time
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from PySide6.QtCore import QPoint, QProcess, Qt
        from PySide6.QtGui import QFont, QPainter
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QWidget
        from app import Window
        from notebook import Notebook
        app=QApplication.instance()
        if app.platformName() != 'windows': self.skipTest('isolated desktop required')
        rows=['The inspection team opened the machine and',
              'reviewed every connection around the main panel',
              'before checking the pressure and the temperature',
              'while the sensor remained connected to the',
              'controller and the backup power supply so',
              'the recorded measurements could be compared with',
              'the previous results after the inspection ended.']
        class Sample(QWidget):
            def paintEvent(self,event):
                with QPainter(self) as painter:
                    painter.fillRect(self.rect(),Qt.white)
                    painter.setPen(Qt.black)
                    font=QFont('Segoe UI'); font.setPixelSize(18); painter.setFont(font)
                    for i,row in enumerate(rows): painter.drawText(24,47+i*27,row)
                    metrics=painter.fontMetrics()
                    self.hit=QPoint(24+metrics.horizontalAdvance('while the sen'),47+3*27-metrics.capHeight()//2)
        sample=Sample(); sample.resize(620,285)
        area=app.primaryScreen().availableGeometry(); sample.move(area.center()-sample.rect().center())
        sample.show(); sample.raise_(); QTest.qWait(200)
        with TemporaryDirectory() as temp, patch.object(QProcess,'start'):
            window=Window(Notebook(Path(temp)/'desktop.sqlite3'))
            calls=[]; original=window.capture
            def tracked(*args,**kwargs):
                calls.append((args,kwargs)); return original(*args,**kwargs)
            window.capture=tracked
            try:
                window.workspace.source_code='en'
                window.begin(False,sample.mapToGlobal(sample.hit))
                deadline=time.monotonic()+45
                while window.saved_result is None:
                    QApplication.processEvents(); QTest.qWait(15)
                    if time.monotonic()>deadline: self.fail('bounded lookup did not finish: '+window.card.text.toPlainText())
                passage,result=window.saved_result
                self.assertEqual(len(calls),2)
                self.assertEqual((passage.word,passage.text,passage.extent),('sensor',' '.join(rows),'complete'))
                self.assertIn('sensor',window.card.listen.sentence)
                # Closing/new work invalidates a scheduled capture before it reads the screen.
                window.invalidate(); ticket=window.ticket; window.invalidate()
                with patch.object(window,'submit') as submit:
                    original(ticket,sample.mapToGlobal(sample.hit),False,passage)
                    submit.assert_not_called()
            finally:
                window.shutdown(); window.card.close(); window.hide(); window.deleteLater(); sample.close()


if __name__=='__main__':
    if '--contract' in sys.argv:
        report=run_contract()
        for error in report['failures']: print('FAIL',error)
        print(f"Boundary corpus: {report['passed']}/{report['checks']} passed; {report['baseCases']} base cases; {len(report['categories'])} categories.")
        if '--report' in sys.argv:
            path=Path(sys.argv[sys.argv.index('--report')+1]); path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise SystemExit(bool(report['failures']))
    unittest.main()
