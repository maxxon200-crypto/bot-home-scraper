"""Simple, inspectable rules. No AI calls or pretend market valuations."""
from datetime import datetime, timedelta, timezone
from statistics import median

from .models import risk_flags


def matches(home, filters):
    if home.city.casefold() != filters["city"].casefold():
        return False
    if home.property_type not in filters["property_types"]:
        return False
    if home.price is None or not filters["min_price"] <= home.price <= filters["max_price"]:
        return False
    if home.sqm is None:
        if filters["min_sqm"] > 0 or filters["max_sqm"] < 10000:
            return False
    elif not filters["min_sqm"] <= home.sqm <= filters["max_sqm"]:
        return False
    for name in ("bedrooms", "bathrooms"):
        minimum = filters["min_" + name]
        if minimum and (getattr(home, name) is None or getattr(home, name) < minimum):
            return False
    ceiling = filters["max_price_per_sqm"]
    if ceiling and (home.price_per_sqm is None or home.price_per_sqm > ceiling):
        return False
    text = (home.title + " " + home.description).casefold()
    if filters["include_any"] and not any(s.casefold() in text for s in filters["include_any"]):
        return False
    if not all(s.casefold() in text for s in filters["require_all"]):
        return False
    if any(s.casefold() in text for s in filters["exclude_any"]):
        return False
    if filters["energy_classes"] and (home.energy_class or "").upper() not in [s.upper() for s in filters["energy_classes"]]:
        return False
    if filters["furnished_only"] and home.furnished is not True:
        return False
    if filters["garden_only"] and home.garden is not True:
        return False
    flags = risk_flags(home)
    if filters["exclude_auctions"] and any(s.startswith("Auction") for s in flags):
        return False
    if filters["exclude_partial_ownership"] and any(s.startswith("Partial") for s in flags):
        return False
    if filters["only_price_drops"] and not home.price_drop_pct:
        return False
    return True


def fresh_homes(homes, hours, now=None):
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    return [h for h in homes if h.last_seen and datetime.fromisoformat(h.last_seen) >= cutoff]


def rank(homes, filters):
    results = []
    for home in homes:
        if not matches(home, filters):
            continue
        flags = risk_flags(home)
        # Exclude self. Compare same city/type and ±25% floor area, before user filters.
        # Deduplicate equal price/size/text peers to reduce obvious syndicated duplicates.
        peers = {}
        for other in homes:
            if (other.id != home.id and home.sqm and other.sqm and other.price_per_sqm
                and other.city.casefold() == home.city.casefold()
                and other.property_type == home.property_type
                and 0.75 * home.sqm <= other.sqm <= 1.25 * home.sqm
                and not any(s.startswith(("Auction", "Partial")) for s in risk_flags(other))):
                peers[(other.price, other.sqm, other.description[:100])] = other.price_per_sqm
        baseline = median(peers.values()) if len(peers) >= 5 else None
        discount = 100 * (1 - home.price_per_sqm / baseline) if baseline and home.price_per_sqm else None
        reasons = []
        score = 0.0
        if discount is not None:
            reasons.append(f"{discount:+.1f}% below the observed peer median ({len(peers)} peers)")
            score += max(-50, min(50, discount))
        else:
            reasons.append(f"Too few comparable observations ({len(peers)}; need 5)")
        if home.price_drop_pct:
            reasons.append(f"Asking price fell {home.price_drop_pct:.1f}% since its previous recorded price")
            score += min(30, home.price_drop_pct)
        if any(s.startswith(("Auction", "Partial")) for s in flags):
            score -= 40
            reasons.append("Ranking reduced for auction / ownership language")
        results.append({"home": home, "score": round(score, 1), "peer_count": len(peers),
                        "peer_median": baseline, "discount_pct": discount, "reasons": reasons, "flags": flags})
    return sorted(results, key=lambda row: (-row["score"], row["home"].price, row["home"].id))

