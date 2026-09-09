"""One cycle: latest homes + rotating catalogue pages + queued detail checks."""
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import time

from .ranking import fresh_homes, rank
from .report import write_report
from .source import parse_detail, parse_search
from .storage import utc_now

LOG = logging.getLogger(__name__)


def cycle(config, store, source):
    settings, filters = config["monitor"], config["search"]
    root = config["source"]["city_url"].rstrip("/") + "/"
    errors = []
    observed_ids = set()

    def fetch_page(url):
        homes, last_page = parse_search(source.get(url), url)
        for home in homes:
            store.save(home)
            observed_ids.add(home.id)
        return last_page

    try:
        fetch_page(root) # Latest 30 city adverts; parser excludes rent and commercial units.
    except Exception as error:
        LOG.exception("Latest listing page failed")
        errors.append(f"Latest listings: {error}")

    categories = config["source"]["categories"]
    index = store.get_state("category_index:" + root, 0)
    for _ in range(settings["catalog_pages_per_cycle"]):
        category = categories[index % len(categories)]
        base = root + category + "-in-vendita/"
        page = store.get_state("page:" + base, 1)
        url = base if page == 1 else base + f"?page={page}"
        try:
            last_page = fetch_page(url)
            next_page = page + 1 if page < min(last_page, settings["max_catalog_pages"]) else 1
            store.set_state("page:" + base, next_page)
        except Exception as error:
            LOG.exception("Catalogue page failed: %s", url)
            errors.append(f"{category} page {page}: {error}")
            # A removed last page must not trap the category forever.
            if page > 1:
                store.set_state("page:" + base, 1)
        index += 1
    store.set_state("category_index:" + root, index % len(categories))

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=settings["detail_refresh_hours"])).isoformat()
    # Oldest checked first: sustained incoming listings cannot starve the detail queue.
    retry_cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    queue = sorted((h for h in store.all() if h.city.casefold() == filters["city"].casefold()
                    and h.url.startswith(root) and h.detail_checked < cutoff
                    and store.get_state("detail_attempt:" + h.id, "") < retry_cutoff),
                   key=lambda h: (store.get_state("detail_attempt:" + h.id, ""), h.first_seen, h.id))
    for home in queue[:settings["detail_pages_per_cycle"]]:
        store.set_state("detail_attempt:" + home.id, utc_now())
        try:
            updated = parse_detail(source.get(home.url), home)
            store.save(updated, detailed=True)
            observed_ids.add(home.id)
        except Exception as error:
            LOG.exception("Detail check failed: %s", home.id)
            errors.append(f"Detail #{home.id}: {error}")
            # The separate attempt time prevents one broken advert starving the queue.

    homes = fresh_homes([h for h in store.all() if h.url.startswith(root)], settings["stale_after_hours"])
    rows = rank(homes, filters)
    now = utc_now()
    if not errors:
        store.set_state("last_success", now)
    status = {"checked_at": now, "last_success": store.get_state("last_success"),
              "observed": len(homes), "observed_this_cycle": len(observed_ids),
              "details_pending": sum(not h.detail_checked for h in homes),
              "requests_today": store.get_state("requests:" + now[:10], 0),
              "daily_budget": settings["max_requests_per_day"], "city": filters["city"],
              "max_price": filters["max_price"], "errors": errors}
    write_report(rows, status, settings["report_dir"])
    # Notify even when a later detail check makes a home pass the filters for the first time.
    # Only local console/log output: no email accounts, tokens, or paid notification API.
    for row in rows:
        home = row["home"]
        key = "alert:" + home.id
        previous_alert = store.get_state(key)
        if previous_alert != home.price:
            event = "NEW MATCH" if previous_alert is None else "PRICE CHANGE"
            LOG.info("%s | EUR %s | %s", event, home.price, home.url)
            store.set_state(key, home.price)
    LOG.info("Cycle done: %d matches, %d errors. Report: %s", len(rows), len(errors), Path(settings["report_dir"]) / "index.html")
    return status


def run(config, store, source, once=False, deadline=None):
    failures = 0
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            break
        status = cycle(config, store, source)
        if once:
            return 1 if status["errors"] else 0
        failures = min(4, failures + 1) if status["errors"] else 0
        wait = min(7200, config["monitor"]["interval_seconds"] * (2 ** failures))
        if deadline is not None:
            wait = min(wait, max(0, deadline - time.monotonic()))
        LOG.info("Next cycle in %.0f seconds. Ctrl+C stops safely.", wait)
        time.sleep(wait)
    return 0
