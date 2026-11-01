#!/usr/bin/env python3
"""Find spoken calendar dates in downloaded transcripts.

Writes data/hits.jsonl: one row per date mention with surrounding context.
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
ORD_WORDS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth",
             "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth", "sixteenth",
             "seventeenth", "eighteenth", "nineteenth", "twentieth", "twenty-first", "twenty-second",
             "twenty-third", "twenty-fourth", "twenty-fifth", "twenty-sixth", "twenty-seventh",
             "twenty-eighth", "twenty-ninth", "thirtieth", "thirty-first"]
WORD_DAY = {w: i + 1 for i, w in enumerate(ORD_WORDS)}
WORD_DAY.update({w.replace("-", " "): d for w, d in list(WORD_DAY.items()) if "-" in w})
ABBR = {m[:3]: i + 1 for i, m in enumerate(MONTHS)}
ABBR["Sept"] = 9
MON = "(?P<mon>" + "|".join(MONTHS) + r"|(?:" + "|".join(k for k in ABBR if k != "May") + r")\.?)"
DAYN = r"(?P<dn>[12]?\d|3[01])(?:st|nd|rd|th)?"
DAYW = "(?P<dw>" + "|".join(sorted(WORD_DAY, key=len, reverse=True)) + ")"
YEAR = r"(?:,?\s+(?:in\s+)?(?P<yr>1[0-9]{3}|20[0-9]{2}))?"
PATTERNS = [
    re.compile(MON + r"\s+(?:the\s+)?" + DAYN + r"\b" + YEAR),
    re.compile(MON + r"\s+(?:the\s+)?" + DAYW + r"\b" + YEAR, re.I),
    re.compile(r"\b(?:the\s+)?" + DAYN + r"\s+of\s+" + MON + r"\b" + YEAR),
    re.compile(r"\b(?:the\s+)?" + DAYW + r"\s+of\s+" + MON + r"\b" + YEAR, re.I),
    re.compile(r"\b" + DAYN + r"\s+" + MON + r"\b" + YEAR),  # British "12 October 1985"
]
# a 4-digit "day" is a year or a keypad code, not a date
KEYPAD = re.compile(r"\d-\d-\d-\d")
HOLIDAYS = {
    r"Christmas Eve": (12, 24), r"Christmas Day": (12, 25), r"New Year'?s Eve": (12, 31),
    r"New Year'?s Day": (1, 1), r"Halloween": (10, 31), r"Valentine'?s Day": (2, 14),
    r"Independence Day": (7, 4), r"St\.? Patrick'?s Day": (3, 17), r"Guy Fawkes": (11, 5),
    r"April Fools'?": (4, 1), r"Groundhog Day": (2, 2), r"Boxing Day": (12, 26),
    r"Cinco de Mayo": (5, 5), r"Bastille Day": (7, 14), r"D-Day": (6, 6),
}
HOL = [(re.compile(r"\b" + p + r"\b"), md) for p, md in HOLIDAYS.items()]
MAXDAY = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def scan(text):
    seen = set()
    for pat in PATTERNS:
        for m in pat.finditer(text):
            mon_raw = m.group("mon").rstrip(".")
            if not mon_raw[0].isupper():
                continue  # "march", "may" as verbs
            if KEYPAD.search(text[max(0, m.start() - 25): m.end() + 25]):
                continue
            name = mon_raw.capitalize()
            mon = MONTHS.index(name) + 1 if name in MONTHS else ABBR[name]
            g = m.groupdict()
            day = int(g["dn"]) if g.get("dn") else WORD_DAY[re.sub(r"\s+", " ", g["dw"].lower())]
            if day < 1 or day > MAXDAY[mon - 1] or m.start() in seen:
                continue
            seen.add(m.start())
            yield m, mon, day, g.get("yr"), "date"
    # bare holiday names ("Christmas Eve") don't count; see data/DECISIONS.md


def main():
    out = (ROOT / "data/hits.jsonl").open("w")
    n = 0
    for f in sorted((ROOT / "transcripts").rglob("*.txt")):
        raw = f.read_text()
        header, _, text = raw.partition("\n")
        # subtitle OCR glitches: "1 2th, 1 985" -> "12th, 1985", "21 st" -> "21st"
        text = re.sub(r"(?<=\b1) (?=\d)", "", text)
        text = re.sub(r"(?<=\d) (?=(?:st|nd|rd|th)\b)", "", text)
        text = re.sub(r"\s*\n\s*", " ", text)
        kind = "movie" if f.parent.name == "movies" else "tv"
        for m, mon, day, yr, typ in scan(text):
            ctx = text[max(0, m.start() - 300): m.end() + 300].replace("\n", " ")
            out.write(json.dumps({
                "kind": kind, "source": header.lstrip("# "), "file": str(f.relative_to(ROOT)),
                "month": mon, "day": day, "year": yr, "type": typ, "match": m.group(0),
                "context": ctx}) + "\n")
            n += 1
    print(f"{n} hits")


if __name__ == "__main__":
    main()
