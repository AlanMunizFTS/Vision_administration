import unittest
from datetime import date

from app import change_log


class FakeChangeLogDb:
    def __init__(self, fetch_one_rows=None, fetch_rows=None):
        self.fetch_one_rows = list(fetch_one_rows or [])
        self.fetch_rows = list(fetch_rows or [])
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
            "employee_id": 7,
        }

    def fetch(self, query, params=None):
        self.calls.append((query, params or []))
        if self.fetch_rows:
            return self.fetch_rows.pop(0)
        return []


class ChangeLogTests(unittest.TestCase):
    def test_create_employee_trims_values(self):
        db = FakeChangeLogDb(fetch_one_rows=[{
            "id": 7,
            "employee_number": "2102",
            "full_name": "Tavitas Salazar, Tiberio",
        }])

        row = change_log.create_employee(
            db,
            employee_number=" 2102 ",
            full_name=" Tavitas Salazar, Tiberio ",
        )

        self.assertEqual(row["employee_number"], "2102")
        self.assertEqual(row["full_name"], "Tavitas Salazar, Tiberio")
        _, params = db.calls[0]
        self.assertEqual(params, ["2102", "Tavitas Salazar, Tiberio"])

    def test_create_employee_allows_blank_number(self):
        db = FakeChangeLogDb(fetch_one_rows=[{
            "id": 7,
            "employee_number": None,
            "full_name": "User Name",
        }])

        row = change_log.create_employee(db, employee_number=" ", full_name="User Name")

        self.assertIsNone(row["employee_number"])
        _, params = db.calls[0]
        self.assertEqual(params, [None, "User Name"])

    def test_create_employee_rejects_blank_name(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "full_name is required"):
            change_log.create_employee(db, employee_number="2102", full_name=" ")

        self.assertEqual(db.calls, [])

    def test_create_employee_rejects_long_number(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "employee_number must be at most 10 characters"):
            change_log.create_employee(db, employee_number="12345678901", full_name="User Name")

        self.assertEqual(db.calls, [])

    def test_create_employee_rejects_long_name(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "full_name must be at most 50 characters"):
            change_log.create_employee(db, employee_number="2102", full_name="A" * 51)

        self.assertEqual(db.calls, [])

    def test_create_employee_rejects_duplicate_number(self):
        db = FakeChangeLogDb(fetch_one_rows=[None])

        with self.assertRaisesRegex(ValueError, "employee_number already exists"):
            change_log.create_employee(db, employee_number="2102", full_name="User Name")

        self.assertEqual(len(db.calls), 1)

    def test_update_employee_trims_values(self):
        db = FakeChangeLogDb(fetch_one_rows=[None, {
            "id": 7,
            "employee_number": "2103",
            "full_name": "Updated Name",
        }])

        row = change_log.update_employee(
            db,
            7,
            employee_number=" 2103 ",
            full_name=" Updated Name ",
        )

        self.assertEqual(row["employee_number"], "2103")
        self.assertEqual(row["full_name"], "Updated Name")
        _, params = db.calls[1]
        self.assertEqual(params, ["2103", "Updated Name", 7])

    def test_update_employee_rejects_duplicate_number(self):
        db = FakeChangeLogDb(fetch_one_rows=[{"id": 8}])

        with self.assertRaisesRegex(ValueError, "employee_number already exists"):
            change_log.update_employee(db, 7, employee_number="2102")

        self.assertEqual(len(db.calls), 1)

    def test_update_employee_allows_clearing_number(self):
        db = FakeChangeLogDb(fetch_one_rows=[{
            "id": 7,
            "employee_number": None,
            "full_name": "Updated Name",
        }])

        row = change_log.update_employee(db, 7, employee_number=" ")

        self.assertIsNone(row["employee_number"])
        _, params = db.calls[0]
        self.assertEqual(params, [None, 7])

    def test_update_employee_rejects_blank_name(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "full_name cannot be empty"):
            change_log.update_employee(db, 7, full_name=" ")

        self.assertEqual(db.calls, [])

    def test_update_employee_rejects_long_number(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "employee_number must be at most 10 characters"):
            change_log.update_employee(db, 7, employee_number="12345678901")

        self.assertEqual(db.calls, [])

    def test_update_employee_rejects_long_name(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "full_name must be at most 50 characters"):
            change_log.update_employee(db, 7, full_name="A" * 51)

        self.assertEqual(db.calls, [])

    def test_update_employee_requires_changes(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "nothing to update"):
            change_log.update_employee(db, 7)

        self.assertEqual(db.calls, [])

    def test_delete_employee_deletes_by_id(self):
        db = FakeChangeLogDb(fetch_one_rows=[{"id": 7}])

        change_log.delete_employee(db, 7)

        _, params = db.calls[0]
        self.assertEqual(params, [7])

    def test_delete_employee_rejects_missing_employee(self):
        db = FakeChangeLogDb(fetch_one_rows=[None])

        with self.assertRaisesRegex(ValueError, "employee not found"):
            change_log.delete_employee(db, 7)

        self.assertEqual(len(db.calls), 1)

    def test_create_entry_requires_description(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "description is required"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="  ",
                employee_id=7,
            )

        self.assertEqual(db.calls, [])

    def test_create_entry_trims_description(self):
        db = FakeChangeLogDb(fetch_one_rows=[{"id": 7}, {
            "id": 1,
            "station_pair": "ART_ENDFORM_1859",
            "side": "both",
            "change_date": date(2026, 7, 7),
            "change_time": None,
            "category": "Lots",
            "label": "Lots",
            "description": "Material lot change completed",
            "employee_id": 7,
        }])

        change_log.create_entry(
            db,
            station_pair="ART_ENDFORM_1859",
            change_date=date(2026, 7, 7),
            category="Lots",
            description="  Material lot change completed  ",
            employee_id=7,
        )

        _, params = db.calls[1]
        self.assertEqual(params[-1], "Material lot change completed")
        self.assertEqual(params[4], 7)

    def test_create_entry_requires_description_minimum_length(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "description must be at least 20 characters"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="short description",
                employee_id=7,
            )

        self.assertEqual(db.calls, [])

    def test_create_entry_requires_employee(self):
        db = FakeChangeLogDb()

        with self.assertRaisesRegex(ValueError, "employee_id is required"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="Material lot change completed",
            )

        self.assertEqual(db.calls, [])

    def test_create_entry_rejects_unknown_employee(self):
        db = FakeChangeLogDb(fetch_one_rows=[None])

        with self.assertRaisesRegex(ValueError, "employee not found"):
            change_log.create_entry(
                db,
                station_pair="ART_ENDFORM_1859",
                change_date=date(2026, 7, 7),
                category="Lots",
                description="Material lot change completed",
                employee_id=999,
            )

        self.assertEqual(len(db.calls), 1)

    def test_get_entries_keeps_legacy_logs_without_employee(self):
        db = FakeChangeLogDb(fetch_rows=[[
            {
                "id": 1,
                "station_pair": "ART_ENDFORM_1859",
                "side": "both",
                "change_date": date(2026, 7, 7),
                "change_time": None,
                "category": "Lots",
                "label": "Lots",
                "description": "Material lot change completed",
                "employee_id": None,
                "employee_number": None,
                "employee_name": None,
            }
        ]])

        rows = change_log.get_entries(db)

        self.assertIsNone(rows[0]["employee_id"])
        self.assertIsNone(rows[0]["employee_number"])
        self.assertIsNone(rows[0]["employee_name"])

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
