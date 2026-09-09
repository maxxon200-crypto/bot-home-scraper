"""SQLite is a small database stored in a file; no server or subscription."""
from dataclasses import asdict
from datetime import datetime, timezone
import json
import sqlite3

from .models import Home


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS homes (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS prices (id TEXT, observed_at TEXT, price REAL);
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def get_state(self, key, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set_state(self, key, value):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def reserve_request(self, limit):
        """Persist the budget BEFORE sending a request, including failed requests."""
        key = "requests:" + utc_now()[:10]
        count = self.get_state(key, 0)
        if count >= limit:
            raise RuntimeError("Daily request budget reached; resumes after 00:00 UTC")
        self.set_state(key, count + 1)

    def get(self, home_id):
        row = self.db.execute("SELECT payload FROM homes WHERE id=?", (home_id,)).fetchone()
        return Home(**json.loads(row[0])) if row else None

    def all(self):
        return [Home(**json.loads(row[0])) for row in self.db.execute("SELECT payload FROM homes")]

    def save(self, home, detailed=False, now=None):
        now = now or utc_now()
        old = self.get(home.id)
        home.first_seen = old.first_seen if old else now
        home.last_seen = now
        if old:
            home.previous_price = old.previous_price
            home.price_changed_at = old.price_changed_at
            if not detailed:
                # A summary refresh must not erase the full description or structured details.
                for field in ("bedrooms", "bathrooms", "energy_class", "furnished", "garden", "condition", "detail_checked"):
                    setattr(home, field, getattr(old, field))
                if old.detail_checked:
                    home.description = old.description
        changed = old is not None and home.price is not None and old.price is not None and home.price != old.price
        if changed:
            home.previous_price = old.price
            home.price_changed_at = now
        if detailed:
            home.detail_checked = now
        with self.db:
            if home.price is not None and (not old or old.price != home.price):
                self.db.execute("INSERT INTO prices VALUES (?, ?, ?)", (home.id, now, home.price))
            self.db.execute("INSERT OR REPLACE INTO homes VALUES (?, ?)", (home.id, json.dumps(asdict(home))))
        return "new" if not old else "price_change" if changed else "seen"

