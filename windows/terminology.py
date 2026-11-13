"""Explain reading terms from explicit definitions and a small offline glossary."""

import re
import unicodedata


# A "model" can also be physical or clinical. The ML sense needs a specific
# ML term, or a model with evidence about one of its components or variants.
_ABLATION_CUE = (r"\b(?:encoders?|decoders?|neural networks?|datasets?|transformers?|llms?|machine learning)\b|"
                 r"编码器|解码器|神经网络|数据集|机器学习|消融实验|"
                 r"(?=.*(?:\bmodels?\b|模型))(?=.*(?:\b(?:components?|layers?|modules?|variants?|architectures?)\b|组件|模块|变体))")

# Whole expressions have their own reading unit. Ambiguous expressions also
# require nearby evidence before the reader expands a single pointed word.
READING_PHRASES = [
    dict(forms=["ablation study", "ablation studies"], translation="消融实验",
         detail="移除或替换模型中的某一部分，比较结果如何变化。", cue=_ABLATION_CUE,
         exclude=r"\b(?:catheters?|cardiac|atrial|patients?)\b|手术|消融术|导管|患者|心房"),
    dict(forms=["emergent ability", "emergent abilities", "emergent capability", "emergent capabilities"],
         translation="涌现能力", detail="模型扩大后才表现出来的能力。",
         cue=r"\b(?:models?|llms?|scal(?:e|ing))\b|模型|规模|大语言"),
    dict(forms=["stochastic gradient descent"], translation="随机梯度下降", detail="每次用一个样本或一个小批次估计梯度，再更新参数。"),
    dict(forms=["gradient descent"], translation="梯度下降", detail="沿着函数值下降的方向逐步更新参数。"),
    dict(forms=["confidence interval", "confidence intervals"], translation="置信区间", detail="由样本估算的参数范围，按给定的置信水平构造。"),
    dict(forms=["standard deviation", "standard deviations"], translation="标准差", detail="衡量一组数值相对平均值的离散程度。"),
    dict(forms=["attention mask", "attention masks"], translation="注意力掩码", detail="用来控制模型可以关注哪些位置。"),
    dict(forms=["padding token", "padding tokens"], translation="填充词元", detail="用于将不同长度的输入补齐。"),
    dict(forms=["race condition", "race conditions"], translation="竞态条件", detail="多个操作的执行顺序会改变程序结果。",
         cue=r"\b(?:threads?|concurren(?:t|cy)|locks?|processes|writes?|deadlocks?|deadlocked|synchroni[sz]ation|memory safety|atomics?)\b|并发|线程|进程"),
]

_PHRASES_BY_FORM = {form: phrase for phrase in READING_PHRASES for form in phrase["forms"]}
_FORMS = "|".join(re.escape(form).replace(r"\ ", r"[ \t\u00a0\u202f]+")
                  for form in sorted(_PHRASES_BY_FORM, key=len, reverse=True))
_PHRASES = re.compile(r"(?<![a-z0-9_/‐‑-])(?<![a-z0-9_]\.)(?:" + _FORMS +
                      r")(?![a-z0-9_/‐‑-]|\.[a-z0-9_])", re.I | re.ASCII)


def phrase_at(text, hit, structure):
    if not hit or structure in ("code", "path"):
        return None
    for match in _PHRASES.finditer(text):
        if match.start() > hit[0]:
            break
        if match.start() <= hit[0] < hit[1] <= match.end():
            phrase = _PHRASES_BY_FORM[" ".join(match[0].lower().split())]
            if "cue" in phrase:
                left = re.split(r"[,;!?，；。！？]|\b(?:but|whereas)\b", text[max(0, match.start()-110):match.start()], flags=re.I)[-1]
                right = re.split(r"[,;!?，；。！？]|\b(?:but|whereas)\b", text[match.end():match.end()+110], flags=re.I)[0]
                evidence = left + " " + right
                matches = lambda pattern: re.search(pattern, evidence, re.I) is not None
                if not matches(phrase["cue"]) or ("exclude" in phrase and matches(phrase["exclude"])):
                    return None
            return match.span(), phrase
    return None


def selected_phrase(passage):
    if not passage.selection or not any(c.isspace() for c in passage.word) or passage.source_code not in ("", "en", "zh", "zh-Hans"):
        return None
    match = phrase_at(passage.text, passage.selection, passage.structure)
    return match[1] if match and match[0] == passage.selection else None


