"""Match an advertised street AND civic number to Milan's official open data.

No city-centre pins, fuzzy geocoding, street centroids, or paid API requests.
An advert can mention another address, so matches are labelled as inferred.
"""
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9/ ]", " ", text)).strip()


@lru_cache(maxsize=1)
def address_index():
    path = Path(__file__).with_name("assets") / "milan-addresses.json"
    return json.loads(path.read_text(encoding="utf-8"))["streets"]


def locate(home, index=None):
    if home.city.casefold() not in ("milano", "milan"):
        return replace(home, address=None, latitude=None, longitude=None, location_source=None)
    index = address_index() if index is None else index
    # Agency contact details normally occur later. Only consider the opening property text.
    text = normalize(home.description[:1000])
    candidates = []
    for match in re.finditer(r"\b(via|viale|piazza|piazzale|corso|largo|vicolo|alzaia|bastioni)\s+", text):
        before = text[max(0, match.start() - 65):match.start()]
        if re.search(r"(?:vicino|pressi|passi|fermata|metropolitana|agenzia|uffici\w*|sede|distanza|adiacen\w*|ad ze|angolo|incontro|\w*group|immobiliari|immobiliare|contatt\w*)\b", before):
            continue
        segment = text[match.start():match.start() + 100]
        # Try all civic-number boundaries; a street itself may contain a number/date.
        for number in re.finditer(r"\s+(?:n\s+|numero\s+)?(\d{1,4}(?:[a-z]|/\d{1,3})?)\b", segment):
            street = segment[:number.start()].strip()
            if street not in index:
                continue
            record = index[street].get(number[1])
            if record:
                candidates.append(record)
    # Two different complete addresses are ambiguous. Leave the listing unlocated.
    unique = {record[0]: record for record in candidates}
    if len(unique) != 1:
        return replace(home, address=None, latitude=None, longitude=None, location_source=None)
    address, lat, lon = next(iter(unique.values()))
    return replace(home, address=address, latitude=lat, longitude=lon,
                   location_source="Advert address matched to Comune di Milano civic data (2026-09)")
