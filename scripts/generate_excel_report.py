import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_DAYS = 30
DEFAULT_OUTPUT_DIR = "reports"
REQUEST_TIMEOUT_SECONDS = 20


class ReportError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReportParams:
    api_url: str
    start_at: str
    end_at: str
    source_station: str | None = None
    source_id: int | None = None
    output_dir: str = DEFAULT_OUTPUT_DIR


def parse_datetime(value, name):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ReportError(f"{name} must use ISO datetime format") from exc


def default_period(days):
    end_at = datetime.now().replace(microsecond=0)
    start_at = (end_at - timedelta(days=days)).replace(microsecond=0)
    return start_at, end_at


def build_params(args):
    if args.start_at or args.end_at:
        if not args.start_at or not args.end_at:
            raise ReportError("--start-at and --end-at must be used together")
        start_at = parse_datetime(args.start_at, "--start-at")
        end_at = parse_datetime(args.end_at, "--end-at")
    else:
        start_at, end_at = default_period(args.days)

    if end_at < start_at:
        raise ReportError("--end-at must be greater than or equal to --start-at")

    return ReportParams(
        api_url=args.api_url.rstrip("/"),
        start_at=start_at.isoformat(sep=" ", timespec="seconds"),
        end_at=end_at.isoformat(sep=" ", timespec="seconds"),
        source_station=args.source_station,
        source_id=args.source_id,
        output_dir=args.output_dir,
    )


def _request_json(session, url, params=None):
    try:
        response = session.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise ReportError(f"API request failed: {url} ({exc})") from exc
    except ValueError as exc:
        raise ReportError(f"API returned invalid JSON: {url}") from exc


def fetch_report_data(report_params, session=None):
    session = session or requests.Session()
    health = _request_json(session, f"{report_params.api_url}/health")
    if health.get("api") != "ok" or health.get("database") != "ok":
        detail = health.get("detail") or health
        raise ReportError(f"API health check failed: {detail}")

    common_params = {
        "start_at": report_params.start_at,
        "end_at": report_params.end_at,
    }
    if report_params.source_station:
        common_params["source_station"] = report_params.source_station
    if report_params.source_id is not None:
        common_params["source_id"] = report_params.source_id

    return {
        "summary": _request_json(
            session,
            f"{report_params.api_url}/api/v1/summary",
            params=common_params,
        ),
        "defects": _request_json(
            session,
            f"{report_params.api_url}/api/v1/defects",
            params=common_params,
        ),
        "timeseries_hour": _request_json(
            session,
            f"{report_params.api_url}/api/v1/timeseries",
            params={**common_params, "bucket": "hour"},
        ),
        "timeseries_day": _request_json(
            session,
            f"{report_params.api_url}/api/v1/timeseries",
            params={**common_params, "bucket": "day"},
        ),
    }


def _normalize_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_int(value):
    return int(_normalize_number(value, 0))


def _safe_sheet_title(title):
    return title[:31]


def _style_sheet(sheet):
    header_fill = PatternFill(fill_type="solid", fgColor="404040")
    header_font = Font(color="FFFFFF", bold=True)
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    sheet.freeze_panes = "A2"


def _fit_columns(sheet, max_width=42):
    for column_cells in sheet.columns:
        column_letter = column_cells[0].column_letter
        width = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_letter].width = min(max(width + 2, 12), max_width)


def _add_table(sheet, table_name, max_col=None):
    max_row = max(sheet.max_row, 2)
    max_col = max_col or sheet.max_column
    if sheet.max_row < 2:
        sheet.append([""] * max_col)
    ref = f"A1:{sheet.cell(row=max_row, column=max_col).coordinate}"
    table = Table(displayName=table_name, ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)


