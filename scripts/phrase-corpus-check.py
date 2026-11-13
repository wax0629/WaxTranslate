"""Evaluate reading spans on pinned English UD corpora without shipping their text."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "windows"))
from terminology import phrase_at

# (dataset, pairs per genre). EWT development rounds remain reproducible.
CORPORA = {
    "0612e45914359e4b36d187ef2bfeaf66fc8933210925be985c5fbf6a9e311036": ("EWT", 8),
    "99deb5746618d8ab83e5cafc2d07851e76389b2c8babf5ad9e5ef176a4619114": ("GUM", 3),
}
WORD = re.compile(r"[A-Za-z]+")


def spans(text, word):
    return [m.span() for m in re.finditer(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("samples", type=Path, help="Ignored local JSON for the native reader check")
    parser.add_argument("--round", type=int, choices=(1, 2), default=1,
                        help="EWT round 2 takes the next eight disjoint pairs per genre")
    args = parser.parse_args()
    data = args.corpus.read_bytes()
    corpus = CORPORA.get(hashlib.sha256(data).hexdigest())
    if corpus is None:
        parser.error("Use UD English EWT 4dc8e10 or GUM 34d01cb (r2.15 test split)")
    name, count = corpus
    if name == "GUM" and args.round != 1:
        parser.error("GUM has one preselected evaluation round")
    cases, counts = defaultdict(list), Counter()
    triggers = set()
    for block in data.decode().strip().split("\n\n"):
        lines = block.splitlines()
        meta = dict(line[2:].split(" = ", 1) for line in lines if line.startswith("# ") and " = " in line)
        text, sentence_id = meta["text"], meta["sent_id"]
        genre = sentence_id.split("_")[1] if name == "GUM" else sentence_id.split("-", 1)[0]
        counts["sentences"] += 1
        for token in WORD.finditer(text):
            counts["token_hits"] += 1
            found = phrase_at(text, token.span(), "sentence")
            if found:
                triggers.add((sentence_id, found[0], found[1]["translation"]))
        rows = {int(row[0]): row for line in lines if line and line[0].isdigit()
                and (row := line.split("\t"))[0].isdigit()}
        for index, row in rows.items():
            head_id = int(row[6])
            if row[7] != "compound" or head_id != index + 1 or row[3] != "NOUN" or rows[head_id][3] != "NOUN":
                continue
            left, head = row[1], rows[head_id][1]
            if not WORD.fullmatch(left) or not WORD.fullmatch(head):
                continue
            phrase = left + " " + head
            heads, pairs = spans(text, head), spans(text, phrase)
            if len(heads) != 1 or len(pairs) != 1:
                continue
            counts["eligible_pairs"] += 1
            cases[genre].append(dict(id=sentence_id + "/" + str(index), text=text, word=head, phrase=phrase))
    samples = []
    for genre, pairs in sorted(cases.items()):
        ordered = sorted(pairs, key=lambda pair: hashlib.sha256(pair["id"].encode()).digest())
        start = (args.round - 1) * count
        batch = ordered[start:start + count]
        samples.extend(batch)
        print(f"{genre}: {len(pairs)} eligible, {len(batch)} sampled")
    args.samples.write_text(json.dumps(samples, ensure_ascii=False))
    print(dict(counts), "unique glossary activations", len(triggers), "sampled", len(samples))
    for sentence_id, selection, translation in sorted(triggers):
        print(sentence_id, selection, translation)


if __name__ == "__main__":
    main()
