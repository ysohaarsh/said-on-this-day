#!/usr/bin/env python3
"""Append a verification round's agent results to data/verified.jsonl.

Usage: merge_verified.py <workflow journal.jsonl> <hits snapshot.jsonl>
Joins each agent result to its hit by id; skips (file, month, day) already merged.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP = ("kind", "source", "file", "month", "day", "year", "match", "tag", "mentions")


def main():
    journal, snapshot = sys.argv[1], sys.argv[2]
    hits = {h["id"]: h for h in map(json.loads, open(snapshot))}
    out = ROOT / "data/verified.jsonl"
    seen = {(v["file"], v["month"], v["day"]) for v in map(json.loads, open(out))} if out.exists() else set()
    added = 0
    with out.open("a") as f:
        for line in open(journal):
            e = json.loads(line)
            if e.get("type") != "result":
                continue
            v = e.get("value") or e.get("result") or {}
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except ValueError:
                    continue
            for x in v.get("hits") or []:
                h = hits.get(x["id"])
                if not h or (h["file"], h["month"], h["day"]) in seen:
                    continue
                seen.add((h["file"], h["month"], h["day"]))
                f.write(json.dumps({**{k: h.get(k) for k in KEEP}, **x}) + "\n")
                added += 1
    print(added, "added;", len(seen), "total verified")


if __name__ == "__main__":
    main()
