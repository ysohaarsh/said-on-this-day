#!/usr/bin/env python3
"""Per-day coverage of verified lines. Writes data/empty_days.json and prints a summary."""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAXDAY = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
TAG_RANK = {"watched": 0, "watchlist": 1, "list": 2}


def score(v):
    # memorable first, then your own titles, then movies over TV, then a known speaker
    return (-v["memorable"], TAG_RANK.get(v.get("tag"), 2), v["kind"] != "movie", v["speaker"] == "unknown")


def main():
    days = defaultdict(list)
    for line in open(ROOT / "data/verified.jsonl"):
        v = json.loads(line)
        if v["keep"]:
            days[(v["month"], v["day"])].append(v)
    empty, thin = [], []
    for m in range(12):
        for d in range(1, MAXDAY[m] + 1):
            vs = days.get((m + 1, d), [])
            if not vs:
                empty.append([m + 1, d])
            elif max(v["memorable"] for v in vs) <= 2:
                thin.append([m + 1, d])
    (ROOT / "data/empty_days.json").write_text(json.dumps({"empty": empty, "weak": thin}))
    print(f"covered {366 - len(empty)}/366; empty {len(empty)}; weak (best line memorable<=2) {len(thin)}")
    print("empty:", " ".join(f"{MONTHS[m - 1]}{d}" for m, d in empty))


if __name__ == "__main__":
    main()
