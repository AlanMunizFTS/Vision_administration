import unittest

from app import reports


class FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.calls = []

    def fetch(self, query, params=None):
        self.calls.append((query, params or []))
        return self.rows


class SequencedDb:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def fetch(self, query, params=None):
        self.calls.append((query, params or []))
        return self.responses[len(self.calls) - 1]


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

    def test_reject_summary_returns_excel_shaped_collections(self):
        db = SequencedDb(
            [
                [{"source_station": "Tesla 1 - Left", "total_pieces": 10, "ok_pieces": 7, "nok_pieces": 3}],
                [{"source_station": "Tesla 1 - Left", "reject_date": "2026-06-01", "pct_nok": 0.3}],
                [{"source_station": "Tesla 1 - Left", "class_name": "WRINKLE", "nok_pieces": 3}],
                [{"source_station": "Tesla 1 - Left", "class_name": "WRINKLE", "nok_pieces": 3}],
                [{"source_station": "Tesla 1 - Left", "class_name": "WRINKLE", "reject_date": "2026-06-01"}],
            ]
        )

        result = reports.get_reject_summary(db, source_station="Tesla 1 - Left")

        self.assertEqual(set(result), {"stations", "daily", "condition_periods", "condition_totals", "top3_history"})
        self.assertEqual(result["stations"][0]["source_station"], "Tesla 1 - Left")
        self.assertEqual(len(db.calls), 5)
        for _, params in db.calls:
            self.assertEqual(params, ["Tesla 1 - Left"])

    def test_reject_summary_groups_by_day_station_and_top3_class(self):
        db = SequencedDb([[], [], [], [], []])

        reports.get_reject_summary(db)

        daily_query = db.calls[1][0]
        condition_query = db.calls[2][0]
        top3_query = db.calls[4][0]
        self.assertIn("date_trunc('day', captured_at)::date", daily_query)
        self.assertIn("GROUP BY source_station, date_trunc('day', captured_at)::date", daily_query)
        self.assertIn("day_bounds", condition_query)
        self.assertIn("CASE WHEN model_result = 'OK' THEN 'OK' ELSE condition_name END", condition_query)
        self.assertIn("ROW_NUMBER() OVER", top3_query)
        self.assertIn("class_rank <= 3", top3_query)

    def test_defect_aggregates_use_canonical_names_and_alpha_order(self):
        db = FakeDb([])

        reports.get_defects(db)
        reports.get_station_defects(db)

        defects_query = db.calls[0][0]
        station_defects_query = db.calls[1][0]
        self.assertIn("COALESCE(NULLIF(UPPER(TRIM(main_defect)), ''), 'UNCLASSIFIED') AS class_name", defects_query)
        self.assertIn("GROUP BY COALESCE(NULLIF(UPPER(TRIM(main_defect)), ''), 'UNCLASSIFIED')", defects_query)
        self.assertIn("ORDER BY class_name ASC", defects_query)
        self.assertNotIn("ORDER BY piece_count DESC", defects_query)
        self.assertIn("ORDER BY source_station ASC NULLS LAST, class_name ASC", station_defects_query)

    def test_reject_summary_uses_canonical_condition_names_and_alpha_condition_order(self):
        db = SequencedDb([[], [], [], [], []])

        reports.get_reject_summary(db)

        filtered_query = db.calls[2][0]
        totals_query = db.calls[3][0]
        self.assertIn("COALESCE(NULLIF(UPPER(TRIM(main_defect)), ''), 'UNCLASSIFIED') AS condition_name", filtered_query)
        self.assertIn("ORDER BY reject_date ASC, source_station ASC NULLS LAST, class_name ASC", filtered_query)
        self.assertIn("ORDER BY source_station ASC NULLS LAST, class_name ASC", totals_query)


if __name__ == "__main__":
    unittest.main()
