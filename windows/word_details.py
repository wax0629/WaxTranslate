"""Infer the selected English word's part of speech with the offline NLTK model."""
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
from zipfile import BadZipFile, ZipFile

from install_model import POS_ARCHIVE, POS_PACKAGE, POS_SHA


TAGS = {
    "CC": "并列连词", "CD": "数词", "DT": "限定词", "PDT": "限定词", "WDT": "限定词",
    "EX": "存在句引导词", "MD": "情态动词", "PRP": "代词", "PRP$": "物主限定词",
    "WP": "代词", "WP$": "物主限定词", "RP": "小品词", "UH": "感叹词", "WRB": "副词",
    "JJ": "形容词", "JJR": "形容词", "JJS": "形容词",
    "NN": "名词", "NNS": "名词", "NNP": "专有名词", "NNPS": "专有名词",
    "RB": "副词", "RBR": "副词", "RBS": "副词",
    "VB": "动词", "VBD": "动词", "VBG": "动词", "VBN": "动词", "VBP": "动词", "VBZ": "动词",
}


@lru_cache(maxsize=1)
def _model():
    bundled = Path(__file__).resolve().parents[1] / "models" / POS_ARCHIVE.name
    path = bundled if bundled.is_file() else POS_ARCHIVE
    try:
        with path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != POS_SHA:
                return None
            with ZipFile(source) as archive:
                stem = f"{POS_PACKAGE}/{POS_PACKAGE}."
                weights = json.loads(archive.read(stem + "weights.json"))
                dictionary = json.loads(archive.read(stem + "tagdict.json"))
                return weights, dictionary
    except (OSError, BadZipFile):
        return None


def _token_spans(text):
    # The model was trained with separate Penn Treebank clitics. Use spans
    # in the original OCR text, including for repeated words and slash pairs.
    for match in re.finditer(r"\w+(?:[-']\w+)*|[^\w\s]", text):
        clitic = re.search(r"(?:n't|'(?:s|m|d|re|ll|ve))$", match.group(), re.I)
        if clitic and clitic.start():
            split = match.start() + clitic.start()
            yield match.start(), split
            yield split, match.end()
        else:
            yield match.span()


def _normalized(word):
    if "-" in word[1:]:
        return "!HYPHEN"
    if word.isdigit() and len(word) == 4:
        return "!YEAR"
    if word[0].isdigit():
        return "!DIGITS"
    return word.lower()


def _predict(word, index, context, previous, earlier, weights):
    # Feature names, including "i tag+i-2 tag", are model identifiers.
    # Compatible with NLTK's English averaged perceptron. See licenses/english-pos.txt.
    features = (
        "bias", "i suffix " + word[-3:], "i pref1 " + word[0],
        "i-1 tag " + previous, "i-2 tag " + earlier, f"i tag+i-2 tag {previous} {earlier}",
        "i word " + context[index], f"i-1 tag+i word {previous} {context[index]}",
        "i-1 word " + context[index - 1], "i-1 suffix " + context[index - 1][-3:],
        "i-2 word " + context[index - 2], "i+1 word " + context[index + 1],
        "i+1 suffix " + context[index + 1][-3:], "i+2 word " + context[index + 2],
    )
    scores = defaultdict(float)
    for feature in features:
        for tag, weight in weights.get(feature, {}).items():
            scores[tag] += weight
    best = max(scores, key=lambda t: (scores[t], t))
    # Different inflections of the same part of speech do not compete in the UI.
    family = TAGS.get(best, best)
    alternative = max(score for t, score in scores.items() if TAGS.get(t, t) != family)
    return best, scores[best] - alternative


def _label(tag, token):
    if tag == "IN":
        # Penn IN groups both uses; don't invent a distinction for ambiguous words.
        if token.lower() in {"if", "although", "though", "because", "unless", "whereas", "whether"}:
            return "从属连词"
        if token.lower() in {"after", "as", "before", "for", "like", "since", "than", "that", "till", "until"}:
            return "介词 / 连词"
        return "介词"
    if tag == "TO":
        return "介词 / 不定式标记"
    return TAGS.get(tag, "")


def part_of_speech(passage):
    """Return a Chinese label, or an empty string when the occurrence is unclear."""
    if not passage.selection or not re.fullmatch(r"[A-Za-z]+(?:-[A-Za-z]+)*", passage.word):
        return ""
    text = passage.text.replace("’", "'")
    selection = passage.selection
    # A slash-separated alternative occupies one grammatical slot. Score the
    # chosen side in that slot, retaining the occurrence from the OCR range.
    for group in re.finditer(r"[A-Za-z-]+(?:/[A-Za-z-]+)+", text):
        if group.start() <= selection[0] and selection[1] <= group.end():
            text = text[:group.start()] + passage.word + text[group.end():]
            selection = (group.start(), group.start() + len(passage.word))
            break
    spans = list(_token_spans(text))
    if selection not in spans:
        return ""
    model = _model()
    if model is None:
        return ""
    weights, dictionary = model
    tokens = [text[start:end] for start, end in spans]
    selected = spans.index(selection)
    if not any(i != selected and token[0].isalnum() for i, token in enumerate(tokens)):
        label = _label(dictionary.get(passage.word), passage.word)
        return f"{label}（参考）" if label else ""
    # A strong syntactic prior alone can label OCR noise and novel terminology
    # with unwarranted precision. Require a lexical trace in the trained model.
    word = passage.word.lower()
    if passage.word not in dictionary and not any(
        f"{feature} {word}" in weights for feature in ("i word", "i-1 word", "i+1 word", "i-2 word", "i+2 word")
    ):
        return ""
    previous, earlier = "-START-", "-START2-"
    context = [previous, earlier] + [_normalized(token) for token in tokens] + ["-END-", "-END2-"]
    tags = []
    for i, token in enumerate(tokens):
        tag = dictionary.get(token)
        if tag is None:
            tag, margin = _predict(token, i + 2, context, previous, earlier, weights)
            # The score gap is a confidence heuristic, not a probability.
            if i == selected and margin < 1.5:
                return ""
        elif tag == "NN" and i and (previous == "MD" or tokens[i - 1].lower() in {"i", "we", "you", "they"}):
            # The fast dictionary retains only the dominant training tag. In
            # a finite verb slot, allow a strongly supported verbal use of a
            # common noun ("they bank on it", "we will table the proposal").
            verbal, margin = _predict(token, i + 2, context, previous, earlier, weights)
            if verbal in {"VB", "VBP"} and margin >= 2.5:
                tag = verbal
        tags.append(tag)
        earlier, previous = previous, tag
    tag = tags[selected]
    if tag == "TO":
        for following in tags[selected + 1:]:
            if following in {"RB", "RBR", "RBS"}:
                continue  # e.g. "to accurately measure"
            if following == "VB":
                return "不定式标记"
            if following in {"DT", "PRP", "PRP$", "VBG", "NN", "NNS", "NNP", "NNPS"}:
                return "介词"
            break
    return _label(tag, tokens[selected])
