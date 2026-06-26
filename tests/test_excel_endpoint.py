import unittest
from datetime import datetime
from unittest.mock import patch

from app import main


EMPTY_REJECT_SUMMARY = {
    "stations": [],
    "daily": [],
    "condition_periods": [],
    "condition_totals": [],
    "top3_history": [],
}


class ExcelEndpointTests(unittest.TestCase):
    def test_excel_report_uses_explicit_dates_and_station_only(self):
        fake_db = object()
        with patch.object(main.reports, "get_reject_summary", return_value=EMPTY_REJECT_SUMMARY) as get_reject_summary:
            response = main.excel_report(
                start_at="2026-06-19 00:00:00",
                end_at="2026-06-26 23:59:59",
                source_station="station-a",
                source_id=2,
                jsn="JSN001",
                db=fake_db,
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        get_reject_summary.assert_called_once_with(
            fake_db,
            start_at="2026-06-19 00:00:00",
            end_at="2026-06-26 23:59:59",
            source_station="station-a",
        )

    def test_excel_report_uses_default_period_when_dates_are_missing(self):
        fake_db = object()
        with patch.object(main, "default_period", return_value=(datetime(2026, 6, 19), datetime(2026, 6, 26, 23, 59, 59))):
            with patch.object(main.reports, "get_reject_summary", return_value=EMPTY_REJECT_SUMMARY) as get_reject_summary:
                main.excel_report(source_station="station-a", db=fake_db)

        get_reject_summary.assert_called_once_with(
            fake_db,
            start_at="2026-06-19 00:00:00",
            end_at="2026-06-26 23:59:59",
            source_station="station-a",
        )

    def test_excel_report_rejects_partial_date_range(self):
        with self.assertRaises(Exception) as context:
            main.excel_report(start_at="2026-06-19 00:00:00", db=object())

        self.assertIn("start_at and end_at must be used together", str(context.exception))


if __name__ == "__main__":
    unittest.main()
