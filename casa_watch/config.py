"""Read the settings file and catch common mistakes before making requests."""
from pathlib import Path
import math
import tomllib
from urllib.parse import urlsplit


def load_config(path):
    path = Path(path).resolve()
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    with Path(__file__).with_name("defaults.toml").open("rb") as handle:
        defaults = tomllib.load(handle)
    # Unknown keys are usually typos: do not silently ignore a misspelled budget.
    for section, values in config.items():
        if section not in defaults or not isinstance(values, dict):
            raise ValueError(f"Unknown section: {section}")
        if values.keys() - defaults[section].keys():
            raise ValueError(f"Unknown settings in {section}: {values.keys() - defaults[section].keys()}")
    for section, values in defaults.items():
        config.setdefault(section, {})
        for key, default in values.items():
            value = config[section].setdefault(key, default)
            if isinstance(default, bool):
                valid = isinstance(value, bool)
            elif isinstance(default, int):
                valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
            elif isinstance(default, list):
                valid = isinstance(value, list) and all(isinstance(v, str) for v in value)
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                raise ValueError(f"Invalid {section}.{key}: {value!r}")
    search, monitor, source = config["search"], config["monitor"], config["source"]
    for low, high in [("min_price", "max_price"), ("min_sqm", "max_sqm")]:
        if search[low] > search[high]:
            raise ValueError(f"{low} cannot exceed {high}")
    if set(search["property_types"]) - {"apartment", "penthouse", "house", "rustic"}:
        raise ValueError("Unknown property type")
    for key in ("max_requests_per_day", "catalog_pages_per_cycle", "max_catalog_pages", "detail_pages_per_cycle"):
        if type(monitor[key]) is not int or monitor[key] < 1:
            raise ValueError(f"{key} must be a positive whole number")
    if monitor["interval_seconds"] < 300 or monitor["request_delay_seconds"] < 2:
        raise ValueError("Use at least 300 seconds between cycles and 2 seconds between requests")
    if monitor["stale_after_hours"] <= 0 or monitor["detail_refresh_hours"] <= 0:
        raise ValueError("Freshness settings must be positive")
    url = urlsplit(source["city_url"])
    if url.scheme != "https" or url.netloc != "www.case24.it" or not url.path.startswith("/immobili/") or url.query:
        raise ValueError("city_url must be a Case24 /immobili/ city URL without a query")
    allowed = {"appartamenti", "attici", "case_e_ville_indipendenti", "case_e_ville_a_schiera", "rustici"}
    if not source["categories"] or set(source["categories"]) - allowed:
        raise ValueError("Choose supported residential Case24 categories")
    for key in ("data_dir", "report_dir"):
        monitor[key] = str((path.parent / monitor[key]).resolve())
    return config
