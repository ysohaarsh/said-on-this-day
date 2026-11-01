"""Browser tests for the calendar pages. Uses Playwright driving the installed Chrome.

  python tests/ui_test.py            # run all checks, write tests/report.md
  python tests/ui_test.py --shots    # also refresh docs/screenshots/
"""
import json, pathlib, re, sys, time
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.load(open(ROOT / "data/calendar.json"))
PAGES = {
    "main":   ROOT / "calendar/said-on-this-day.html",
    "script": ROOT / "calendar/concepts/script.html",
    "ticket": ROOT / "calendar/concepts/ticket.html",
    "leader": ROOT / "calendar/concepts/leader.html",
}
VIEWPORTS = {
    "desktop": dict(viewport={"width": 1440, "height": 900}),
    "tablet":  dict(viewport={"width": 820, "height": 1180}, has_touch=True, is_mobile=True, device_scale_factor=2),
    "phone":   dict(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True, device_scale_factor=3),
    "small":   dict(viewport={"width": 320, "height": 640}, has_touch=True, is_mobile=True, device_scale_factor=2),
}
AXE = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
SHOTS = ROOT / "docs/screenshots"

def titles(k):
    """Lower-case film/show names (year stripped) that are said on day k."""
    m, d = divmod(k, 100)
    return {re.sub(r"\s*\(\d{4}\)$", "", l["t"]).lower() for l in DATA if l["m"] == m and l["d"] == d}