# Each gloss is written for a reader who may not know the English expansion.
ACRONYMS = {
    "AI": ("artificial intelligence", "人工智能，指让机器完成语言理解、推理等任务的技术。"),
    "API": ("application programming interface", "应用程序编程接口，供一个程序调用另一个程序提供的功能。"),
    "BPE": ("byte pair encoding", "字节对编码，一种反复合并常见相邻单元的算法，在语言模型中常用于分词。"),
    "CLI": ("command-line interface", "命令行界面，可以输入文本命令来操作程序。"),
    "CPU": ("central processing unit", "中央处理器，负责执行计算机指令。"),
    "CSS": ("cascading style sheets", "层叠样式表，用来指定网页的颜色、字体和布局。"),
    "DNS": ("domain name system", "域名系统，可以根据域名查到服务器的网络地址。"),
    "GPU": ("graphics processing unit", "图形处理器，擅长并行计算，常用于图形渲染和模型训练。"),
    "GUI": ("graphical user interface", "图形用户界面，可以通过窗口、图标和按钮操作程序。"),
    "HTML": ("hypertext markup language", "超文本标记语言，用来描述网页内容的结构。"),
    "HTTP": ("hypertext transfer protocol", "超文本传输协议，规定客户端和服务器如何交换请求与响应。"),
    "HTTPS": ("hypertext transfer protocol secure", "使用 TLS 加密连接的 HTTP，常见于安全网页连接。"),
    "IDE": ("integrated development environment", "集成开发环境，把写代码、运行和调试等工具放在一起。"),
    "JSON": ("JavaScript object notation", "一种文本数据格式，常用于程序之间交换键值、列表等数据。"),
    "JWT": ("JSON web token", "一种用紧凑格式传递声明的令牌，常用于让服务器验证登录身份。"),
    "LLM": ("large language model", "大语言模型，能根据输入的上下文生成文本。"),
    "OCR": ("optical character recognition", "光学字符识别，把图片里的文字转成可处理的文本。"),
    "OS": ("operating system", "操作系统，负责管理硬件资源并运行应用程序。"),
    "RAG": ("retrieval-augmented generation", "检索增强生成，先查找相关资料，再用这些资料辅助模型回答。"),
    "RAM": ("random-access memory", "随机存取存储器，常指程序运行时使用的内存。"),
    "REST": ("representational state transfer", "表述性状态转移，一种按资源组织网络服务的架构风格。"),
    "SDK": ("software development kit", "软件开发工具包，提供为某个平台开发应用所需的库和工具。"),
    "SQL": ("structured query language", "结构化查询语言，用来查询和修改关系数据库里的数据。"),
    "SSH": ("secure shell", "一种加密网络协议，常用于远程登录和执行命令。"),
    "TLS": ("transport layer security", "传输层安全协议，为网络连接提供加密和身份验证。"),
    "UI": ("user interface", "用户界面，人们操作产品时接触的控件和信息呈现。"),
    "URL": ("uniform resource locator", "统一资源定位符，如浏览器地址栏中的网址。"),
    "UX": ("user experience", "用户体验，指一个人使用产品时的实际感受。"),
}

NAMES = {
    "chatgpt": ("产品名", "OpenAI 的对话式 AI 助手，可以用自然语言提问、写作或讨论代码。"),
    "gpt-4o": ("模型名", "OpenAI 的多模态模型，能处理文字和图像等输入。"),
    "openai": ("机构名", "开发 ChatGPT 和 Codex 等人工智能产品的机构。"),
    "github": ("平台名", "托管 Git 代码仓库的平台，支持协作开发和代码审查。"),
    "node.js": ("运行环境", "让 JavaScript 程序在浏览器外运行的环境，常用于服务器和命令行工具。"),
    ".net": ("开发平台", "微软发起的跨平台开发平台，提供运行环境和程序库，支持 C# 等语言。"),
    "c++": ("编程语言", "通用编程语言，常用于对性能或内存控制有要求的软件。"),
    "c#": ("编程语言", "读作 C sharp，常用于在 .NET 平台上开发应用。"),
    "f#": ("编程语言", "读作 F sharp，一门注重函数式编程的 .NET 语言。"),
    "ciallo": ("网络用语", "一种俏皮的招呼，相当于「嗨！」，常见于柚子社游戏及其玩家社群。"),
}

