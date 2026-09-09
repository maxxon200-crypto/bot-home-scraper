"""Synthetic fixtures: tests never fetch the network or redistribute real adverts."""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from casa_watch.config import load_config
from casa_watch.models import Home, italian_number
from casa_watch.monitor import cycle, run
from casa_watch.ranking import fresh_homes, matches, rank
from casa_watch.report import write_report
from casa_watch.source import Case24, canonical_url, parse_detail, parse_search
from casa_watch.storage import Store

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.case24.it/immobili/lombardia/milano/milano/"


def sample(**changes):
    fields = dict(id="1", url=URL + "2_camere_in_vendita/1.html", title="Test apartment",
                  city="Milano", property_type="apartment", price=300000, sqm=80)
    fields.update(changes)
    return Home(**fields)


def card(home_id="1", category="2_camere_in_vendita", price="300.000"):
    return f'''<div class="risultatoRicerca"><div class="fasciaAltaRisultato03">Milano (MI) | € {price} | 80,5 Mq</div>
    <a href="{URL}{category}/{home_id}.html#annuncio">Open</a><p><strong>Apartment</strong>Test description</p></div>'''


class ParsingTests(unittest.TestCase):
    def test_italian_prices_and_unknowns(self):
        self.assertEqual(italian_number("€ 1.250.000"), 1250000)
        self.assertEqual(italian_number("80,5 mq"), 80.5)
        self.assertIsNone(italian_number("Trattativa riservata"))
        self.assertIsNone(italian_number("0"))

    def test_sales_only_dedup_pagination(self):
        html = card() + card() + card("2", "2_camere_in_affitto") + card("3", "garage_in_vendita")
        html += '<div class="linkPagine"><a href="?&amp;page=181">last</a></div>'
        homes, pages = parse_search(html, URL)
        self.assertEqual(len(homes), 1)
        self.assertEqual(homes[0].price, 300000)
        self.assertEqual(homes[0].sqm, 80.5)
        self.assertEqual(pages, 181)
        self.assertNotIn("#", homes[0].url)

    def test_block_or_changed_layout_is_error(self):
        with self.assertRaises(ValueError):
            parse_search("<h1>Please sign in</h1>", URL)
        with self.assertRaises(ValueError):
            parse_search('<div class="risultatoRicerca">Changed layout</div>', URL)

    def test_detail_fields_and_wrong_identity(self):
        fields = {"Codice inserzione:": "1", "Comune:": "Milano", "Prezzo": "€ 280.000",
                  "Superficie (Mq) :": "80,5 Mq.", "Camere:": "2", "Bagni:": "1",
                  "Arredato:": "SÌ", "Classe energetica:": "B", "Tipologia giardino :": "Nessuno"}
        html = '<p class="contenuti"><strong>Descrizione:</strong>Test apartment</p><table>'
        html += "".join(f"<tr><td>{key}</td><td>{value}</td></tr>" for key, value in fields.items()) + "</table>"
        home = parse_detail(html, sample())
        self.assertEqual((home.price, home.sqm, home.bedrooms, home.bathrooms), (280000, 80.5, 2, 1))
        self.assertTrue(home.furnished)
        self.assertFalse(home.garden)
        with self.assertRaises(ValueError):
            parse_detail(html, sample(id="2"))

    def test_url_rejects_foreign_host_and_normalises_path(self):
        with self.assertRaises(ValueError):
            canonical_url(URL, "https://example.com/a")
        self.assertEqual(canonical_url(URL, "/immobili//1.html#x"), "https://www.case24.it/immobili/1.html")


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()

    def test_price_history_and_detail_preservation(self):
        self.assertEqual(self.store.save(sample(bedrooms=2, description="Full text"), detailed=True), "new")
        self.store.save(sample(price=280000, description="Short text"))
        home = self.store.get("1")
        self.assertEqual(home.previous_price, 300000)
        self.assertAlmostEqual(home.price_drop_pct, 6.6666667)
        self.assertEqual(home.bedrooms, 2)
        self.assertEqual(home.description, "Full text")
        self.store.save(sample(price=280000))
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM prices").fetchone()[0], 2)
        self.store.save(sample(price=350000))
        self.assertEqual(self.store.get("1").price_drop_pct, 0)

    def test_budget_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "db.sqlite"
            first = Store(path)
            first.reserve_request(1)
            first.close()
            second = Store(path)
            try:
                with self.assertRaises(RuntimeError):
                    second.reserve_request(1)
            finally:
                second.close()


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.filters = load_config(ROOT / "config.toml")["search"]

    def test_budget_and_missing_data_fail_strict_filters(self):
        self.assertTrue(matches(sample(price=10000000), self.filters))
        self.assertFalse(matches(sample(price=10000001), self.filters))
        self.assertFalse(matches(sample(price=None), self.filters))
        self.filters["min_bedrooms"] = 2
        self.assertFalse(matches(sample(), self.filters))
        self.assertTrue(matches(sample(bedrooms=2), self.filters))

    def test_keywords_and_auction_exclusion(self):
        self.filters["require_all"] = ["terrazzo"]
        self.filters["exclude_auctions"] = True
        self.assertFalse(matches(sample(description="Terrazzo, vendita all'asta"), self.filters))
        self.assertTrue(matches(sample(description="Appartamento con TERRAZZO"), self.filters))

    def test_peer_median_requires_five_and_excludes_self_and_other_city(self):
        target = sample(price=200000)
        peers = [sample(id=str(i + 2), price=300000 + i * 10000) for i in range(5)]
        rows = rank([target] + peers, self.filters)
        self.assertEqual(rows[0]["home"].id, "1")
        self.assertEqual(rows[0]["peer_count"], 5)
        self.assertEqual(rows[0]["peer_median"], 4000)
        sparse = rank([target] + peers[:4] + [sample(id="99", city="Roma")], self.filters)
        self.assertIsNone(next(row for row in sparse if row["home"].id == "1")["peer_median"])

    def test_stale_observation_hidden(self):
        now = datetime(2026, 9, 9, tzinfo=timezone.utc)
        homes = [sample(last_seen="2026-09-01T00:00:00+00:00"), sample(id="2", last_seen="2026-09-09T00:00:00+00:00")]
        self.assertEqual([h.id for h in fresh_homes(homes, 72, now)], ["2"])


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.source = Case24(self.store, load_config(ROOT / "config.toml")["monitor"])

    def tearDown(self):
        self.source.close()
        self.store.close()

    def response(self, code=200, content=b"User-agent: *\nAllow: /", headers=None):
        response = requests.Response()
        response.status_code = code
        response._content = content
        response.headers.update(headers or {})
        return response

    def test_robots_denial_prevents_listing_request(self):
        with patch.object(self.source.session, "get", return_value=self.response(content=b"User-agent: *\nDisallow: /")) as get:
            with self.assertRaises(RuntimeError):
                self.source.get(URL)
            self.assertEqual(get.call_count, 1)

    def test_rate_limit_persists_cooldown(self):
        with patch.object(self.source.session, "get", return_value=self.response(429, headers={"Retry-After": "7200"})) as get:
            with self.assertRaises(requests.HTTPError):
                self.source.raw_get(URL)
            with self.assertRaises(RuntimeError):
                self.source.raw_get(URL)
            self.assertEqual(get.call_count, 1)
            self.assertGreater(self.store.get_state("source_cooldown"), 0)

    def test_redirect_is_not_followed(self):
        with patch.object(self.source.session, "get", return_value=self.response(302)) as get:
            with self.assertRaises(RuntimeError):
                self.source.raw_get(URL)
            self.assertFalse(get.call_args.kwargs["allow_redirects"])


