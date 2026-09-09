"""The common shape of one property. None means the site did not say."""
from dataclasses import dataclass
import re


@dataclass
class Home:
    id: str
    url: str
    title: str
    city: str
    property_type: str
    price: float | None
    sqm: float | None
    description: str = ""
    bedrooms: int | None = None
    rooms: int | None = None
    bathrooms: int | None = None
    energy_class: str | None = None
    furnished: bool | None = None
    garden: bool | None = None
    condition: str | None = None
    first_seen: str = ""
    last_seen: str = ""
    detail_checked: str = ""
    previous_price: float | None = None
    price_changed_at: str = ""
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_source: str | None = None

    @property
    def price_per_sqm(self):
        return self.price / self.sqm if self.price and self.sqm else None

    @property
    def price_drop_pct(self):
        if self.previous_price and self.price is not None:
            return max(0, 100 * (1 - self.price / self.previous_price))
        return 0


def italian_number(text):
    """Read '€ 310.000' or '80,5 Mq'. Never turn 'price on request' into 0."""
    match = re.search(r"\d[\d.,]*", text.replace("\xa0", " "))
    if not match:
        return None
    value = float(match[0].rstrip(".,").replace(".", "").replace(",", "."))
    return value if value > 0 else None


def risk_flags(home):
    text = home.description.casefold()
    flags = []
    if re.search(r"\b(asta|aste|pignoramento)\b", text):
        flags.append("Auction language: the price may be a starting bid")
    if re.search(r"nuda propriet|quota di|quota pari|usufrutto|proprietà superficiaria", text):
        flags.append("Partial ownership / property rights: check the advert")
    if not home.detail_checked:
        flags.append("Details pending: filters use only the short advert")
    if home.price is None:
        flags.append("Price unavailable: cannot verify your budget")
    return flags
