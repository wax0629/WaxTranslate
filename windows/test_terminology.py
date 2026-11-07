import re
import unittest

from reader import Passage, sentence_at
from terminology import resolve_term


def lookup(text, word, occurrence=0):
    start = [match.start() for match in re.finditer(re.escape(word), text)][occurrence]
    return resolve_term(sentence_at(text, start, start + len(word)))


class TermChecks(unittest.TestCase):
    def test_names_and_spelling(self):
        for text, word, meaning in (
                ("Ask chatgpt.", "chatgpt", "对话"),
                ("Check ChatGPT’s response.", "ChatGPT’s", "OpenAI"),
                ("Call these APIs first.", "APIs", "application programming interface"),
                ("The JWT signed by the server expires soon.", "JWT", "令牌"),
                ("The tokenizer uses BPE.", "BPE", "字节对编码"),
                ("Read about GPT-4o.", "GPT-4o", "多模态"),
                ("Read about GPT‑4o.", "GPT‑4o", "多模态"),
                ("Use Node.js, .NET, C# or C++.", "Node.js", "JavaScript"),
                ("Use Node.js, .NET, C# or C++.", ".NET", "开发平台"),
                ("Use Node.js, .NET, C# or C++.", "C++", "编程语言"),
                ("Use Node.js, .NET, C# or C++.", "C#", "sharp"),
                ("Ciallo～(∠・ω< )⌒☆", "Ciallo", "招呼"),
                ("Ciallooo!", "Ciallooo", "招呼")):
            with self.subTest(word=word):
                self.assertIn(meaning, lookup(text, word)[1])

    def test_domain_cues_and_repeated_terms(self):
        text = "The startup shipped its MVP, whereas the season MVP scored 40 points."
        self.assertIn("minimum viable product", lookup(text, "MVP", 0)[1])
        self.assertIn("most valuable player", lookup(text, "MVP", 1)[1])
        text = "They built a minimum viable product (MVP). She was named MVP after the game."
        self.assertIn("minimum viable product", lookup(text, "MVP", 0)[1])
        self.assertIn("most valuable player", lookup(text, "MVP", 1)[1])
        for text, word, meaning in (
                ("MVP separates the view from the presenter.", "MVP", "表示器"),
                ("She was named MVP after the game.", "MVP", "最有价值球员"),
                ("We built an MVP for a multiplayer game.", "MVP", "最小可行产品"),
                ("The echocardiogram revealed MVP.", "MVP", "二尖瓣脱垂"),
                ("Our Microsoft MVP spoke today.", "MVP", "微软"),
                ("The rag pipeline uses documents from a vector database.", "rag", "检索增强"),
                ("This laptop has 16 GB of ram.", "ram", "内存"),
                ("That rest API serves profiles.", "rest", "架构风格"),
                ("They used Codex to fix a bug.", "Codex", "编程助手"),
                ("A scribe illuminated the medieval codex.", "codex", "册页"),
                ("Food safety follows the Codex Alimentarius.", "Codex", "食品法典"),
                ("Write the prd for the next feature.", "prd", "产品需求文档"),
                ("Urbanization in the PRD near Guangzhou has accelerated.", "PRD", "珠江三角洲")):
            with self.subTest(text=text):
                self.assertIn(meaning, lookup(text, word)[1])
        for term in ("MVP", "codex", "prd"):
            self.assertEqual(lookup(term, term)[0], "多义参考")
        self.assertEqual(lookup("The startup asked the NBA about MVP.", "MVP")[0], "多义参考")

    def test_explicit_definitions_and_wrapped_lines(self):
        for text, word, expansion in (
                ("We use a novel Data Flow Protocol (DFP). The DFP was fast.", "DFP", "Data Flow Protocol"),
                ("The DFP (data flow protocol) stalled. Inspect DFP.", "DFP", "data flow protocol"),
                ("DFP stands for data flow protocol in this paper. Use DFP.", "DFP", "data flow protocol"),
                ("DFP is short for data flow protocol. Try DFP.", "DFP", "data flow protocol"),
                ("Here we use data\nflow protocol （DFP）. DFP is new.", "DFP", "data flow protocol"),
                ("The Point of Contact (PoC) joined. Ask the PoC.", "PoC", "Point of Contact"),
                ("Try an end-to-end network (EEN). Install the EEN.", "EEN", "end-to-end network"),
                ("We use quantum packet detectors (QPDs). Check two QPDs.", "QPDs", "quantum packet detectors"),
                ("Measure the mean volume pressure (MVP). Then record MVP.", "MVP", "mean volume pressure")):
            with self.subTest(text=text):
                self.assertEqual(lookup(text, word, -1), ("文中定义", expansion, "缩写"))
        title, meaning, _ = lookup("Write a Product Requirements Document (PRD).", "PRD")
        self.assertEqual(title, "文中定义")
        self.assertIn("产品需求文档", meaning)
        self.assertIn("Product Requirements Document", meaning)

    def test_changed_definition_and_missing_position(self):
        text = ("Quantum Packet Delay (QPD). We measured QPD.\n\n"
                "Queued Parcel Delivery (QPD). We measured QPD.")
        for occurrence, expansion in enumerate(("Quantum Packet Delay", "Quantum Packet Delay",
                                                 "Queued Parcel Delivery", "Queued Parcel Delivery")):
            self.assertEqual(lookup(text, "QPD", occurrence)[1], expansion)
        self.assertIsNone(resolve_term(Passage("QPD", (0, 3)), text))
        self.assertEqual(resolve_term(Passage("QPD", (0, 3)), "Quantum Packet Delay (QPD)")[1],
                         "Quantum Packet Delay")

    def test_ordinary_words_and_unverified_acronyms(self):
        for text, word in (
                ("Let us rest in the shade.", "rest"),
                ("They documented the rest of the API.", "rest"),
                ("The ram stood near the hill.", "ram"),
                ("The rag was wet.", "rag"),
                ("Write ciallopro.", "ciallopro"),
                ("A barcode {QPD} is printed here.", "QPD"),
                ("The QPD (see appendix B) changed.", "QPD"),
                ("The old window closed (QPD).", "QPD"),
                ("The old chapter ends with quantum\n\nPacket delay (QPD) begins this one.", "QPD"),
                ("This QPD stands for yellow paper labels.", "QPD"),
                ("Quasar Project Document (XQPD) is not QPD.", "QPD"),
                ("The QPD driver is ready.", "QPD")):
            with self.subTest(text=text):
                self.assertIsNone(lookup(text, word, -1))
        self.assertIsNone(resolve_term(Passage("ChatGPT")))


if __name__ == "__main__":
    unittest.main()
