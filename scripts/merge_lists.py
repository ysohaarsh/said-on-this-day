#!/usr/bin/env python3
"""Merge lists/*.csv into data/titles_movies.csv and data/titles_tv.csv,
ranked by how many lists each title appears on. Letterboxd titles are skipped
(already fetched)."""
import csv, re, unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("&", "and")
    s = re.sub(r"^(the|a|an) ", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


def main():
    seen_lb = {norm(r["title"]) for r in csv.DictReader(open(ROOT / "data/titles_letterboxd.csv"))}
    for kind in ("movie", "tv"):
        agg = {}
        hits = defaultdict(set)
        for f in sorted((ROOT / "lists").glob(f"{kind}_*.csv")):
            for r in csv.DictReader(open(f, newline="", encoding="utf-8", errors="replace")):
                t = (r.get("title") or "").strip()
                if not t:
                    continue
                y = re.sub(r"\D", "", r.get("year") or "")[:4]
                key = norm(t)
                # same title, years far apart = different film (remakes)
                if key in agg and y and agg[key]["year"] and abs(int(agg[key]["year"]) - int(y)) > 1:
                    key = f"{key}{y}"
                agg.setdefault(key, {"title": t, "year": y, "kind": kind})
                if y and not agg[key]["year"]:
                    agg[key]["year"] = y
                hits[key].add(f.stem)
        rows = []
        for k, v in agg.items():
            if kind == "movie" and norm(v["title"]) in seen_lb:
                continue
            rows.append({**v, "lists": len(hits[k])})
        rows.sort(key=lambda r: -r["lists"])
        out = ROOT / f"data/titles_{'movies' if kind == 'movie' else 'tv'}.csv"
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["title", "year", "kind", "lists"])
            w.writeheader()
            w.writerows(rows)
        print(kind, len(rows), "unique;", sum(r["lists"] >= 3 for r in rows), "on 3+ lists")


if __name__ == "__main__":
    main()
