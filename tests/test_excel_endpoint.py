import unittest
from datetime import datetime
from inspect import signature
from unittest.mock import patch

from app import main


EMPTY_REJECT_SUMMARY = {
    "stations": [],
    "daily": [],
    "condition_periods": [],
    "condition_totals": [],
    "top3_history": [],
}


class FakeWorkbook:
    def save(self, stream):
        stream.write(b"excel")


class ExcelEndpointTests(unittest.TestCase):
    def test_excel_report_uses_explicit_dates_and_station_only(self):
        fake_db = object()
        with patch.object(main.reports, "get_reject_summary", return_value=EMPTY_REJECT_SUMMARY) as get_reject_summary:
            response = main.excel_report(
                start_at="2026-06-19 00:00:00",
                end_at="2026-06-26 23:59:59",
                source_station="station-a",
                source_id=2,
                db=fake_db,
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        get_reject_summary.assert_called_once_with(
            fake_db,
            start_at="2026-06-19 00:00:00",
            end_at="2026-06-26 23:59:59",
            source_station="station-a",
        )

    def test_excel_report_does_not_declare_deprecated_jsn_query_param(self):
        self.assertNotIn("jsn", signature(main.excel_report).parameters)

    def test_excel_report_from_summary_uses_payload_without_db_query(self):
        with patch.object(main.reports, "get_reject_summary") as get_reject_summary:
            response = main.excel_report_from_summary(
                {
                    "filters": {
                        "start_at": "2026-06-19 00:00:00",
                        "end_at": "2026-06-26 23:59:59",
                        "source_station": "station-a",
                    },
                    "data": EMPTY_REJECT_SUMMARY,
                }
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        get_reject_summary.assert_not_called()

    def test_excel_report_from_summary_accepts_source_stations_array(self):
        with patch.object(main, "build_workbook", return_value=FakeWorkbook()) as build_workbook:
            response = main.excel_report_from_summary(
                {
                    "filters": {
                        "start_at": "2026-06-19 00:00:00",
                        "end_at": "2026-06-26 23:59:59",
                        "source_stations": ["station-a", "station-b"],
                    },
                    "data": EMPTY_REJECT_SUMMARY,
                }
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        report_params = build_workbook.call_args.args[0]
        self.assertEqual(report_params.source_station, "station-a, station-b")

    def test_excel_report_from_summary_accepts_station_pairs_array(self):
        with patch.object(main, "build_workbook", return_value=FakeWorkbook()) as build_workbook:
            response = main.excel_report_from_summary(
                {
                    "filters": {
                        "start_at": "2026-06-19 00:00:00",
                        "end_at": "2026-06-26 23:59:59",
                        "station_pairs": ["ART_ENDFORM_1859", "ART_ENDFORM_1862"],
                    },
                    "data": EMPTY_REJECT_SUMMARY,
                }
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        report_params = build_workbook.call_args.args[0]
        self.assertEqual(report_params.source_station, "ART_ENDFORM_1859, ART_ENDFORM_1862")

    def test_excel_report_from_summary_accepts_part_numbers_array(self):
        with patch.object(main, "build_workbook", return_value=FakeWorkbook()) as build_workbook:
            response = main.excel_report_from_summary(
                {
                    "filters": {
                        "start_at": "2026-06-19 00:00:00",
                        "end_at": "2026-06-26 23:59:59",
                        "part_numbers": ["PN-1", "PN-2"],
                    },
                    "data": EMPTY_REJECT_SUMMARY,
                }
            )

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        report_params = build_workbook.call_args.args[0]
        self.assertEqual(report_params.part_numbers, ["PN-1", "PN-2"])

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