# These names are also ordinary English words. Only a nearby construction
# identifying the technology should override a normal word lookup.
_LANGUAGE_CUE = r"(?:written|coded|implemented|programmed|rewritten) in |(?:code|applications?|services?) (?:in|to) "
CONTEXT_NAMES = {
    "rust": (rf"(?:{_LANGUAGE_CUE})rust|rust (?:programming language|compiler|crate|code)|borrow checker|rustc",
             "编程语言", "一种重视内存安全和性能的编程语言，常用于编写系统软件和服务。"),
    "go": (rf"(?:{_LANGUAGE_CUE})go|go (?:programming language|compiler|modules?|goroutines?)|golang",
           "编程语言", "一种支持并发的编程语言，也常叫 Golang，常用于编写服务器和命令行工具。"),
    "react": (r"react (?:components?|hooks?|app|library)|(?:jsx|frontend|interface|ui) (?:with|in|using) react",
              "界面库", "用于构建用户界面的 JavaScript 库，可以把界面拆成可复用的组件。"),
    "docker": (r"docker (?:containers?|images?|compose|engine|desktop|build|run)|"
               r"(?:containers?|images?) (?:with|in|using) docker",
               "开发工具", "用容器打包和运行应用的平台，方便在不同环境中部署同一程序。"),
    "signal": (r"(?:uses?|installed|via|on) signal (?:for |to )?(?:encrypted|private|messag\w*)|"
               r"signal (?:messenger|messaging app)",
               "应用名", "一款使用端到端加密的通信应用，可以发送消息和进行通话。"),
}

# Distinct cues keep a lone ambiguous term from acquiring a made-up domain.
# Each tuple contains the written-out form, Chinese explanation, and nearby cues.
SENSES = {
    "mvp": (
        ("minimum viable product", "最小可行产品，先用满足核心需求的版本验证用户是否需要它。",
         r"products?|prototypes?|customers?|users?|launch(?:ed)?|ship(?:ped)?|built|startup|features?|roadmap"),
        ("most valuable player", "最有价值球员，指一场比赛或一个赛季里表现最突出的选手。",
         r"players?|goals?|scored?|finals?|season|league|basketball|nba|athletes?|tournament|match|"
         r"(?:was|is|been) (?:named|voted|crowned) (?:the )?mvp|won (?:the )?mvp"),
        ("model-view-presenter", "模型－视图－表示器，一种把数据、界面和交互逻辑分开的设计模式。",
         r"presenter|view|mvc|mvvm|design pattern"),
        ("most valuable professional", "微软最有价值专家，指获得微软技术社区贡献奖项的人。",
         r"microsoft|technical community"),
        ("mitral valve prolapse", "二尖瓣脱垂，指心脏二尖瓣的瓣叶向左心房突出。",
         r"mitral|valve|cardiac|cardiology|echocardiogram"),
    ),
    "prd": (
        ("product requirements document", "产品需求文档，说明要解决的用户问题、功能及验收要求。",
         r"products?|requirements?|documents?|draft(?:ed)?|writ(?:e|ing)|features?|review(?:ed)?|specs?"),
        ("Pearl River Delta", "珠江三角洲，是中国广东省珠江下游的区域。",
         r"pearl river|guangdong|guangzhou|delta|hong kong|shenzhen"),
    ),
    "codex": (
        ("OpenAI Codex", "OpenAI 的编程助手，可以读懂代码库、修改代码和检查问题。",
         r"openai|chatgpt|cod(?:e|ing)|codebase|repository|repo|agent|cli|bugs?|tests?|pull request|function|developers?|software|patch"),
        ("codex", "册页式手抄本，把书页装订成册的古代书籍。",
         r"manuscripts?|medieval|ancient|parchment|scribe|illuminated|library|leaves|folios?|book"),
        ("Codex Alimentarius", "国际食品法典，汇集了食品安全和贸易方面的标准、指南及操作规范。",
         r"alimentarius|food standards?|food safety"),
    ),
}
MULTIPLE = {
    "mvp": "产品开发中常指最小可行产品（minimum viable product），体育中常指最有价值球员（most valuable player）。",
    "prd": "做产品时常指产品需求文档（product requirements document），地理文章里也可指珠江三角洲（Pearl River Delta）。",
    "codex": "编程工具名常指 OpenAI 的编程助手，在历史文献里通常指装订成册的古代手抄本。",
}


def _key(text):
    return unicodedata.normalize("NFKC", text).casefold().replace("–", "-").replace("‐", "-")


def _phrase_key(text):
    return " ".join(re.findall(r"[a-z0-9]+", _key(text)))


def _format_sense(expansion, gloss):
    title, comma, detail = gloss.rstrip("。").partition("，")
    return f"{title}（{expansion}）{comma}{detail}。"


_WORD = r"[A-Za-z][A-Za-z0-9]*(?:[-‐‑–][A-Za-z0-9]+)*"
_WORDS_LEFT = re.compile(rf"(?<![A-Za-z0-9-])({_WORD}(?:\s+{_WORD}){{0,11}})\s*$")
_WORDS_RIGHT = re.compile(rf"\s*({_WORD}(?:\s+{_WORD}){{0,11}})")
_CONNECTORS = {"and", "for", "in", "of", "on", "the", "to", "with"}


