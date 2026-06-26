import unittest

from app import reports


class FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def fetch(self, query, params=None):
        self.calls.append((query, params or []))
        return self.rows


class ReportsTests(unittest.TestCase):
    def test_piece_cte_partitions_by_station_and_jsn(self):
        query = reports.piece_cte()

        self.assertIn("PARTITION BY source_station, jsn", query)
        self.assertIn("selected.source_station IS NOT DISTINCT FROM raw.source_station", query)
        self.assertIn("GROUP BY raw.source_station, raw.jsn", query)

    def test_station_summary_groups_by_source_station(self):
        db = FakeDb(
            [
                {
                    "source_station": "station-a",
                    "total_pieces": 4,
                    "ok_pieces": 3,
                    "nok_pieces": 1,
                    "pct_ok": 0.75,
                    "pct_nok": 0.25,
                }
            ]
        )

        result = reports.get_station_summary(db)

        query, _ = db.calls[0]
        self.assertIn("GROUP BY source_station", query)
        self.assertEqual(result["items"][0]["source_station"], "station-a")
        self.assertEqual(result["items"][0]["pct_nok"], 0.25)

    def test_station_timeseries_groups_by_station_and_bucket(self):
        db = FakeDb([])

        reports.get_station_timeseries(db, bucket="day")

        query, params = db.calls[0]
        self.assertIn("GROUP BY source_station, date_trunc", query)
        self.assertEqual(params, ["day", "day"])


if __name__ == "__main__":
    unittest.main()
