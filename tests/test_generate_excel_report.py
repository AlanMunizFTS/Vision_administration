import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from openpyxl import load_workbook

from scripts.generate_excel_report import (
    ReportParams,
    build_workbook,
    fetch_report_data,
    generate_report,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {}), timeout))
        if url.endswith("/health"):
            return FakeResponse({"api": "ok", "database": "ok"})
        if url.endswith("/api/v1/summary"):
            return FakeResponse(
                {
                    "total_pieces": 10,
                    "ok_pieces": 7,
                    "nok_pieces": 3,
                    "pct_ok": 0.7,
                    "pct_nok": 0.3,
                }
            )
        if url.endswith("/api/v1/defects"):
            return FakeResponse(
                {
                    "items": [
                        {"class_name": "scratch", "piece_count": 2, "max_confidence": 0.91, "avg_confidence": 0.8},
                        {"class_name": "dent", "piece_count": 1, "max_confidence": 0.82, "avg_confidence": 0.7},
                    ]
                }
            )
        if url.endswith("/api/v1/timeseries") and params.get("bucket") == "hour":
            return FakeResponse(
                {
                    "bucket": "hour",
                    "items": [
                        {"bucket_start": "2026-06-26 10:00:00", "total_pieces": 4, "ok_pieces": 3, "nok_pieces": 1},
                        {"bucket_start": "2026-06-26 11:00:00", "total_pieces": 6, "ok_pieces": 4, "nok_pieces": 2},
                    ],
                }
            )
        if url.endswith("/api/v1/timeseries") and params.get("bucket") == "day":
            return FakeResponse(
                {
                    "bucket": "day",
                    "items": [
                        {"bucket_start": "2026-06-26 00:00:00", "total_pieces": 10, "ok_pieces": 7, "nok_pieces": 3},
                    ],
                }
            )
        raise AssertionError(f"Unexpected URL: {url}")


class GenerateExcelReportTests(unittest.TestCase):
    def make_params(self, output_dir="reports"):
        return ReportParams(
            api_url="http://testserver",
            start_at="2026-05-27 00:00:00",
            end_at="2026-06-26 23:59:59",
            output_dir=output_dir,
        )

    def test_fetch_report_data_uses_aggregated_endpoints_only(self):
        session = FakeSession()
        data = fetch_report_data(self.make_params(), session=session)

        urls = [url for url, _, _ in session.calls]
        self.assertIn("http://testserver/api/v1/summary", urls)
        self.assertIn("http://testserver/api/v1/defects", urls)
        self.assertEqual(urls.count("http://testserver/api/v1/timeseries"), 2)
        self.assertFalse(any(url.endswith("/api/v1/pieces") for url in urls))
        self.assertEqual(data["summary"]["total_pieces"], 10)

    def test_fetch_report_data_sends_common_filters_to_each_report_endpoint(self):
        params = ReportParams(
            api_url="http://testserver",
            start_at="2026-05-27 00:00:00",
            end_at="2026-06-26 23:59:59",
            source_station="station-a",
            source_id=2,
        )
        session = FakeSession()

        fetch_report_data(params, session=session)

        report_calls = [call for call in session.calls if not call[0].endswith("/health")]
        for _, query_params, _ in report_calls:
            self.assertEqual(query_params["start_at"], params.start_at)
            self.assertEqual(query_params["end_at"], params.end_at)
            self.assertEqual(query_params["source_station"], "station-a")
            self.assertEqual(query_params["source_id"], 2)

    def test_build_workbook_creates_expected_sheets_tables_and_charts(self):
        session = FakeSession()
        params = self.make_params()
        workbook = build_workbook(params, fetch_report_data(params, session=session))

        self.assertEqual(
            workbook.sheetnames,
            ["Dashboard", "Resumen", "Por hora", "Por dia", "Defectos"],
        )
        self.assertIn("tblResumen", workbook["Resumen"].tables)
        self.assertIn("tblPorHora", workbook["Por hora"].tables)
        self.assertIn("tblPorDia", workbook["Por dia"].tables)
        self.assertIn("tblDefectos", workbook["Defectos"].tables)
        self.assertGreaterEqual(len(workbook["Dashboard"]._charts), 2)
        self.assertGreaterEqual(len(workbook["Resumen"]._charts), 1)
        self.assertGreaterEqual(len(workbook["Defectos"]._charts), 1)

    def test_generate_report_writes_xlsx_file(self):
        session = FakeSession()
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = generate_report(self.make_params(output_dir=tmp_dir), session=session)

            self.assertTrue(Path(output_path).exists())
            workbook = load_workbook(output_path)
            self.assertIn("Dashboard", workbook.sheetnames)
            self.assertEqual(workbook["Resumen"]["B4"].value, 10)

    def test_empty_data_still_creates_workbook(self):
        params = self.make_params()
        data = {
            "summary": {"total_pieces": 0, "ok_pieces": 0, "nok_pieces": 0},
            "defects": {"items": []},
            "timeseries_hour": {"items": []},
            "timeseries_day": {"items": []},
        }

        workbook = build_workbook(params, data)

        self.assertEqual(workbook["Por hora"]["A2"].value, "Sin datos")
        self.assertEqual(workbook["Defectos"]["A2"].value, "Sin datos")


if __name__ == "__main__":
    unittest.main()
