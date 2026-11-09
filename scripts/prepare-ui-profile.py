"""Create synthetic macOS UI fixtures without touching the user's app domain."""
import argparse
import json
import plistlib
import subprocess
import time
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', default='WaxTranslate.Test.' + uuid.uuid4().hex)
parser.add_argument('--scenario', choices=['empty', 'legacy', 'full', 'terms', 'context'], default='full')
args = parser.parse_args()
if not args.profile.startswith('WaxTranslate.Test.') or len(args.profile) > 160:
    parser.error('Only a dedicated WaxTranslate.Test.* profile is allowed.')
now = time.time() - 978307200  # JSONEncoder's Date reference is 2001-01-01 UTC.
prefs = {'reading.sourceLanguage': 'en', 'lookup.onlineReferences': False, 'window.showOnLaunch': True}
if args.scenario not in ('empty', 'terms', 'context'):
    entries = [
        dict(id=str(uuid.uuid4()), source='bank', target='河岸', context='They sat on the river bank.', due=0, streak=2),
        dict(id=str(uuid.uuid4()), source='warehouse', target='仓库', context='The warehouse stores goods.', due=0, streak=3),
    ]
    prefs['notebook.entries.v1'] = json.dumps(entries, ensure_ascii=False).encode()
if args.scenario in ('full', 'terms', 'context'):
    examples = [('logistics', '物流'), ('rule out', '排除'), ('ran out of', '用完了'),
                ('bank', '银行'), ('warehouse', '仓库'), ('OCR', '光学字符识别')]
    contexts = {}
    if args.scenario == 'terms':
        prefs['reading.sourceLanguage'] = ''
        prefs['lookup.onlineReferences'] = True
        examples = [('OCR', '光学字符识别'), ('API', '应用程序编程接口'), ('SDK', '软件开发工具包'),
                    ('JSON', '数据格式'), ('Codex', '编程助手'), ('Rust', '编程语言')]
        contexts = {'OCR': '这里用OCR识别图片里的文字，结果保存在本机。', 'API': 'The API returns a response.',
                    'SDK': '开发应用需要SDK软件开发工具包。', 'JSON': '接口用JSON数据格式交换内容。',
                    'Codex': '开发者用Codex修复仓库里的代码。', 'Rust': '我们用Rust开发软件。'}
    if args.scenario == 'context':
        examples = [('magpie', '喜鹊'), ('bank', '河岸'), ('API', '应用程序编程接口'), ('OCR', '光学字符识别')]
        contexts = {'magpie': 'In a magpie, the black and white feathers are easy to recognize.',
                    'bank': 'After a very long walk through the quiet village and past the old houses where people were preparing for the evening, they sat on the river bank and watched the water flow slowly toward the distant mountains.',
                    'API': 'The API returns a response.', 'OCR': '这里用OCR识别图片中的文字。'}
    recent = []
    for index, (word, meaning) in enumerate(examples):
        context = contexts.get(word, word)
        offset = context.index(word)
        span = [len(context[:offset].encode('utf-16-le'))//2, len(word.encode('utf-16-le'))//2]
        recent.append(dict(id=str(uuid.uuid4()), passage=dict(text=word, context=context,
                      selection=span, anchor=span, language='zh-Hans' if (args.scenario == 'terms' and word != 'API') or (args.scenario == 'context' and word == 'OCR') else 'en'), meaning=meaning, date=now-index*900))
    prefs['notebook.activity.v1'] = json.dumps(dict(total=len(recent), day=now, today=len(recent), recent=recent), ensure_ascii=False).encode()
subprocess.run(['/usr/bin/defaults', 'import', args.profile, '-'], input=plistlib.dumps(prefs), check=True)
print(args.profile)
print('Synthetic fixture only. Run the installed app with --test-profile ' + args.profile + ' --show')
print('After quitting the fixture app, remove only this profile with: defaults delete ' + args.profile)