def _write_timeseries_sheet(workbook, title, table_name, rows, chart_kind):
    sheet = workbook.create_sheet(_safe_sheet_title(title))
    sheet.append(["Periodo", "Total", "OK", "NOK", "% OK", "% NOK"])
    for row in rows:
        total = _normalize_int(row.get("total_pieces"))
        ok = _normalize_int(row.get("ok_pieces"))
        nok = _normalize_int(row.get("nok_pieces"))
        sheet.append(
            [
                row.get("bucket_start") or "",
                total,
                ok,
                nok,
                ok / total if total else 0,
                nok / total if total else 0,
            ]
        )

    if not rows:
        sheet.append(["Sin datos", 0, 0, 0, 0, 0])

    for row_idx in range(2, sheet.max_row + 1):
        sheet.cell(row=row_idx, column=5).number_format = "0.00%"
        sheet.cell(row=row_idx, column=6).number_format = "0.00%"

    _style_sheet(sheet)
    _add_table(sheet, table_name)
    _fit_columns(sheet)

    chart = LineChart() if chart_kind == "line" else BarChart()
    chart.title = title
    chart.y_axis.title = "Piezas"
    chart.x_axis.title = "Periodo"
    chart.height = 8
    chart.width = 18
    data = Reference(sheet, min_col=3, max_col=4, min_row=1, max_row=sheet.max_row)
    categories = Reference(sheet, min_col=1, min_row=2, max_row=sheet.max_row)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    sheet.add_chart(chart, "H2")
    return sheet


def _write_defects_sheet(workbook, defects):
    rows = sorted(
        list(defects or []),
        key=lambda item: (-_normalize_int(item.get("piece_count")), str(item.get("class_name") or "")),
    )
    sheet = workbook.create_sheet("Defectos")
    sheet.append(["Defecto", "Piezas", "Confianza maxima", "Confianza promedio"])
    for row in rows:
        sheet.append(
            [
                row.get("class_name") or "UNCLASSIFIED",
                _normalize_int(row.get("piece_count")),
                _normalize_number(row.get("max_confidence")),
                _normalize_number(row.get("avg_confidence")),
            ]
        )
    if not rows:
        sheet.append(["Sin datos", 0, 0, 0])

    _style_sheet(sheet)
    _add_table(sheet, "tblDefectos")
    _fit_columns(sheet)

    top_count = min(max(len(rows), 1), 3)
    chart = BarChart()
    chart.title = "Top 3 defectos"
    chart.y_axis.title = "Piezas"
    chart.x_axis.title = "Defecto"
    chart.height = 8
    chart.width = 14
    data = Reference(sheet, min_col=2, min_row=1, max_row=top_count + 1)
    categories = Reference(sheet, min_col=1, min_row=2, max_row=top_count + 1)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(categories)
    sheet.add_chart(chart, "F2")
    return sheet


def _write_summary_sheet(workbook, report_params, summary):
    sheet = workbook.active
    sheet.title = "Resumen"
    total = _normalize_int(summary.get("total_pieces"))
    ok = _normalize_int(summary.get("ok_pieces"))
    nok = _normalize_int(summary.get("nok_pieces"))

    rows = [
        ("Periodo inicio", report_params.start_at),
        ("Periodo fin", report_params.end_at),
        ("Total piezas", total),
        ("OK", ok),
        ("NOK", nok),
        ("% OK", ok / total if total else 0),
        ("% NOK", nok / total if total else 0),
    ]
    sheet.append(["Metrica", "Valor"])
    for label, value in rows:
        sheet.append([label, value])
    sheet["B6"].number_format = "0.00%"
    sheet["B7"].number_format = "0.00%"

    sheet["D1"] = "Resultado"
    sheet["E1"] = "Piezas"
    sheet["D2"] = "OK"
    sheet["E2"] = ok
    sheet["D3"] = "NOK"
    sheet["E3"] = nok

    _style_sheet(sheet)
    _add_table(sheet, "tblResumen", max_col=2)
    _fit_columns(sheet)

    pie = PieChart()
    pie.title = "OK vs NOK"
    data = Reference(sheet, min_col=5, min_row=1, max_row=3)
    labels = Reference(sheet, min_col=4, min_row=2, max_row=3)
    pie.add_data(data, titles_from_data=True)
    pie.set_categories(labels)
    pie.height = 8
    pie.width = 10
    sheet.add_chart(pie, "G2")
    return sheet


