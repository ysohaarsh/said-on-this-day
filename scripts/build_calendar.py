#!/usr/bin/env python3
"""Build calendar/said-on-this-day.html from data/verified.jsonl (+ data/gapfill.jsonl if present)."""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    rows = []
    for src in ("data/verified.jsonl", "data/gapfill.jsonl"):
        p = ROOT / src
        if p.exists():
            rows += [json.loads(l) for l in open(p)]
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
    my_shows = {norm(l.split(",")[0]) for l in open(ROOT / "data/titles_tv_user.csv").read().splitlines()[1:]}
    sp_path = ROOT / "data/speakers.json"
    speakers = json.loads(sp_path.read_text()) if sp_path.exists() else {}
    out = []
    for v in rows:
        if not v.get("keep"):
            continue
        v.update(speakers.get(f"{v['file']}|{v['month']}|{v['day']}", {}))
        title = re.sub(r"\s+s\d+e\d+$", "", v["source"]).strip()
        if v["kind"] == "tv":
            v["tag"] = "watched" if norm(title) in my_shows else "list"
        ep = re.search(r"s(\d+)e(\d+)$", v["source"])
        out.append({
            "m": v["month"], "d": v["day"], "t": title, "k": v["kind"], "tag": v.get("tag", "list"),
            "ep": f"S{int(ep.group(1))}E{int(ep.group(2))}" if ep else "",
            "sp": v["speaker"] if v.get("speaker_confidence") != "low" else "unknown",
            "q": v["quote"], "sc": v.get("scene", ""), "mem": v["memorable"], "match": v.get("match", ""),
        })
    plain = json.dumps(out, separators=(",", ":"))
    (ROOT / "data/calendar.json").write_text(plain)
    # copy for the daily notifier: launchd jobs can't read ~/Desktop
    share = Path.home() / ".local/share/today-in-movies"
    share.mkdir(parents=True, exist_ok=True)
    (share / "calendar.json").write_text(plain)
    data = plain.replace("</", "<\\/")
    html = (ROOT / "calendar/template.html").read_text().replace("__DATA__", data)
    (ROOT / "calendar/said-on-this-day.html").write_text(html)
    print(len(out), "lines;", len({(o["m"], o["d"]) for o in out}), "days;", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
