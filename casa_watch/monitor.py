"""One cycle: latest homes + rotating catalogue pages + queued detail checks."""
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import time
import json

from .ranking import fresh_homes, rank
from .report import atomic_write, write_report
from .locations import locate
from .source import parse_detail, parse_search
from .storage import utc_now

LOG = logging.getLogger(__name__)


def cycle(config, store, source):
    settings, filters = config["monitor"], config["search"]
    root = config["source"]["city_url"].rstrip("/") + "/"
    errors = []
    observed_ids = set()
    report_dir = Path(settings["report_dir"])
    report_dir.mkdir(parents=True, exist_ok=True)
    checked_pages = 0

    def progress(phase):
        atomic_write(report_dir / "progress.json", json.dumps({"running": True, "phase": phase,
            "pages_this_cycle": checked_pages, "collected": len(store.all()), "updated_at": utc_now()}))

    progress("Checking latest homes")

    def fetch_page(url):
        homes, last_page = parse_search(source.get(url), url)
        for home in homes:
            store.save(locate(home))
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
        # Avoid repeatedly downloading tiny finished categories while apartments remain unscanned.
        done_key = "catalogue_done:" + root
        done = store.get_state(done_key, [])
        if set(categories) <= set(done):
            done = []
            store.set_state(done_key, done)
        while categories[index % len(categories)] in done:
            index += 1
        category = categories[index % len(categories)]
        base = root + category + "-in-vendita/"
        page = store.get_state("page:" + base, 1)
        url = base if page == 1 else base + f"?page={page}"
        try:
            last_page = fetch_page(url)
            checked_pages += 1
            seen = store.get_state("visited:" + base, list(range(1, page)))
            store.set_state("visited:" + base, sorted(set(seen + [page])))
            store.set_state("total_pages:" + base, last_page)
            next_page = page + 1 if page < min(last_page, settings["max_catalog_pages"]) else 1
            store.set_state("page:" + base, next_page)
            if next_page == 1:
                store.set_state(done_key, done + [category])
            progress(f"Collecting catalogue · {checked_pages} pages checked")
            LOG.info("Catalogue progress: %d pages this cycle, %d homes saved", checked_pages, len(store.all()))
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
        progress("Checking property details and addresses")
        store.set_state("detail_attempt:" + home.id, utc_now())
        try:
            updated = locate(parse_detail(source.get(home.url), home))
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
              "max_price": filters["max_price"], "errors": errors,
              "collected_total": len(store.all()),
              "catalogue_pages_scanned": sum(len(store.get_state("visited:" + root + c + "-in-vendita/", [])) for c in categories),
              "catalogue_pages_known": sum(store.get_state("total_pages:" + root + c + "-in-vendita/", 0) for c in categories)}
    write_report(rows, status, settings["report_dir"])
    atomic_write(report_dir / "progress.json", json.dumps({"running": False, "phase": "Collection complete",
        "pages_this_cycle": checked_pages, "collected": len(store.all()), "updated_at": utc_now()}))
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


def render_saved(config, store):
    """Refresh only the presentation/location index; never fake source timestamps."""
    for home in store.all():
        store.update_location(locate(home))
    homes = fresh_homes(store.all(), config["monitor"]["stale_after_hours"])
    report = Path(config["monitor"]["report_dir"])
    try:
        status = json.loads((report / "homes.json").read_text(encoding="utf-8"))["status"]
    except (OSError, ValueError, KeyError):
        status = {"checked_at": "", "observed": len(homes)}
    write_report(rank(homes, config["search"]), status, report)


def run(config, store, source, once=False, deadline=None, wake=None):
    failures = 0
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            break
        old_pages = config["monitor"]["catalog_pages_per_cycle"]
        if wake is not None and wake.is_set():
            wake.clear()
            config["monitor"]["catalog_pages_per_cycle"] = max(40, old_pages)
        try:
            status = cycle(config, store, source)
        finally:
            config["monitor"]["catalog_pages_per_cycle"] = old_pages
        if once:
            return 1 if status["errors"] else 0
        failures = min(4, failures + 1) if status["errors"] else 0
        wait = min(7200, config["monitor"]["interval_seconds"] * (2 ** failures))
        if deadline is not None:
            wait = min(wait, max(0, deadline - time.monotonic()))
        LOG.info("Next cycle in %.0f seconds. Ctrl+C stops safely.", wait)
        if wake is None:
            time.sleep(wait)
        else:
            wake.wait(wait)
    return 0
