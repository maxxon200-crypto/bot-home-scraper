"""Command-line entry point. Run: python -m casa_watch --once"""
import argparse
import logging
from logging.handlers import RotatingFileHandler
import math
from pathlib import Path
import time

from .config import load_config
from .monitor import run
from .source import Case24
from .storage import Store


def main():
    parser = argparse.ArgumentParser(description="Monitor Italian homes for sale without paid APIs.")
    parser.add_argument("--config", default="config.toml", help="Path to your TOML settings")
    parser.add_argument("--once", action="store_true", help="Check once, write the report, then exit")
    parser.add_argument("--hours", type=float, help="Run for this many hours; omit to run until Ctrl+C")
    args = parser.parse_args()
    if args.hours is not None and (not math.isfinite(args.hours) or args.hours <= 0):
        parser.error("--hours must be a positive finite number")
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as error:
        parser.error(str(error))
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
    try:
        return run(config, store, source, args.once, deadline)
    except KeyboardInterrupt:
        logging.info("Stopped. Your history and progress are saved.")
        return 0
    except Exception:
        logging.exception("Monitor stopped unexpectedly. See data/monitor.log.")
        return 1
    finally:
        source.close()
        store.close()
        lock.close()
