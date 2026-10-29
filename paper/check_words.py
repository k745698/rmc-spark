"""Per-section word counts against the planning PDF (26FSPDSCPMID4098) ranges.

Counts exactly like build_paper.py: body paragraphs + figure captions, citations resolved to [n],
tables and equations excluded. Run:  python check_words.py
"""
import json
import os
import sys
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_paper as b  # noqa: E402

# (low, high) from the planning PDF; key 0 = Executive Summary + Abstract (keywords listed separately)
RANGES = {0: (450, 750), "kw": (20, 40), 1: (800, 1200), 2: (400, 700), 3: (1500, 2500), 4: (600, 1000),
          5: (1000, 1500), 6: (1000, 1500), 7: (1200, 1800), 8: (1000, 1500), 9: (1200, 1800),
          10: (1000, 1500), 11: (1000, 1500), 12: (800, 1200), 13: (700, 1200), 14: (500, 800),
          15: (1200, 2000), 16: (800, 1200), 17: (700, 1000), 18: (800, 1500), 19: (500, 1000),
          20: (600, 1000), 21: (600, 1200), 22: (500, 800), "appendix": (500, 2000)}


def counts():
    refs = {r["key"]: r for r in json.load(open(os.path.join(HERE, "refs", "refs_keyed.json"), encoding="utf8"))}
    blocks = b.parse_sources()
    nums = b.Numbers(blocks, refs)
    out, titles = OrderedDict(), {0: "Executive Summary and Abstract", "kw": "Keywords", "appendix": "Appendix"}
    abstract = next(x["text"] for x in blocks if x["t"] == "abstract")
    out["kw"] = b.word_count(next(x["text"] for x in blocks if x["t"] == "keywords"))
    out[0] = b.word_count(abstract)
    key, sec = 0, 0
    for x in blocks:
        t = x["t"]
        if t == "section":
            sec += 1
            key = sec
            titles[key] = x["text"]
        elif t == "unnumbered":
            key = {"Executive Summary": 0, "Appendix": "appendix"}.get(x["text"], "other")
        elif t == "para":
            out[key] = out.get(key, 0) + b.word_count(nums.resolve(x["text"]))
        elif t == "figure":
            out[key] = out.get(key, 0) + b.word_count(nums.resolve(x["caption"]))
    return out, titles


# The PDF also caps the whole paper at 15,000 words, which is below the sum of its own section minimums
# (about 18,900). To honour the cap, every section is held at the same share of its planned minimum.
TOTAL_MAX = 15000
SHARE = 0.76


def budget(k):
    lo = RANGES[k][0]
    if k == "kw":
        return RANGES[k]
    if k == "appendix":
        return (150, 300)            # optional section: kept short, the recovery-rules table carries it
    t = SHARE * lo
    return (round(t * 0.95), round(t * 1.05))


if __name__ == "__main__":
    out, titles = counts()
    bad = 0
    for k in RANGES:
        n = out.get(k, 0)
        lo, hi = budget(k)
        ok = lo <= n <= hi
        bad += not ok
        print(f"{'OK ' if ok else 'OUT'} {str(k):>8}  {n:5d}  budget [{lo}-{hi}]  plan {RANGES[k]}  {titles.get(k, '')}")
    total = sum(out.values())
    print(f"total words (prose + captions + appendix + data availability): {total}  (cap {TOTAL_MAX})")
    print("all sections within budget" if not bad and total <= TOTAL_MAX else f"{bad} section(s) off budget")
