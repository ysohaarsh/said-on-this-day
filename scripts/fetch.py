#!/usr/bin/env python3
"""Download transcripts from springfieldspringfield.co.uk.

Usage: fetch.py titles.csv [--workers 6] [--max-episodes 400]
titles.csv columns: title,year,kind (movie|tv)
Writes transcripts/movies/<slug>.txt and transcripts/tv/<slug>/<ep>.txt,
caches slug lookups in data/slugs.json, logs to data/fetch_log.csv.
"""
import csv, html, json, re, sys, threading, time, unicodedata, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.springfieldspringfield.co.uk/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
SLUGS = ROOT / "data/slugs.json"
LOG = ROOT / "data/fetch_log.csv"
lock = threading.Lock()
slugs = json.loads(SLUGS.read_text()) if SLUGS.exists() else {}
# hand-checked slugs for titles the site search can't find
OVERRIDES = ROOT / "data/slug_overrides.json"
slugs.update(json.loads(OVERRIDES.read_text()) if OVERRIDES.exists() else {})


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(0.25)
                return r.read().decode("utf-8", "replace")
        except Exception:
            time.sleep(2 * (i + 1))
    return None


ALIASES = {"sorcerer's": "philosopher's", "pajamas": "pyjamas", "8½": "8 1/2", "wall·e": "wall-e", "m*a*s*h": "mash"}
ROMAN = {"ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "two": "2", "three": "3"}


def norm(s):
    s = s.lower()
    for a, b in ALIASES.items():
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.replace("&", "and")
    s = re.sub(r"^(the|a|an) ", "", s)
    s = re.sub(r"\b(ii|iii|iv|vi|v|two|three)\b", lambda m: ROMAN[m.group(1)], s)
    return re.sub(r"[^a-z0-9]", "", s)


def transcript(page):
    m = re.search(r'class="scrolling-script-container">(.*?)</div>', page or "", re.S)
    if not m:
        return None
    t = re.sub(r"<br\s*/?>", "\n", m.group(1))
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", t).strip()


def label_names(label):
    """'Dark Knight, The (Batman: The Dark Knight) (2008)' -> ({'darkknight', 'batmandarkknight'}, 2008)"""
    label = html.unescape(label).strip()
    m = re.search(r"\((\d{4})\)\s*$", label)
    y = int(m.group(1)) if m else None
    label = label[:m.start()].strip() if m else label
    parts = [p.strip() for p in re.findall(r"\(([^)]*)\)", label)] + [re.sub(r"\([^)]*\)", "", label).strip()]
    names = set()
    for p in parts:
        p = re.sub(r",\s*(The|A|An)$", "", p)
        names.add(norm(p))
    return names, y


def search_variants(title):
    """Site search misses leading articles and digits-for-letters; try a few forms."""
    v = [title, re.sub(r"^(The|A|An)\s+", "", title)]
    v.append(re.split(r"[:\-–]", v[1])[0])
    return [x.strip() for x in dict.fromkeys(v) if x.strip()]


def resolve(title, year, kind):
    key = f"{kind}|{title}|{year}"
    if slugs.get(key):
        return slugs[key]
    want = norm(title)
    slug = None
    for q in search_variants(title):
        q = urllib.parse.quote_plus(q)
        if kind == "movie":
            page = get(f"{BASE}movie_scripts.php?search={q}") or ""
            hits = re.findall(r'movie_script\.php\?movie=([^"]+)"[^>]*>([^<]*)', page)
        else:
            page = get(f"{BASE}tv_show_episode_scripts.php?search={q}") or ""
            hits = re.findall(r'episode_scripts\.php\?tv-show=([^"]+)"[^>]*>([^<]*)', page)
        # score: exact name 3, long containment 2; then closest year
        scored = []
        for s, l in hits:
            names, y = label_names(l)
            sc = 3 if want in names else 2 if len(want) >= 6 and any(want in n or (len(n) >= 6 and n in want) for n in names) else 0
            if sc:
                scored.append((sc, s, y))
        if year and scored:
            yr = int(year)
            ok = [c for c in scored if c[2] and abs(c[2] - yr) <= 1 and (c[0] == 3 or c[2] == yr)]
            if kind == "tv" and not ok:
                ok = [c for c in scored if not c[2] and c[0] == 3]
            ok.sort(key=lambda c: (-c[0], abs(c[2] - yr) if c[2] else 9))
            slug = ok[0][1] if ok else None
        elif len([c for c in scored if c[0] == 3]) == 1:
            slug = [c for c in scored if c[0] == 3][0][1]
        if slug:
            break
    with lock:
        slugs[key] = slug
    return slug


def log(row):
    with lock:
        new = not LOG.exists()
        with LOG.open("a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["title", "year", "kind", "slug", "status", "files"])
            w.writerow(row)


def do_movie(title, year):
    slug = resolve(title, year, "movie")
    if not slug:
        return log([title, year, "movie", "", "no_match", 0])
    out = ROOT / f"transcripts/movies/{slug}.txt"
    if out.exists():
        return log([title, year, "movie", slug, "cached", 1])
    t = transcript(get(f"{BASE}movie_script.php?movie={slug}"))
    if not t or len(t) < 3000:
        return log([title, year, "movie", slug, "empty", 0])
    out.write_text(f"# {title} ({year})\n{t}")
    log([title, year, "movie", slug, "ok", 1])


def do_tv(title, year, max_eps, pool):
    slug = resolve(title, year, "tv")
    if not slug:
        return log([title, year, "tv", "", "no_match", 0])
    d = ROOT / f"transcripts/tv/{slug}"
    d.mkdir(parents=True, exist_ok=True)
    page = get(f"{BASE}episode_scripts.php?tv-show={slug}") or ""
    eps = list(dict.fromkeys(re.findall(r"episode=(s\d+e\d+)", page)))[:max_eps]

    def one(ep):
        f = d / f"{ep}.txt"
        if f.exists():
            return 1
        t = transcript(get(f"{BASE}view_episode_scripts.php?tv-show={slug}&episode={ep}"))
        if t:
            f.write_text(f"# {title} {ep}\n{t}")
            return 1
        return 0

    n = sum(pool.map(one, eps))
    log([title, year, "tv", slug, "ok" if n else "empty", n])


def main():
    args = sys.argv[1:]
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 6
    max_eps = int(args[args.index("--max-episodes") + 1]) if "--max-episodes" in args else 400
    rows = list(csv.DictReader(open(args[0])))
    (ROOT / "transcripts/movies").mkdir(parents=True, exist_ok=True)
    ep_pool = ThreadPoolExecutor(workers)
    done = 0
    try:
        with ThreadPoolExecutor(workers) as pool:
            futs = []
            for r in rows:
                y = (r.get("year") or "").strip()
                if r["kind"] == "movie":
                    futs.append(pool.submit(do_movie, r["title"], y))
            for f in futs:
                f.result()
                done += 1
                if done % 50 == 0:
                    print(f"movies {done}/{len(futs)}", flush=True)
                    SLUGS.write_text(json.dumps(slugs, indent=0))
        for r in rows:
            if r["kind"] == "tv":
                do_tv(r["title"], (r.get("year") or "").strip(), max_eps, ep_pool)
                print(f"tv done: {r['title']}", flush=True)
                SLUGS.write_text(json.dumps(slugs, indent=0))
    finally:
        SLUGS.write_text(json.dumps(slugs, indent=0))
        ep_pool.shutdown()


if __name__ == "__main__":
    main()