def _write_dashboard_sheet(workbook, report_params, summary, defects):
    sheet = workbook.create_sheet("Dashboard", 0)
    total = _normalize_int(summary.get("total_pieces"))
    ok = _normalize_int(summary.get("ok_pieces"))
    nok = _normalize_int(summary.get("nok_pieces"))
    top_defects = sorted(
        list(defects or []),
        key=lambda item: (-_normalize_int(item.get("piece_count")), str(item.get("class_name") or "")),
    )[:3]

    sheet.append(["Reporte Vision", ""])
    sheet.append(["Periodo inicio", report_params.start_at])
    sheet.append(["Periodo fin", report_params.end_at])
    sheet.append(["Total piezas", total])
    sheet.append(["OK", ok])
    sheet.append(["NOK", nok])
    sheet.append(["% OK", ok / total if total else 0])
    sheet.append(["% NOK", nok / total if total else 0])
    sheet["B7"].number_format = "0.00%"
    sheet["B8"].number_format = "0.00%"

    sheet["D1"] = "Resultado"
    sheet["E1"] = "Piezas"
    sheet["D2"] = "OK"
    sheet["E2"] = ok
    sheet["D3"] = "NOK"
    sheet["E3"] = nok

    sheet["D6"] = "Defecto"
    sheet["E6"] = "Piezas"
    if top_defects:
        for idx, defect in enumerate(top_defects, start=7):
            sheet.cell(row=idx, column=4, value=defect.get("class_name") or "UNCLASSIFIED")
            sheet.cell(row=idx, column=5, value=_normalize_int(defect.get("piece_count")))
    else:
        sheet["D7"] = "Sin datos"
        sheet["E7"] = 0

    for cell in sheet[1]:
        cell.font = Font(bold=True)

    pie = PieChart()
    pie.title = "OK vs NOK"
    pie.add_data(Reference(sheet, min_col=5, min_row=1, max_row=3), titles_from_data=True)
    pie.set_categories(Reference(sheet, min_col=4, min_row=2, max_row=3))
    pie.height = 8
    pie.width = 10
    sheet.add_chart(pie, "G2")

    bar = BarChart()
    bar.title = "Top 3 defectos"
    bar.y_axis.title = "Piezas"
    bar.add_data(Reference(sheet, min_col=5, min_row=6, max_row=9), titles_from_data=True)
    bar.set_categories(Reference(sheet, min_col=4, min_row=7, max_row=9))
    bar.height = 8
    bar.width = 12
    sheet.add_chart(bar, "G18")
    _fit_columns(sheet)
    return sheet


def build_workbook(report_params, data):
    workbook = Workbook()
    summary = data.get("summary") or {}
    defects = (data.get("defects") or {}).get("items") or []
    hour_rows = (data.get("timeseries_hour") or {}).get("items") or []
    day_rows = (data.get("timeseries_day") or {}).get("items") or []

    _write_summary_sheet(workbook, report_params, summary)
    _write_timeseries_sheet(workbook, "Por hora", "tblPorHora", hour_rows, "bar")
    _write_timeseries_sheet(workbook, "Por dia", "tblPorDia", day_rows, "line")
    _write_defects_sheet(workbook, defects)
    _write_dashboard_sheet(workbook, report_params, summary, defects)
    return workbook


def save_workbook(workbook, output_dir):
    report_dir = Path(output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"vision_report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    workbook.save(output_path)
    return output_path


def generate_report(report_params, session=None):
    data = fetch_report_data(report_params, session=session)
    workbook = build_workbook(report_params, data)
    return save_workbook(workbook, report_params.output_dir)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Generate aggregated Vision Excel report.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--start-at")
    parser.add_argument("--end-at")
    parser.add_argument("--source-station")
    parser.add_argument("--source-id", type=int)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv=None):
    try:
        args = parse_args(argv)
        if args.days < 1:
            raise ReportError("--days must be greater than zero")
        report_params = build_params(args)
        output_path = generate_report(report_params)
    except ReportError as exc:
        print(f"Error: {exc}")
        return 1

    print(f"Reporte generado: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
