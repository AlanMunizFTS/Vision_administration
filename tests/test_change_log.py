import unittest
from datetime import date

from app import change_log


class FakeChangeLogDb:
    def __init__(self, fetch_one_rows=None):
        self.fetch_one_rows = list(fetch_one_rows or [])
        self.calls = []

    def fetch_one(self, query, params=None):
        self.calls.append((query, params or []))
        if self.fetch_one_rows:
            return self.fetch_one_rows.pop(0)
        return {
            "id": 1,
            "station_pair": "ART_ENDFORM_1859",
            "side": "both",
            "change_date": date(2026, 7, 7),
            "change_time": None,
            "category": "Lots",
            "label": "Lots",
            "description": "Material lot change",
        }


class ChangeLogTests(unittest.TestCase):
    def test_create_entry_requires_description(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "description is required"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="  ",
            )

        self.assertEqual(db.calls, [])

    def test_create_entry_trims_description(self):
        db = FakeChangeLogDb()

        change_log.create_entry(
            db,
            station_pair="ART_ENDFORM_1859",
            change_date=date(2026, 7, 7),
            category="Lots",
            description="  Material lot change completed  ",
        )

        _, params = db.calls[0]
        self.assertEqual(params[-1], "Material lot change completed")

    def test_create_entry_requires_description_minimum_length(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "description must be at least 20 characters"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="short description",
            )

        self.assertEqual(db.calls, [])

    def test_update_entry_rejects_explicit_blank_description(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "description is required"):
            change_log.update_entry(db, 1, description="")

        self.assertEqual(db.calls, [])

    def test_update_entry_without_description_remains_compatible(self):
        db = FakeChangeLogDb()

        change_log.update_entry(db, 1, side="left")

        _, params = db.calls[0]
        self.assertEqual(params, ["left", 1])


if __name__ == "__main__":
    unittest.main()
