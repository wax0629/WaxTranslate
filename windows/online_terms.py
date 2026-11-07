"""Optional word-only Wikidata lookup. Caller runs this off the UI thread."""
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def search_entities(word):
    if len(word) > 96 or not re.fullmatch(r"[\w.+#’'\-]+", word):
        return []
    query = urlencode(dict(action="wbsearchentities", search=word, language="en",
                           uselang="zh-hans", type="item", limit=8, format="json"))
    request = Request("https://www.wikidata.org/w/api.php?" + query, headers={
        "User-Agent": "WaxTranslate/1.0 (https://github.com/wax0629/WaxTranslate)",
        "Accept": "application/json",
    })
    with urlopen(request, timeout=5) as response:
        data = json.loads(response.read(256 * 1024))
    if not isinstance(data, dict) or not isinstance(data.get("search"), list) or "error" in data:
        raise ValueError("Wikidata 返回了无法读取的结果")
    matches = []
    for item in data["search"]:
        identity = item["id"]
        matched = item.get("match", {}).get("text", "")
        description = " ".join(item.get("description", "").split())
        if (matched.casefold() != word.casefold() or not re.fullmatch(r"Q[1-9]\d*", identity)
                or not description or description in {desc for _, desc, _ in matches}):
            continue
        language = item.get("display", {}).get("description", {}).get("language", "")
        matches.append((identity, description[:350], language))
        if len(matches) == 3:
            break
    return matches