def _matches_initials(phrase, acronym):
    words = _phrase_key(phrase).split()
    if len(words) < 2 or len(words) > len(acronym) + 4:
        return False
    # Connectors can contribute an initial (PoC) or be omitted (DoS vs DS).
    positions = {0}
    for word in words:
        advanced = {i + 1 for i in positions if i < len(acronym) and acronym[i] == word[0]}
        positions = positions | advanced if word in _CONNECTORS else advanced
    return len(acronym) in positions and words[0][0] == acronym[0] and words[-1] not in _CONNECTORS


def _expansion_at(before, after, acronym):
    if before.endswith(("(", "（")) and after.startswith((")", "）")):
        phrase = _WORDS_LEFT.search(before[:-1])
        if phrase:
            words = phrase[1].split()
            for start in range(len(words) - 1, -1, -1):
                candidate = " ".join(words[start:])
                if _matches_initials(candidate, acronym):
                    return candidate
    parenthetical = re.match(r"[(（]([^()（）.!?;]{2,160})[)）]", after)
    if parenthetical:
        candidate = " ".join(parenthetical[1].split())
        if re.fullmatch(rf"{_WORD}(?:\s+{_WORD})*", candidate) and _matches_initials(candidate, acronym):
            return candidate
    intro = re.match(r"(?:stands? for|is short for|is an abbreviation for)\s+", after, re.I)
    if intro:
        phrase = _WORDS_RIGHT.match(after[intro.end():])
        if phrase:
            words = phrase[1].split()
            for end in range(1, len(words) + 1):
                candidate = " ".join(words[:end])
                if _matches_initials(candidate, acronym):
                    return candidate
    return ""


_QUOTES = {'"': '"', "'": "'", "“": "”", "‘": "’", "`": "`", "<": ">"}
_NON_SUBJECTS = {"he", "she", "i", "we", "us", "they", "you", "it", "who", "that", "this", "which",
                 "no", "one", "the", "some", "what", "nobody", "everybody", "someone", "anyone"}


def _prose_at(before, after, word):
    opener = before[-1:]
    quoted = opener in _QUOTES and after.startswith(_QUOTES[opener])
    if quoted:
        before = before[:-1].rstrip()
        after = after[1:].lstrip()
    # Require a declaration, not an incidental phrase like "I think he means".
    clause = re.split(r"[.!?;:\n]", before)[-1].strip()
    lead = r"(?:(?:here|in this (?:paper|article|study|context|document))\s*,?\s*)?"
    if re.fullmatch(lead + r"we use(?: the (?:word|term|name))?", clause, re.I):
        marker = re.match(r"to (?:mean|denote)\s+", after, re.I)
    else:
        introduced = re.fullmatch(lead + r"(?:(?:the|our) (?:word|term|name))?", clause, re.I)
        if introduced is None:
            return ""
        markers = r"means|denotes|refers to"
        if not quoted and not clause:
            if word.casefold() in _NON_SUBJECTS or not word[0].isupper():
                return ""
            # A bare person's name followed by "means to ..." expresses intent.
            markers = r"denotes|refers to"
        if not quoted and word.casefold() in _NON_SUBJECTS:
            return ""
        marker = re.match(rf"(?:{markers})\s+", after, re.I)
    if not marker:
        return ""
    tail = after[marker.end():].strip()
    if tail[:1] in _QUOTES and _QUOTES[tail[0]] in tail[1:]:
        tail = tail[1:tail.index(_QUOTES[tail[0]], 1)]
    # Keep the author's first explanation. A trailing example can stand alone.
    gloss = re.split(r"[;!?]|\.(?=\s|$)|,?\s+(?:for example|for instance)\b", tail, maxsplit=1, flags=re.I)[0]
    words = gloss.strip(" ,").split()
    if not words or not re.search(r"[A-Za-z]", gloss) or len(words) == 1 and words[0].casefold() in _NON_SUBJECTS:
        return ""
    return " ".join(words[:26]) + ("..." if len(words) > 26 else "")


