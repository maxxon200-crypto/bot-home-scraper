"""Rebuild the compact offline address index from a downloaded municipal CSV ZIP.

Usage: python tools/build_address_index.py path/to/milan-addresses.zip
Download/provenance: see THIRD_PARTY.md. No listings are included in this index.
"""
import csv
import io
import json
from pathlib import Path
import re
import sys
import zipfile

from casa_watch.locations import normalize


def build(archive_path, target):
    aliases = {}
    streets = {}
    with zipfile.ZipFile(archive_path) as archive:
        name = next(name for name in archive.namelist() if name.endswith(".csv"))
        rows = csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig")), delimiter=";")
        for row in rows:
            if row["RESIDENZIALE"] != "1" or row["DATA_SOPPRESSIONE"] not in ("0", "") or row["BARRA2"].strip():
                continue
            code = row["CODICE_VIA"]
            kind = row["TIPO"]
            label = row["OPENSTREETMAP"] or row["DESCRITTIVO"]
            names = [row[k] for k in ("OPENSTREETMAP", "DESCRITTIVO", "ANNCSU")]
            # The municipality also supplies surname (given name) notation.
            names.append(re.sub(r"\([^)]*\)", "", row["DENOMINAZIONE"]))
            for name in names:
                if name.strip():
                    alias = normalize(kind + " " + name)
                    aliases.setdefault(alias, set()).add(code)
            number = normalize(row["NUMEROCOMPLETO"])
            try:
                lat, lon = float(row["LAT_WGS84"]), float(row["LONG_WGS84"])
            except ValueError:
                continue
            if not (45.3 < lat < 45.65 and 8.9 < lon < 9.4):
                continue
            record = [f"{kind} {label.title()}, {row['NUMEROCOMPLETO']}", lat, lon]
            addresses = streets.setdefault(code, {})
            if number not in addresses:
                addresses[number] = record
    result = {alias: streets[next(iter(codes))] for alias, codes in aliases.items() if len(codes) == 1}
    payload = {"source": "Comune di Milano — Numeri civici con coordinate geografiche", "date": "2026-09-01", "license": "CC BY 4.0", "streets": result}
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Built {len(result)} unambiguous street aliases from {sum(len(v) for v in streets.values())} civic addresses")


if __name__ == "__main__":
    build(sys.argv[1], Path(__file__).resolve().parents[1] / "casa_watch/assets/milan-addresses.json")
