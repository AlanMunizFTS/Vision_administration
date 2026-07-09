import unittest
from datetime import date, time

from app import scrap


class FakeDb:
    def __init__(self, rows=None, row=None):
        self.rows = rows or []
        self.row = row
        self.calls = []

    def fetch(self, query, params=None):
        self.calls.append((query, params or []))
        return self.rows

    def fetch_one(self, query, params=None):
        self.calls.append((query, params or []))
        return self.row


class ScrapTests(unittest.TestCase):
    def test_create_entry_accepts_whole_hour_and_positive_quantity(self):
        db = FakeDb(
            row={
                "id": 1,
                "station_pair": "ART_ENDFORM_1859",
                "scrap_date": date(2026, 7, 9),
                "scrap_time": time(7, 0),
                "quantity": 4,
            }
        )

        result = scrap.create_entry(db, "ART_ENDFORM_1859", date(2026, 7, 9), time(7, 0), 4)

        _, params = db.calls[0]
        self.assertEqual(params, ["ART_ENDFORM_1859", date(2026, 7, 9), time(7, 0), 4])
        self.assertEqual(result["scrap_time"], "07:00:00")

    def test_create_entry_rejects_non_whole_hour(self):
        db = FakeDb()

        with self.assertRaisesRegex(ValueError, "whole hour"):
            scrap.create_entry(db, "ART_ENDFORM_1859", date(2026, 7, 9), time(7, 30), 4)

    def test_create_entry_rejects_non_positive_quantity(self):
        db = FakeDb()

        with self.assertRaisesRegex(ValueError, "greater than 0"):
            scrap.create_entry(db, "ART_ENDFORM_1859", date(2026, 7, 9), time(7, 0), 0)

    def test_update_entry_rejects_empty_patch(self):
        db = FakeDb()

        with self.assertRaisesRegex(ValueError, "nothing to update"):
            scrap.update_entry(db, 1)

    def test_delete_entry_rejects_missing_entry(self):
        db = FakeDb(row=None)

        with self.assertRaisesRegex(ValueError, "not found"):
            scrap.delete_entry(db, 404)


if __name__ == "__main__":
    unittest.main()
