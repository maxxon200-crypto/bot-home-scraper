"""Build the report from small HTML/CSS/JS files; never reinsert removed UI copy."""
from dataclasses import asdict
import json
from pathlib import Path
import re
import shutil


def atomic_write(path, text):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def money(value):
    return f"€{value:,.0f}" if value is not None else ""


def brief(home):
    """Only known structured features, or an excerpt capped at 110 characters."""
    facts = []
    if home.condition:
        facts.append(home.condition.capitalize())
    if home.furnished is True:
        facts.append("Furnished")
    if home.garden is True:
        facts.append("Garden listed")
    if facts:
        return " · ".join(facts)
    text = re.sub(r"\s+", " ", home.description).strip()
    return text if len(text) <= 110 else text[:107].rsplit(" ", 1)[0].rstrip(".,;:") + "…"


def write_report(rows, status, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    assets = directory / "assets"
    assets.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("assets") / "background.png", assets / "background.png")
    web = Path(__file__).with_name("web")
    for path in web.rglob("*"):
        if path.is_file() and path.name != "index.html":
            output = assets / path.relative_to(web)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
    export = [{**row, "summary": brief(row["home"]), "home": asdict(row["home"])} for row in rows]
    payload = {"status": status, "results": export}
    atomic_write(directory / "homes.json", json.dumps(payload, indent=2, ensure_ascii=False))
    # Inert embedded JSON supports direct file opening; never let adverts close this tag.
    embedded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    template = (web / "index.html").read_text(encoding="utf-8")
    atomic_write(directory / "index.html", template.replace("__INITIAL_DATA__", embedded))