class MonitorTests(unittest.TestCase):
    def test_full_cycle_restart_price_change_and_no_duplicate_alert(self):
        config = load_config(ROOT / "config.toml")
        config["source"]["categories"] = ["appartamenti"]
        config["monitor"]["catalog_pages_per_cycle"] = 1
        with tempfile.TemporaryDirectory() as directory:
            config["monitor"]["report_dir"] = directory
            store = Store(Path(directory) / "test.sqlite")
            source = Mock()
            def get(url):
                if url.endswith(".html"):
                    return '<p class="contenuti">Descrizione: Test</p><table><tr><td>Codice inserzione:</td><td>1</td></tr><tr><td>Prezzo</td><td>€ 300.000</td></tr><tr><td>Superficie (Mq) :</td><td>80,5 Mq</td></tr></table>'
                return card()
            source.get.side_effect = get
            with self.assertLogs("casa_watch.monitor", level="INFO") as logs:
                first = cycle(config, store, source)
            self.assertEqual(first["errors"], [])
            self.assertEqual(first["observed"], 1)
            self.assertTrue(any("NEW MATCH" in line for line in logs.output))
            store.close()
            store = Store(Path(directory) / "test.sqlite")
            try:
                with self.assertLogs("casa_watch.monitor", level="INFO") as logs:
                    cycle(config, store, source)
                self.assertFalse(any("NEW MATCH" in line for line in logs.output))
                source.get.side_effect = lambda url: card(price="280.000")
                with self.assertLogs("casa_watch.monitor", level="INFO") as logs:
                    cycle(config, store, source)
                self.assertTrue(any("PRICE CHANGE" in line for line in logs.output))
                self.assertEqual(store.get("1").previous_price, 300000)
            finally:
                store.close()

    def test_configuration_catches_typo_and_reversed_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text('[search]\nmax_prize = 100000\n')
            with self.assertRaises(ValueError):
                load_config(path)
            path.write_text('[search]\nmin_price = 100000\nmax_price = 100\n')
            with self.assertRaises(ValueError):
                load_config(path)

    def test_multiple_cycles_backoff_and_deadline_without_real_sleep(self):
        config = load_config(ROOT / "config.toml")
        fake_time = [0]
        def sleep(seconds):
            fake_time[0] += seconds
        with patch("casa_watch.monitor.cycle", side_effect=[{"errors": ["network"]}, {"errors": []}]) as cycle_mock:
            with patch("casa_watch.monitor.time.monotonic", side_effect=lambda: fake_time[0]), patch("casa_watch.monitor.time.sleep", side_effect=sleep) as wait:
                self.assertEqual(run(config, None, None, deadline=1800), 0)
                self.assertEqual(cycle_mock.call_count, 2)
                self.assertEqual([c.args[0] for c in wait.call_args_list], [1200, 600])

    def test_report_escapes_advert_content(self):
        config = load_config(ROOT / "config.toml")
        rows = rank([sample(title="<script>alert(1)</script>")], config["search"])
        status = dict(observed=1, checked_at="today", requests_today=1, daily_budget=10, details_pending=1)
        with tempfile.TemporaryDirectory() as directory:
            write_report(rows, status, directory)
            html = (Path(directory) / "index.html").read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", html)
            self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
