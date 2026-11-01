#!/usr/bin/env python3
"""Dedupe data/hits.jsonl and split it into verification batches.

Writes data/batches/<kind>_NNN.json (lists of hits with ids) and prints counts.
Usage: prep_batches.py [--per-batch 60]
"""
import csv, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
per = int(sys.argv[sys.argv.index("--per-batch") + 1]) if "--per-batch" in sys.argv else 60
# documentaries that recite history; off-scope
BLOCK = ["shoah", "the-act-of-killing", "night-and-fog"]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    tags = {}
    for r in csv.DictReader(open(ROOT / "data/titles_letterboxd.csv")):
        tags.setdefault(norm(r["title"]), r["tag"])
    # the user's own shows rank like watched films
    tv_tags = {norm(r["title"]): "watched" for r in csv.DictReader(open(ROOT / "data/titles_tv_user.csv"))}
    # hits already checked in an earlier round are skipped
    done = set()
    vf = ROOT / "data/verified.jsonl"
    if vf.exists():
        for line in open(vf):
            v = json.loads(line)
            done.add((v["file"], v["month"], v["day"]))
    by_file = defaultdict(list)
    for line in open(ROOT / "data/hits.jsonl"):
        h = json.loads(line)
        if (h["file"], h["month"], h["day"]) not in done:
            by_file[h["file"]].append(h)
    rows = []
    for f, hs in by_file.items():
        if any(b in f for b in BLOCK):
            continue
        # one hit per (title, date), preferring the mention that states a year
        best = {}
        for h in hs:
            k = (h["month"], h["day"])
            if k not in best or (h["year"] and not best[k]["year"]):
                best[k] = {**h, "mentions": best.get(k, {}).get("mentions", 0) + 1}
            else:
                best[k]["mentions"] += 1
        rows.extend(best.values())
    for i, h in enumerate(rows):
        h["id"] = i
        title = re.sub(r"\s*\(\d{4}\)$", "", h["source"])
        if h["kind"] == "movie":
            h["tag"] = tags.get(norm(title), "list")
        else:
            h["tag"] = tv_tags.get(norm(re.sub(r"\s+s\d+e\d+$", "", h["source"])), "list")
    out = ROOT / "data/batches"
    out.mkdir(exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    (ROOT / "data/hits_dedup.jsonl").write_text("".join(json.dumps(h) + "\n" for h in rows))
    # batches keep a title's hits together; watched/watchlist films first
    order = {"watched": 0, "watchlist": 1, "list": 2}
    groups = defaultdict(list)
    for h in rows:
        groups[(h["kind"], h["file"].rsplit("/", 1)[0] if h["kind"] == "tv" else h["file"])].append(h)
    keys = sorted(groups, key=lambda k: (k[0] != "movie", min(order[h["tag"]] for h in groups[k])))
    n, cur, kind = 0, [], None
    for k in keys:
        g = groups[k]
        for chunk in [g[i:i + per] for i in range(0, len(g), per)]:
            if cur and (len(cur) + len(chunk) > per or k[0] != kind):
                (out / f"{kind}_{n:03d}.json").write_text(json.dumps(cur))
                n, cur = n + 1, []
            kind = k[0]
            cur.extend(chunk)
    if cur:
        (out / f"{kind}_{n:03d}.json").write_text(json.dumps(cur))
    print(len(rows), "hits after dedupe;", n + 1, "batches;",
          sum(h["type"] == "date" for h in rows), "explicit dates;",
          sum(h["type"] == "holiday" for h in rows), "holiday names")


if __name__ == "__main__":
    main()