def _written_definition(text, word, offset, try_acronym):
    positions = []
    ending = "s?" if try_acronym else ""
    for match in re.finditer(rf"(?<![\w-]){re.escape(word)}{ending}(?![\w-])", text, re.I):
        before = re.split(r"\n[ \t]*\n", text[max(0, match.start() - 200):match.start()])[-1].rstrip()
        after = re.split(r"\n[ \t]*\n", text[match.end():match.end() + 500], maxsplit=1)[0].lstrip()
        # Reusing a lowercase word must not inherit a different uppercase abbreviation.
        meaning = _prose_at(before, after, match[0]) if word.isupper() == match[0].isupper() else ""
        kind = "文中用语"
        if not meaning and try_acronym and match[0] in (word, word + "s"):
            meaning = _expansion_at(before, after, word.casefold())
            kind = "缩写"
        if meaning:
            item = meaning, kind
            if match.start() == offset:
                return item, True
            positions.append((match.start(), item))
    if not positions:
        return None, False
    if offset is not None:
        prior = [item for start, item in positions if start <= offset]
        return (prior[-1] if prior else positions[0][1]), False
    first = positions[0][1]
    consistent = all(_phrase_key(value[0]) == _phrase_key(first[0]) for _, value in positions)
    return (first if consistent else None), False


def _local_clause(passage):
    start, end = passage.selection
    # Never borrow cues from another occurrence in the same sentence.
    boundary = rf"[,;!?]|\b(?:whereas|while|but|{re.escape(passage.word)})\b"
    left = re.split(boundary, passage.text[:start], flags=re.I)[-1]
    right = re.split(boundary, passage.text[end:], flags=re.I)[0]
    return " ".join((left[-110:] + passage.word + right[:110]).casefold().split())


_LOWERCASE_CUES = {
    "ram": r"\b(?:gb|gib|mb|ddr[345]|memory)\b",
    "rag": r"\b(?:llm|retrieval|embeddings?|vector database)\b|\brag pipeline\b",
    "ide": r"\b(?:debugger|plugins?|editor|source code)\b",
    "rest": r"\brest (?:api|endpoints?|services?)\b",
}


def resolve_term(passage, context=""):
    """Return (source label, explanation, kind), or defer to ordinary translation."""
    if not passage.selection or not passage.word or len(passage.word) > 100:
        return None
    word = re.sub(r"['’]s$", "", unicodedata.normalize("NFKC", passage.word), flags=re.I)
    if re.fullmatch(r"[A-Z]{2,10}s", word):
        word = word[:-1]
    key = _key(word)
    acronym = ACRONYMS.get(word.upper())
    if key in _LOWERCASE_CUES and word != word.upper():
        if not re.search(_LOWERCASE_CUES[key], _local_clause(passage)):
            acronym = None
    senses = SENSES.get(key, ())
    local_sense = None
    if senses:
        clause = _local_clause(passage)
        matches = [(full, gloss) for full, gloss, cue in senses if re.search(rf"\b(?:{cue})\b", clause)]
        if len(matches) == 1:
            local_sense = matches[0]
    try_acronym = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,11}", word) and (
            sum(char.isupper() for char in word) >= 2 or acronym or key in {"mvp", "prd"}))
    nearby = context or passage.local_context
    if try_acronym or re.search(r"\b(?:means?|denotes?|refers to)\b", nearby or passage.text, re.I):
        if nearby and nearby == passage.local_context and passage.local_context_offset is not None:
            item, direct = _written_definition(nearby, word, passage.local_context_offset, try_acronym)
        else:
            item, direct = _written_definition(passage.text, word, passage.selection[0], try_acronym)
            if not item and nearby and nearby != passage.text:
                item, direct = _written_definition(nearby, word, None, try_acronym)
        if item:
            expansion, kind = item
            if kind == "文中用语":
                return "文中定义", expansion, kind
            options = ([(acronym[0], acronym[1])] if acronym else []) + [(s[0], s[1]) for s in senses]
            for full, gloss in options:
                if _phrase_key(full) == _phrase_key(expansion):
                    # A paper can compare two conventions for the same acronym.
                    # A previous known expansion need not apply to this occurrence.
                    if not direct and local_sense and full != local_sense[0]:
                        return "术语参考", _format_sense(*local_sense), "缩写"
                    return "文中定义", _format_sense(expansion, gloss), "缩写"
            return "文中定义", expansion, "缩写"
    if senses:
        kind = "名称" if key == "codex" else "缩写"
        if local_sense:
            return "术语参考", _format_sense(*local_sense), kind
        return "多义参考", MULTIPLE[key], kind
    if acronym:
        return "术语参考", _format_sense(*acronym), "缩写"
    if key in CONTEXT_NAMES:
        cue, kind, gloss = CONTEXT_NAMES[key]
        if re.search(rf"\b(?:{cue})\b", _local_clause(passage)):
            return "术语参考", gloss, kind
    if re.fullmatch(r"ciallo{2,6}", key):
        key = "ciallo"
    name = NAMES.get(key)
    if name:
        return "术语参考", name[1], name[0]
    return None
