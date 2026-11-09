"""Create synthetic macOS UI fixtures without touching the user's app domain."""
import argparse
import json
import plistlib
import subprocess
import time
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--profile', default='WaxTranslate.Test.' + uuid.uuid4().hex)
parser.add_argument('--scenario', choices=['empty', 'legacy', 'full'], default='full')
args = parser.parse_args()
if not args.profile.startswith('WaxTranslate.Test.') or len(args.profile) > 160:
    parser.error('Only a dedicated WaxTranslate.Test.* profile is allowed.')
now = time.time() - 978307200  # JSONEncoder's Date reference is 2001-01-01 UTC.
prefs = {'reading.sourceLanguage': 'en', 'lookup.onlineReferences': False, 'window.showOnLaunch': True}
if args.scenario != 'empty':
    entries = [
        dict(id=str(uuid.uuid4()), source='bank', target='河岸', context='They sat on the river bank.', due=0, streak=2),
        dict(id=str(uuid.uuid4()), source='warehouse', target='仓库', context='The warehouse stores goods.', due=0, streak=3),
    ]
    prefs['notebook.entries.v1'] = json.dumps(entries, ensure_ascii=False).encode()
if args.scenario == 'full':
    examples = [('logistics', '物流'), ('rule out', '排除'), ('ran out of', '用完了'),
                ('bank', '银行'), ('warehouse', '仓库'), ('OCR', '光学字符识别')]
    recent = []
    for index, (word, meaning) in enumerate(examples):
        span = [0, len(word)]  # NSRange uses an unkeyed Codable representation.
        recent.append(dict(id=str(uuid.uuid4()), passage=dict(text=word, context=word,
                      selection=span, anchor=span, language='en'), meaning=meaning, date=now-index*900))
    prefs['notebook.activity.v1'] = json.dumps(dict(total=6, day=now, today=6, recent=recent), ensure_ascii=False).encode()
subprocess.run(['/usr/bin/defaults', 'import', args.profile, '-'], input=plistlib.dumps(prefs), check=True)
print(args.profile)
print('Synthetic fixture only. Run the installed app with --test-profile ' + args.profile + ' --show')
print('After quitting the fixture app, remove only this profile with: defaults delete ' + args.profile)
