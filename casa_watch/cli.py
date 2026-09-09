"""Command-line entry point. Run: python -m casa_watch --once"""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import time
from threading import Event

from .config import load_config
from .monitor import run
from .source import Case24
from .storage import Store


def main():
    parser = argparse.ArgumentParser(description="Monitor Italian homes for sale without paid APIs.")
    parser.add_argument("--config", default="config.toml", help="Path to your TOML settings")
    parser.add_argument("--once", action="store_true", help="Check once, write the report, then exit")
    parser.add_argument("--hours", type=float, help="Run for this many hours; omit to run until Ctrl+C")
    parser.add_argument("--catalog-pages", type=int, help="Catalogue pages per cycle (1–200), e.g. 40 for an initial collection")
    parser.add_argument("--detail-pages", type=int, help="Detail pages per cycle (1–200)")
    parser.add_argument("--serve", action="store_true", help="Open the local onboarding/map UI on http://127.0.0.1:8765")
    parser.add_argument("--port", type=int, default=8765, help="Local UI port")
    args = parser.parse_args()
    if args.hours is not None and (not math.isfinite(args.hours) or args.hours <= 0):
        parser.error("--hours must be a positive finite number")
    if not 1024 <= args.port <= 65535 or (args.serve and args.once):
        parser.error("Use port 1024–65535; --serve cannot be combined with --once")
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for argument, setting in ((args.catalog_pages, "catalog_pages_per_cycle"), (args.detail_pages, "detail_pages_per_cycle")):
        if argument is not None:
            if not 1 <= argument <= 200:
                parser.error("Page counts must be between 1 and 200")
            config["monitor"][setting] = argument
    data = Path(config["monitor"]["data_dir"])
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.StreamHandler(), RotatingFileHandler(data / "monitor.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")])
    # OS file lock is released even after a crash. Stops two monitors sharing a budget/DB.
    lock = (data / "monitor.lock").open("a+b")
    try:
        lock.seek(0)
        if lock.read(1) == b"":
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        import os
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        parser.error("Another monitor is using this data directory. Stop it first.")
    store = Store(data / "homes.sqlite3")
    deadline = time.monotonic() + args.hours * 3600 if args.hours else None
    source = Case24(store, config["monitor"], deadline)
    server = None
    wake = Event() if args.serve else None
    try:
        if args.serve:
            from .server import start_server
            from .monitor import render_saved
            render_saved(config, store)
            server = start_server(config["monitor"]["report_dir"], wake, args.port)
            logging.info("Open http://127.0.0.1:%d — Ctrl+C stops the app", args.port)
        return run(config, store, source, args.once, deadline, wake)
    except KeyboardInterrupt:
        logging.info("Stopped. Your history and progress are saved.")
        return 0
    except Exception:
        logging.exception("Monitor stopped unexpectedly. See data/monitor.log.")
        return 1
    finally:
        if server:
            server.shutdown()
            server.server_close()
        source.close()
        store.close()
        lock.close()
