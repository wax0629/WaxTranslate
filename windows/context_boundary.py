"""Source lines -> logical block -> exact sentence -> completeness.

Pure contract shared with ContextBoundary.swift. No Qt, OCR or model imports:
platform adapters supply observed lines, source coordinates and the pointed span.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from concurrent.futures import CancelledError
import re
import unicodedata


@dataclass(frozen=True)
class Line:
    text: str
    rect: tuple
    hit: tuple | None = None

    @property
    def left(self): return self.rect[0]
    @property
    def top(self): return self.rect[1]
    @property
    def width(self): return self.rect[2]
    @property
    def height(self): return self.rect[3]
    @property
    def right(self): return self.left + self.width
    @property
    def bottom(self): return self.top + self.height
    @property
    def middle(self): return self.top + self.height / 2


@dataclass(frozen=True)
class Span:
    line: int
    start: int
    end: int
    rect: tuple


@dataclass(frozen=True)
class Analysis:
    text: str
    selection: tuple
    anchor: tuple
    block: str
    block_hit: tuple
    structure: str
    extent: str
    sources: tuple
    joins: tuple


HONORIFICS = {'dr','prof','mr','mrs','ms','fig','eq','no','sr','jr'}
ABBREVIATIONS = {'e.g','i.e','etc','vs','inc','ltd','st','approx','dept','vol'}
STARTERS = {'The','A','An','This','That','These','Those','He','She','It','They','We','I','You','However','Meanwhile','Therefore','Another'}
DANGLING = {'the','a','an','and','or','but','because','although','unless','until','while','that','which','whose','when','where','whether','of','to','from','with','without','for','on','at','by','as','into','between','through','than','not','is','are','was','were','le','la','les','de','du','et','der','die','das','und','el','los','las','del','以及','因为','如果','虽然','以便'}
CONTINUATIONS = ('の','を','は','が','に','と','で','へ','も','から','まで','的','在','与','和','将','把','被','向','从','对','为','由','及','或','은','는','이','가','을','를','의','에','와','과','도','로')
PAIRS = dict(zip('([{（【「『“‘«', ')]}）】」』”’»')) | {'"':'"', "'":"'"}
CLOSING = set(PAIRS.values())
STOPS = '.!?。！？．'
LIST = r'^\s*(?:[•●▪◦*+-]|[0-9]+[.)、])\s*'
COMMENT = r'^\s*//[/!]?(?:\s+|$)'
COMMENT_VARIANT = r'^\s*(?://[/!]?|/|[|Il/]{2})(?:\s+|$)'
NOTICES = {'complete':'', 'missingStart':'句首可能缺失，当前显示可见片段。',
           'missingEnd':'句尾可能缺失，当前显示可见片段。', 'missingBoth':'原文两端可能缺失，当前显示可见片段。',
           'uncertain':'尚不能确认原文完整，当前显示可见片段。'}


def joined_script(text):
    return bool(re.search(r'[\u3400-\u9fff\uf900-\ufaff\u3040-\u30ff\uff66-\uff9f]', text))


def uncased_script(text):
    return joined_script(text) or bool(re.search(r'[\uac00-\ud7af]', text))


def lower_start(text):
    return next((c.islower() for c in text if c.isalpha()), False)


def content(text, ocr_comment=False):
    prefix = re.match(COMMENT_VARIANT if ocr_comment else COMMENT, text)
    start = prefix.end() if prefix else 0
    remainder = text[start:]
    return remainder.strip(), start + len(remainder) - len(remainder.lstrip())


def kind(text):
    stripped = text.strip()
    if not content(text)[0]: return 'empty'
    if re.match(COMMENT, text): return 'comment'
    if re.match(r'^#{1,6}\s+', stripped): return 'title'
    if re.fullmatch(r'(?:[A-Za-z]:)?[\w./\\-]+[/\\][\w.\-]+', stripped): return 'path'
    if re.match(r'^(?:[•●▪◦*+-]|[0-9]+[.)、])\s+', stripped): return 'list'
    if re.match(r'^(?:(?:type|func|struct|class|enum|import|package|return|let|var|const|def|fn|public|private)\b|[{}]\s*$|[A-Za-z_][\w.\[\]]*\s*(?::=|=(?!=)))', stripped): return 'code'
    if re.fullmatch(r'[A-Za-z_]\w*\s+(?:string|int|bool|float\d*|[A-Za-z_]\w*\.[A-Za-z_]\w*)\s*(?:`[^`]*`)?;?', stripped): return 'code'
    return 'prose'


def apostrophe(text, i):
    return text[i] in "'’" and 0 < i < len(text)-1 and text[i-1].isalpha() and text[i+1].isalpha()


def unclosed(text):
    stack = []
    for i,c in enumerate(text):
        if apostrophe(text,i): continue
        if c in PAIRS:
            if stack and stack[-1] == c: stack.pop()
            else: stack.append(PAIRS[c])
        elif stack and stack[-1] == c: stack.pop()
    return bool(stack)


def punctuation_ends(text, i):
    c = text[i]
    if c in '。！？!?': return True
    if 0 < i < len(text)-1 and text[i-1].isdigit() and text[i+1].isdigit(): return False
    if i+1 < len(text) and (text[i+1] == '.' or text[i+1].isalpha()): return False
    left = i
    while left > 0 and (text[left-1].isalpha() or text[left-1] == '.'): left -= 1
    token = text[left:i].lower()
    next_ = i+1
    while next_ < len(text) and (text[next_].isspace() or text[next_] in CLOSING): next_ += 1
    if next_ == len(text): return token not in HONORIFICS and token not in ('e.g','i.e')
    if token in HONORIFICS or len(token) == 1 and token.isalpha(): return False
    if token in ABBREVIATIONS or re.fullmatch(r'(?:[a-z]\.)+[a-z]', token):
        word = re.search(r'[^\W\d_]+', text[next_:])
        return bool(word and word.group() in STARTERS)
    return True


def terminal(text, next_=None):
    text = text.strip()
    i = len(text)-1
    while i >= 0 and text[i] in CLOSING: i -= 1
    return i >= 0 and text[i] in STOPS and punctuation_ends(text + (' '+next_ if next_ is not None else ''), i)


def dangling(text):
    if text and text[-1] in ',，:：;；-‐': return True
    words = re.findall(r'[^\W\d_]+', text, re.UNICODE)
    return bool(words and words[-1].lower() in DANGLING)


def continuation(text):
    return bool(text and text[-1] in ',，:：;；-‐\u00ad') or (not terminal(text) and uncased_script(text) and text.endswith(CONTINUATIONS)) or dangling(text) or unclosed(text)


def sentence_opening(text):
    first = re.search(r'[^\W\d_]+',text)
    return bool(first and first.group() in STARTERS) or bool(re.match(r"^[A-Z](?:[^\W\d_]|['’-])+(?:\s+(?:[^\W\d_]|['’-])+){0,2}\s+(?:is|are|was|were|has|have|had|will|would|can|could|should|does|do|did)\b",text))


def needs_space(left,right,code):
    if not left or not right: return False
    a,b = left[-1],right[0]
    if code.startswith(('zh','ja')) and (joined_script(a) or joined_script(b)): return False
    return not (joined_script(a) and joined_script(b)) and not (a in '、。，；：！？' and joined_script(b)) and b not in '、。，；：！？「」『』）】' and a not in '（【「『'


def coalesce(lines, code=''):
    rows=[]
    for line in sorted(lines,key=lambda x:x.middle):
        row=next((r for r in rows if abs(r[0].middle-line.middle) <= max(r[0].height,line.height)*.4 and min(r[0].bottom,line.bottom)-max(r[0].top,line.top) >= min(r[0].height,line.height)*.6),None)
        if row is None: rows.append([line])
        else: row.append(line)
    output=[]
    for row in rows:
        merged=[]
        for nxt in sorted(row,key=lambda x:x.left):
            if not merged: merged.append(nxt); continue
            left=merged[-1]; height=max(left.height,nxt.height); gap=nxt.left-left.right
            a,b=left.text.strip(),nxt.text.strip(); duplicate=None
            if gap < 0:
                words=a.split()
                duplicate=next((v for n in range(len(words),0,-1) if (v:=' '.join(words[-n:])) == b or b.startswith(v+' ')),None)
            duplicate_width=left.width*len(duplicate)/max(1,len(a)) if duplicate else 0
            overlap=duplicate is not None and duplicate_width*.35 <= -gap <= duplicate_width*1.7+height
            labels=len(a.split()) == len(b.split()) == 1 and not lower_start(b) and not continuation(a)
            if not ((-.4*height <= gap <= height and not labels) or overlap): merged.append(nxt); continue
            prefix=left.text.rstrip(); leading=len(nxt.text)-len(nxt.text.lstrip()); removed=len(duplicate) if overlap else 0
            remainder=b[removed:]; whitespace=len(remainder)-len(remainder.lstrip()); tail=remainder.strip()
            separator=' ' if tail and needs_space(prefix,tail,code) else ''
            hit=left.hit
            if hit is None and nxt.hit is not None:
                pos=nxt.hit[0]-leading
                start=len(prefix)-removed+pos if pos < removed else len(prefix)+len(separator)+pos-removed-whitespace
                hit=(start,start+nxt.hit[1]-nxt.hit[0])
            rect=(min(left.left,nxt.left),min(left.top,nxt.top),max(left.right,nxt.right)-min(left.left,nxt.left),max(left.bottom,nxt.bottom)-min(left.top,nxt.top))
            merged[-1]=Line(prefix+separator+tail,rect,hit)
        output.extend(merged)
    return output


def corroborated_comment(index,lines):
    line=lines[index]
    if not re.match(COMMENT_VARIANT,line.text): return False
    if kind(line.text)=='comment': return True
    if len(content(line.text,True)[0].split()) < 3: return False
    return any(
        i != index and abs(line.left-n.left) <= max(line.height,n.height)*2 and abs(line.middle-n.middle) <= max(line.height,n.height)*2.1
        and (kind(n.text)=='code' or re.match(COMMENT_VARIANT,n.text)) for i,n in enumerate(lines))


def sentence_range(text,hit,list_=False):
    protected=[]
    for m in re.finditer(r'(?:https?://|www\.)\S+|[\w.%+-]+@[\w.-]+\.[^\W\d_]{2,}',text):
        end=m.end()
        while end > m.start() and text[end-1] in '.!?。！？,;': end-=1
        protected.append((m.start(),end))
    prefix=re.match(LIST,text) if list_ else None
    stack=[]; start=i=0
    def trim(a,b):
        while a < b and text[a].isspace(): a+=1
        while b > a and text[b-1].isspace(): b-=1
        return a,b
    while i < len(text):
        c=text[i]
        if c in PAIRS and not apostrophe(text,i):
            if stack and stack[-1]==c: stack.pop()
            else: stack.append(PAIRS[c])
        elif stack and stack[-1]==c: stack.pop()
        if c in STOPS and not any(a <= i < b for a,b in protected) and not (prefix and i < prefix.end()) and punctuation_ends(text,i):
            end=i+1; rest=stack.copy()
            while end < len(text) and text[end] in STOPS: end+=1
            while end < len(text) and text[end] in CLOSING:
                if rest and rest[-1]==text[end]: rest.pop()
                end+=1
            next_=end
            while next_ < len(text) and text[next_].isspace(): next_+=1
            attribution=bool(stack) and next_ < len(text) and (text[next_].islower() or joined_script(text[next_]) or text[next_] in ',，:：;；')
            if not rest and not attribution:
                candidate=trim(start,end)
                if candidate[0] <= hit[0] and candidate[1] >= hit[1]: return candidate
                start=i=next_; stack=[]; continue
        i+=1
    return trim(start,len(text))


def analyze(lines, *, source='editor', code='', capture=None):
    if not code:
        joined='\n'.join(x.text for x in lines)
        code='ja' if re.search(r'[ぁ-ヺ]',joined) else 'ko' if re.search(r'[\uac00-\ud7af]',joined) else 'zh' if joined_script(joined) else 'en'
    lines=coalesce(lines,code) if source=='ocr' else list(lines)
    anchor=next(i for i,x in enumerate(lines) if x.hit is not None)
    bodies=[content(x.text,source=='ocr' and corroborated_comment(i,lines)) for i,x in enumerate(lines)]
    kinds=['empty' if not bodies[i][0] else 'comment' if source=='ocr' and corroborated_comment(i,lines) else kind(x.text) for i,x in enumerate(lines)]
    indents=[sum(4 if c=='\t' else 1 for c in x.text[:len(x.text)-len(x.text.lstrip())]) for x in lines]
    def neighbor(index,direction):
        if source=='editor': return index+direction if 0 <= index+direction < len(lines) else None
        current=lines[index]
        choices=[]
        for i,n in enumerate(lines):
            height=max(current.height,n.height); step=direction*(n.middle-current.middle)
            overlap=min(current.right,n.right)-max(current.left,n.left)
            if .45*min(current.height,n.height) <= step <= 3.2*height and overlap >= .25*min(current.width,n.width) and abs(n.left-current.left) <= 3.5*height:
                choices.append((abs(n.middle-current.middle)+.15*abs(n.left-current.left),i))
        return min(choices)[1] if choices else None
    def hard(left,right):
        if kinds[left] in ('empty','title','path','code') or kinds[right] in ('empty','title','path','code','list'): return True
        if (kinds[left]=='comment') != (kinds[right]=='comment'): return True
        a,b=bodies[left][0],bodies[right][0]
        if terminal(a,b): return True
        if source=='editor': return indents[right]>indents[left] and not continuation(a)
        x,y=lines[left],lines[right]; h=max(x.height,y.height)
        return h > min(x.height,y.height)*1.6 or y.middle-x.middle>2.05*h or (y.left-x.left>=h and not continuation(a) and not lower_start(b))
    def reason(left,right):
        if kinds[left] in ('empty','title','path','code') or kinds[right] in ('empty','title','path','code','list'): return None
        if (kinds[left]=='comment') != (kinds[right]=='comment'): return None
        a,b=bodies[left][0],bodies[right][0]
        if not a or not b: return None
        ends=terminal(a,b); continued=continuation(a) or lower_start(b) or not ends and a.endswith('.')
        x,y=lines[left],lines[right]
        if kinds[left]=='list':
            marker=re.match(LIST,x.text)
            indented=indents[right] >= marker.end() if source=='editor' else y.left>x.left+x.height*.45
            return 'list-continuation' if indented or not ends and continued else None
        if source=='editor':
            if kinds[left]=='comment': return 'comment-continuation'
            if ends or indents[right]>indents[left] and not continuation(a): return None
            return 'text-continuation' if continued or uncased_script(a) and uncased_script(b) and len(a)>=8 else None
        height=max(x.height,y.height)
        if height > min(x.height,y.height)*1.6 or y.middle-x.middle>2.05*height: return None
        if kinds[left]=='comment': return 'comment-continuation'
        if not ends and not continuation(a) and sentence_opening(b): return None
        if y.left-x.left>=height and not continuation(a) and not lower_start(b): return None
        if len(a.split())<=3 and not joined_script(a) and not ends and not continued: return None
        if joined_script(a) and len(a)<8 and not continuation(a) and not ends: return None
        return 'layout-and-language' if continued else 'same-column-flow'
    before=[]; after=[]; joins=[]; uncertain_start=uncertain_end=False
    if kinds[anchor] not in ('empty','title','path','code'):
        for direction in (-1,1):
            current=anchor
            while (next_:=neighbor(current,direction)) is not None:
                left,right=(next_,current) if direction<0 else (current,next_)
                why=reason(left,right)
                if why is None:
                    if not hard(left,right):
                        if direction<0: uncertain_start=True
                        else: uncertain_end=True
                    break
                joins.append((left,right,why)); (before if direction<0 else after).append(next_); current=next_
    indices=before[::-1]+[anchor]+after
    text=''; hit=(0,0); spans=[]; seams=[]
    for i in indices:
        body,leading=bodies[i]
        if text:
            if text.endswith('\u00ad'):
                text=text[:-1]; spans[-1]=replace(spans[-1],end=spans[-1].end-1); seams.append(len(text))
            elif text[-1] in '-‐': seams.append(len(text))
            elif needs_space(text,body,code): text+=' '
        if lines[i].hit is not None:
            a,b=lines[i].hit; hit=(len(text)+a-leading,len(text)+b-leading)
        spans.append(Span(i,len(text),len(text)+len(body),lines[i].rect)); text+=body
    pointer=hit
    for seam in seams:
        def word(i): return 0 <= i < len(text) and (unicodedata.category(text[i])[0] in 'LNM' or text[i] in "-'’‐")
        left=right=seam
        while word(left-1): left-=1
        while word(right): right+=1
        if left<hit[1] and right>hit[0]: hit=(left,right)
    block_kind='list' if kinds[indices[0]]=='list' else kinds[anchor]
    unit=(0,len(text)) if block_kind in ('title','path','code') else sentence_range(text,hit,block_kind=='list')
    a,b=unit; context=text[a:b]; selected=(hit[0]-a,hit[1]-a); pointed=(pointer[0]-a,pointer[1]-a)
    structure=block_kind if block_kind in ('list','title','path','code') else 'sentence'
    if structure=='sentence' and (context.startswith(('…','...')) or context.endswith(('…','...'))): structure='fragment'
    sources=tuple(Span(s.line,max(s.start,a)-a,min(s.end,b)-a,s.rect) for s in spans if s.start<b and s.end>a)
    ambiguous=(a==0 and (uncertain_start or source=='ocr' and kinds[indices[0]]!='comment' and re.match(COMMENT_VARIANT,lines[indices[0]].text))) or b==len(text) and uncertain_end
    extent=completeness(context,structure,unit,len(text),sources,capture,selected==(0,len(context)),bool(ambiguous))
    return Analysis(context,selected,pointed,text,hit,structure,extent,sources,tuple(joins))


def completeness(text,structure,unit,block_length,sources,capture,standalone,ambiguous):
    if structure in ('title','path','code'): return 'complete'
    first=text.startswith(('…','...')); last=text.endswith(('…','...'))
    if capture and sources:
        x,y,w,h=capture; a=Line('',sources[0].rect); b=Line('',sources[-1].rect)
        if unit[0]==0: first=first or a.top-y<=a.height*1.2 or a.left-x<=a.height*.45
        if unit[1]==block_length and not terminal(text): last=last or y+h-b.bottom<=b.height*1.2 or x+w-b.right<=b.height*.45
    last=last or unclosed(text) or dangling(text)
    if first and last: return 'missingBoth'
    if first: return 'missingStart'
    if last: return 'missingEnd'
    if standalone and not ambiguous: return 'complete'
    if ambiguous or not terminal(text) or unit[0]==0 and lower_start(text): return 'uncertain'
    return 'complete'


def editor_lines(text,start,end):
    result=[]; offset=0
    for i,line in enumerate(text.split('\n')):
        a,b=max(start,offset),min(end,offset+len(line))
        result.append(Line(line,(0,i*25,max(1,len(line)*9),18),(a-offset,b-offset) if b>a else None))
        offset+=len(line)+1
    return result


def complete_capture(first, expanded, cancelled=lambda:False):
    def check():
        if cancelled(): raise CancelledError()
    check()
    if not first.needs_context_expansion: return first
    try:
        next_=expanded(); check()
        return choose_capture(first,next_)
    except CancelledError: raise
    except (ValueError,RuntimeError,OSError): check(); return first


def choose_capture(first,next_):
    def pointed(p): return p.text[slice(*(p.anchor or p.selection))].casefold() if p.selection else p.text.casefold()
    if pointed(first)!=pointed(next_): return first
    return next_ if next_.has_complete_context or len(next_.text)>=len(first.text) else first
