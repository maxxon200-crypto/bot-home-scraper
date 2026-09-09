from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from casa_watch.locations import locate
from casa_watch.models import Home
from casa_watch.report import brief, write_report
from casa_watch.storage import Store


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.home = Home("1", "https://www.case24.it/1.html", "Apartment", "Milano", "apartment", 200000, 60)
        self.index = {"via prova": {"12": ["Via Prova, 12", 45.46, 9.19]}, "via esempio": {"3": ["Via Esempio, 3", 45.48, 9.21]}}

    def test_complete_address_required(self):
        found = locate(replace(self.home, description="In via Prova, 12 proponiamo un appartamento."), self.index)
        self.assertEqual((found.latitude, found.longitude), (45.46, 9.19))
        self.assertIsNone(locate(replace(self.home, description="In via Prova proponiamo un appartamento."), self.index).latitude)

    def test_ambiguous_nearby_and_wrong_city_not_mapped(self):
        for description in ("In via prova 12 e in via esempio 3", "Vicino alla fermata di via prova 12"):
            self.assertIsNone(locate(replace(self.home, description=description), self.index).latitude)
        self.assertIsNone(locate(replace(self.home, city="Roma", description="via prova 12"), self.index).latitude)

    def test_location_update_does_not_fake_freshness(self):
        store = Store(":memory:")
        try:
            store.save(self.home, now="2026-01-01T00:00:00+00:00")
            changed = locate(replace(store.get("1"), description="via prova 12"), self.index)
            store.update_location(changed)
            self.assertEqual(store.get("1").last_seen, "2026-01-01T00:00:00+00:00")
            self.assertEqual(store.db.execute("select count(*) from prices").fetchone()[0], 1)
        finally:
            store.close()

    def test_short_factual_summary(self):
        self.assertEqual(brief(replace(self.home, furnished=True, garden=True)), "Furnished · Garden listed")
        self.assertLessEqual(len(brief(replace(self.home, description="Some actual advert text. " * 30))), 110)

    def test_removed_copy_does_not_return_on_regeneration(self):
        with tempfile.TemporaryDirectory() as directory:
            write_report([], {"checked_at":"today"}, directory)
            html=(Path(directory)/"index.html").read_text(encoding="utf-8")
            for removed in ("Your next home, in view", "Coverage is a growing sample", "Last fully successful", "Last attempt:", "This report refreshes"):
                self.assertNotIn(removed, html)


if __name__ == "__main__":
    unittest.main()
