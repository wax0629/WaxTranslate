"""Explainable query and bounded-context policy shared by the Windows card."""
import re
from dataclasses import replace


def chinese_context(passage):
    surrounding = passage.text
    if passage.selection:
        a, b = passage.selection
        surrounding = surrounding[:a] + surrounding[b:]
    return bool(re.search(r"[\u3400-\u9fff]", surrounding)) and not re.search(r"[ぁ-ヺ]", surrounding)


def needs_confirmation(passage):
    return passage.structure == 'path' or passage.word == 'VoiceOver' or bool(re.search(r'[a-z][A-Z]|[_/#]|\.\w+$', passage.word))


def local_reference(passage):
    word, context = passage.word, passage.text
    if word in ('README', 'README.md'):
        return '惯用名称参考', '项目说明文件，通常介绍项目、安装和使用方法。', '文件名称'
    if word == 'VoiceOver' and re.search(r'Apple|苹果|macOS|iOS|辅助功能|读屏|屏幕朗读', context, re.I):
        return '名称参考', 'Apple 的屏幕朗读辅助功能。', '功能名称'
    if word == 'Docker' and re.search(r'部署|容器|镜像',context):
        return '术语参考','用容器打包和运行应用的平台。','开发工具'
    if word == 'Redis' and re.search(r'缓存|数据库|内存|部署|cache|database|deploy', context, re.I):
        return '名称参考', '一种内存数据存储系统，常用于缓存。', '技术名称'
    if word.lower() == 'transformer':
        if re.search(r'变电|电压|电力|电路|power|voltage', context, re.I):
            return '语境术语参考', '变压器，用于改变交流电压。', '技术词'
        if re.search(r'模型|神经网络|注意力|OCR|attention|neural', context, re.I):
            return '语境术语参考', '基于注意力机制的神经网络架构。', '模型架构'
    if word.lower() == 'token' and passage.selection:
        before = context[max(0, passage.selection[0]-18):passage.selection[0]]
        if re.search(r'(?:验证|认证|身份|访问|access|auth)[^与，。；]*$', before, re.I):
            return '语境术语参考', '令牌，用于表示身份、权限或访问凭据。', '技术词'
        if re.search(r'(?:模型|输入|分词|文本|language model)[^与，。；]*$', before, re.I):
            return '语境术语参考', '词元，模型处理文本时使用的基本单位。', '技术词'
    phrases = {'attention mask': '注意力掩码，用来控制模型可以关注哪些位置。',
               'padding token': '填充词元，用于将不同长度的输入补齐。'}
    if word.lower() in phrases:
        return '术语参考', phrases[word.lower()], '英语术语'


def bounded_context(passage):
    if not passage.selection:
        return passage, 0
    limit = 60 if chinese_context(passage) else 160
    if len(passage.text) <= limit:
        return passage, 0
    a, b = passage.selection
    left = max(0, a - max(0, (limit - (b-a)) // 2))
    right = min(len(passage.text), max(b, left + limit))
    left = min(left, max(0, right-limit))
    # Do not split Latin words at either end.
    while left > 0 and passage.text[left-1:left+1].isascii() and passage.text[left-1:left+1].isalpha():
        left -= 1
    while right < len(passage.text) and passage.text[right-1:right+1].isascii() and passage.text[right-1:right+1].isalpha():
        right += 1
    return replace(passage, text=passage.text[left:right], selection=(a-left, b-left)), left