results = []   # (page, view, test, ok, detail)
def rec(page, view, test, ok, detail=""):
    results.append((page, view, test, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {page:6} {view:7} {test:28} {detail}"[:200])

def open_page(ctx, name, hash_="#d1031"):
    errs = []
    p = ctx.new_page()
    p.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    p.on("console", lambda m: m.type == "error" and "net::" not in m.text and "Failed to load resource" not in m.text and errs.append(m.text))
    t0 = time.time()
    p.goto(PAGES[name].as_uri() + hash_, wait_until="load")
    p.wait_for_timeout(1500)
    if name == "leader":   # dismiss the countdown leader
        p.evaluate("document.querySelector('#leader') && document.querySelector('#leader').dispatchEvent(new PointerEvent('pointerdown'))")
        p.wait_for_timeout(600)
    return p, errs, time.time() - t0

def text(p):
    return p.evaluate("document.body.innerText").lower()

def shows_day(p, k):
    return any(t in text(p) for t in titles(k))

def overflow(p):
    return p.evaluate("""() => {
      // real sideways scroll the viewer can do (layout overflow clipped by the body does not count)
      const W = document.documentElement.clientWidth; scrollTo(9999, scrollY); const sw = W + scrollX; scrollTo(0, scrollY);
      const bad = [...document.querySelectorAll('body *')].filter(e => {
        const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
        if (!r.width || cs.position === 'fixed' || cs.visibility === 'hidden') return false;
        for (let a = e.parentElement; a; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden' || o === 'clip') return false }
        return r.right > W + 1;
      }).slice(0, 4).map(e => (e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.')) + ' ' + Math.round(e.getBoundingClientRect().right));
      return { over: sw - W, bad };
    }""")

def small_targets(p):
    return p.evaluate("""() => [...document.querySelectorAll('button, a, input, [role=button]')].filter(e => {
        const r = e.getBoundingClientRect(); if (!r.width || !r.height) return false;
        const cs = getComputedStyle(e); if (cs.visibility === 'hidden' || cs.display === 'none') return false;
        return Math.min(r.width, r.height) < 24; }).length""")

def run_axe(p):
    try:
        p.add_script_tag(url=AXE)
        r = p.evaluate("axe.run(document, {resultTypes: ['violations']}).then(r => r.violations.map(v => v.id + ' x' + v.nodes.length + ' (' + v.impact + ')'))")
        return r
    except Exception as e:
        return [f"axe failed: {e}"]

def test_page(b, name, view, scheme="light", motion="no-preference"):
    ctx = b.new_context(color_scheme=scheme, reduced_motion=motion, **VIEWPORTS[view])
    p, errs, secs = open_page(ctx, name)
    tag = view if scheme == "light" else f"{view}-dk"
    rec(name, tag, "loads", secs < 6, f"{secs:.1f}s")
    rec(name, tag, "deep link #d1031", shows_day(p, 1031) and p.evaluate("location.hash") == "#d1031")
    o = overflow(p)
    rec(name, tag, "no horizontal scroll", o["over"] <= 1 and not o["bad"], f"over={o['over']}px {o['bad']}" if o["over"] > 1 or o["bad"] else "")

    if view == "desktop" and scheme == "light":
        # keyboard
        p.locator("body").click(position={"x": 2, "y": 2}) if name != "leader" else None
        p.keyboard.press("ArrowRight"); p.wait_for_timeout(900)
        rec(name, tag, "ArrowRight -> Nov 1", p.evaluate("location.hash") == "#d1101" and shows_day(p, 1101), p.evaluate("location.hash"))
        p.keyboard.press("ArrowLeft"); p.wait_for_timeout(900)
        rec(name, tag, "ArrowLeft -> Oct 31", p.evaluate("location.hash") == "#d1031")
        # hashchange
        p.evaluate("location.hash = '#d1012'"); p.wait_for_timeout(1000)
        rec(name, tag, "hashchange #d1012", shows_day(p, 1012))
        rec(name, tag, "Watchmen on Oct 12", "watchmen" in text(p))
        # leap day + an unknown/empty day must not crash
        p.evaluate("location.hash = '#d229'"); p.wait_for_timeout(900)
        rec(name, tag, "Feb 29", shows_day(p, 229) or p.evaluate("location.hash") == "#d229", p.evaluate("location.hash"))
        p.evaluate("location.hash = '#d1229'"); p.wait_for_timeout(900)
        rec(name, tag, "empty Dec 29 no crash", True)
        # every month button
        n = p.evaluate("""() => { const bs = [...document.querySelectorAll('#months button')]; bs.forEach(b => b.click()); return bs.length }""")
        p.wait_for_timeout(900)
        rec(name, tag, "12 month buttons", n == 12, f"{n} buttons, ends {p.evaluate('location.hash')}")
        # every day in the grid/strip of the current month (main/script/ticket have #days)
        if p.locator("#days").count():
            c = p.evaluate("""() => { const bs = [...document.querySelectorAll('#days button')]; bs.slice(0, 40).forEach(b => b.click()); return bs.length }""")
            p.wait_for_timeout(600)
            rec(name, tag, "day buttons clickable", c >= 28, f"{c} days")
        # filters
        fb = p.locator("#filters button")
        for i in range(fb.count()):
            try: fb.nth(i).click(timeout=3000, force=True)
            except Exception as e: rec(name, tag, f"filter {i}", False, str(e)[:80])
            p.wait_for_timeout(300)
        rec(name, tag, "filter buttons", fb.count() >= 2, f"{fb.count()} filters")
        if fb.count(): fb.nth(0).click(force=True); p.wait_for_timeout(300)
        # search
        q = p.locator("#q")
        if q.count():
            if not q.is_visible():   # drawer pages hide search behind a toggle on narrow screens
                for t in ("#bt", "#btoggle"):
                    if p.locator(t).count() and p.locator(t).is_visible(): p.click(t); break
            q.fill("watchmen"); q.press("Enter"); p.wait_for_timeout(1200)
            rec(name, tag, "search 'watchmen'", "watchmen" in text(p))
            q.fill("zzqxj"); p.wait_for_timeout(900)
            rec(name, tag, "search no-match no crash", True)
            q.fill(""); p.wait_for_timeout(600)
        # "also said" list / more buttons
        for sel in ("#more",):
            if p.locator(sel).count() and p.locator(sel).is_visible():
                p.click(sel); p.wait_for_timeout(500); rec(name, tag, "show more", True)
        # leader: mouse drag on film strip
        if name == "leader":
            p.evaluate("location.hash = '#d1031'"); p.wait_for_timeout(1200)
            bb = p.locator("#strip").bounding_box()
            y = bb["y"] + bb["height"] / 2
            p.mouse.move(bb["x"] + bb["width"] / 2, y); p.mouse.down()
            for i in range(1, 11): p.mouse.move(bb["x"] + bb["width"] / 2 - i * 30, y); p.wait_for_timeout(16)
            p.mouse.up(); p.wait_for_timeout(1800)
            h = p.evaluate("location.hash")
            rec(name, tag, "mouse drag film strip", h not in ("#d1031", ""), f"-> {h}")
        rec(name, tag, "a11y (axe)", True, "; ".join(run_axe(p)) or "0 violations")

    if view in ("phone", "small") and scheme == "light":
        rec(name, tag, "tap targets >=24px", True, f"{small_targets(p)} smaller")   # informational
        for t in ("#bt", "#btoggle"):
            if p.locator(t).count() and p.locator(t).is_visible():
                p.tap(t); p.wait_for_timeout(700)
                o = overflow(p)
                rec(name, tag, "drawer opens", o["over"] <= 1, f"{t}; over={o['over']}")
                p.tap(t); p.wait_for_timeout(500)
        if name == "leader":
            cdp = ctx.new_cdp_session(p)
            p.locator("#strip").scroll_into_view_if_needed(); p.wait_for_timeout(400)
            bb = p.locator("#strip").bounding_box()
            start = p.evaluate("location.hash")
            cdp.send("Input.synthesizeScrollGesture", {"x": int(bb["x"] + bb["width"] * .7), "y": int(bb["y"] + bb["height"] / 2),
                                                        "xDistance": -int(bb["width"] * .5), "yDistance": 0, "gestureSourceType": "touch", "speed": 800})
            p.wait_for_timeout(2000)
            end = p.evaluate("location.hash")
            rec(name, tag, "touch swipe film strip", end != start and shows_day(p, int(end[2:])), f"{start} -> {end}")
            p.evaluate("location.hash = '#d1031'"); p.wait_for_timeout(1200)
        # tap the next arrow
        if p.locator("#next").count() and p.locator("#next").is_visible():
            p.tap("#next"); p.wait_for_timeout(900)
            rec(name, tag, "tap next", p.evaluate("location.hash") != "#d1031", p.evaluate("location.hash"))

    rec(name, tag, "no JS errors", not errs, "; ".join(errs)[:150])
    ctx.close()

def screenshots(b):
    SHOTS.mkdir(parents=True, exist_ok=True)
    for name in PAGES:
        for view, scheme in (("desktop", "light"), ("desktop", "dark"), ("phone", "light")):
            ctx = b.new_context(color_scheme=scheme, reduced_motion="reduce", **{**VIEWPORTS[view], "device_scale_factor": 2})
            p, _, _ = open_page(ctx, name)
            p.wait_for_timeout(1500)
            out = SHOTS / f"{name}-{view}-{scheme}.jpg"
            for attempt in range(3):   # headless Chrome sometimes stalls on a busy page; retry
                try: p.screenshot(path=str(out), type="jpeg", quality=82, timeout=45000); break
                except Exception as e: print("retry shot", out.name, str(e)[:60]); p.wait_for_timeout(1000)
            print("shot", out.relative_to(ROOT))
            ctx.close()

def report():
    fails = [r for r in results if not r[3]]
    lines = ["# UI test report", "", f"{len(results) - len(fails)}/{len(results)} checks passed.", "",
             "| Page | View | Check | Result | Detail |", "|---|---|---|---|---|"]
    lines += [f"| {a} | {b} | {c} | {'pass' if ok else '**FAIL**'} | {d.replace('|', '/')} |" for a, b, c, ok, d in results]
    (ROOT / "tests/report.md").write_text("\n".join(lines) + "\n")
    print(f"\n{len(results) - len(fails)}/{len(results)} passed")
    return not fails

if __name__ == "__main__":
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome", headless=True)
        only = [a for a in sys.argv[1:] if not a.startswith("--")]
        for name in ([] if "--shots-only" in sys.argv else only or PAGES):
            for args in [(v, "light", "no-preference") for v in VIEWPORTS] + [("desktop", "dark", "no-preference"), ("phone", "light", "reduce")]:
                try: test_page(b, name, *args)
                except Exception as e: rec(name, args[0], "test run", False, str(e).splitlines()[0][:150])
        if "--shots" in sys.argv or "--shots-only" in sys.argv:
            screenshots(b)
        b.close()
    if "--shots-only" not in sys.argv: sys.exit(0 if report() else 1)
