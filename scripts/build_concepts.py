"""Rebuild calendar/concepts/*.html from their templates and data/calendar.json."""
import pathlib
root = pathlib.Path(__file__).resolve().parent.parent
data = (root / "data/calendar.json").read_text().replace("</", "<\\/")
for t in sorted((root / "calendar/concepts").glob("*.template.html")):
    out = t.with_name(t.name.replace(".template", ""))
    out.write_text(t.read_text().replace("__DATA__", data))
    print(out.relative_to(root))
