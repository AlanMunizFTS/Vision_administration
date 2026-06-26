import argparse
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import requests
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_DAYS = 7
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
    output_dir: str = DEFAULT_OUTPUT_DIR


def parse_datetime(value, name):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError as exc:
        raise ReportError(f"{name} must use ISO datetime format") from exc


def default_period(days=DEFAULT_DAYS):
    end_at = datetime.now().replace(hour=23, minute=59, second=59, microsecond=0)
    start_at = (end_at - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
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

    params = {
        "start_at": report_params.start_at,
        "end_at": report_params.end_at,
    }
    if report_params.source_station:
        params["source_station"] = report_params.source_station

    return _request_json(
        session,
        f"{report_params.api_url}/api/v1/reject-summary",
        params=params,
    )


def _normalize_number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_int(value):
    return int(_normalize_number(value, 0))


def _date_label(value):
    return str(value or "")[:10]


def _station_name(value):
    return value or "Sin estacion"


def _safe_sheet_title(title):
    cleaned = re.sub(r"[\[\]:*?/\\]", "-", str(title or "Sheet")).strip()
    return (cleaned or "Sheet")[:31]


def _safe_table_name(name):
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(name or "Table"))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"tbl_{cleaned}"
    return cleaned[:200]


def _style_header(sheet, row_idx, min_col=1, max_col=None):
    max_col = max_col or sheet.max_column
    header_fill = PatternFill(fill_type="solid", fgColor="404040")
    header_font = Font(color="FFFFFF", bold=True)
    for col_idx in range(min_col, max_col + 1):
        cell = sheet.cell(row=row_idx, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _fit_columns(sheet, max_width=42):
    for column_cells in sheet.columns:
        column_letter = column_cells[0].column_letter
        width = max(len(str(cell.value or "")) for cell in column_cells)
        sheet.column_dimensions[column_letter].width = min(max(width + 2, 12), max_width)


def _add_table(sheet, table_name, header_row, min_col, max_row, max_col):
    ref = f"{sheet.cell(row=header_row, column=min_col).coordinate}:{sheet.cell(row=max_row, column=max_col).coordinate}"
    table = Table(displayName=_safe_table_name(table_name), ref=ref)
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False,
    )
    sheet.add_table(table)


def _append_table(sheet, table_name, headers, rows, start_row=None, start_col=1):
    start_row = start_row or sheet.max_row + 1
    if sheet.max_row == 1 and sheet.cell(row=1, column=1).value is None:
        start_row = 1
    rows = list(rows or [])
    if not rows:
        rows = [["Sin datos", *[""] * (len(headers) - 1)]]

    for offset, value in enumerate(headers):
        sheet.cell(row=start_row, column=start_col + offset, value=value)
    _style_header(sheet, start_row, start_col, start_col + len(headers) - 1)

    for row_idx, row in enumerate(rows, start=start_row + 1):
        for col_offset, value in enumerate(row):
            sheet.cell(row=row_idx, column=start_col + col_offset, value=value)

    max_row = start_row + len(rows)
    max_col = start_col + len(headers) - 1
    _add_table(sheet, table_name, start_row, start_col, max_row, max_col)
    return start_row, max_row, max_col


def _group_by(rows, key):
    grouped = {}
    for row in rows or []:
        group_key = row.get(key) or ""
        grouped.setdefault(group_key, []).append(row)
    return grouped


def _station_list(data):
    names = set()
    for collection in ("stations", "daily", "condition_periods", "condition_totals", "top3_history"):
        for row in data.get(collection) or []:
            names.add(row.get("source_station") or "")
    return sorted(names, key=_station_name)


def _condition_classes(rows):
    totals = {}
    for row in rows or []:
        class_name = row.get("class_name")
        nok_pieces = _normalize_int(row.get("nok_pieces"))
        if not class_name or class_name == "OK" or nok_pieces <= 0:
            continue
        totals[class_name] = totals.get(class_name, 0) + nok_pieces
    return [name for name, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))]


def _condition_daily_rows(rows, classes):
    by_date = {}
    for row in rows or []:
        class_name = row.get("class_name")
        nok_pieces = _normalize_int(row.get("nok_pieces"))
        if not class_name or class_name == "OK" or nok_pieces <= 0:
            continue
        day = _date_label(row.get("reject_date"))
        if not day:
            continue
        by_date.setdefault(day, {"reject_date": day, "total_nok": 0})
        by_date[day][class_name] = by_date[day].get(class_name, 0) + nok_pieces
        by_date[day]["total_nok"] += nok_pieces

    output = []
    for day in sorted(by_date):
        item = by_date[day]
        output.append([day, *[_normalize_int(item.get(name)) for name in classes], _normalize_int(item["total_nok"])])
    return output


def _top_history_rows(rows, classes):
    by_date = {}
    for row in rows or []:
        day = _date_label(row.get("reject_date"))
        class_name = row.get("class_name")
        if not day or not class_name:
            continue
        by_date.setdefault(day, {"reject_date": day})
        by_date[day][class_name] = _normalize_int(row.get("nok_pieces"))

    output = []
    for day in sorted(by_date):
        item = by_date[day]
        output.append([day, *[_normalize_int(item.get(name)) for name in classes]])
    return output


def _format_percentage_columns(sheet, columns, start_row=2):
    for col_idx in columns:
        for row_idx in range(start_row, sheet.max_row + 1):
            sheet.cell(row=row_idx, column=col_idx).number_format = "0.0%"


def _write_daily_sheet(workbook, data):
    sheet = workbook.active
    sheet.title = "Por dia"
    stations = _station_list(data)
    daily_rows = data.get("daily") or []
    dates = sorted({_date_label(row.get("reject_date")) for row in daily_rows if _date_label(row.get("reject_date"))})
    by_station_date = {
        (row.get("source_station") or "", _date_label(row.get("reject_date"))): row
        for row in daily_rows
    }

    headers = ["Fecha"]
    for station in stations:
        label = _station_name(station)
        headers.extend([f"{label} OK", f"{label} NOK", f"{label} Total", f"{label} % OK", f"{label} % NOK"])

    rows = []
    for day in dates:
        output = [day]
        for station in stations:
            row = by_station_date.get((station, day))
            if row:
                output.extend(
                    [
                        _normalize_int(row.get("ok_pieces")),
                        _normalize_int(row.get("nok_pieces")),
                        _normalize_int(row.get("total_pieces")),
                        _normalize_number(row.get("pct_ok")),
                        _normalize_number(row.get("pct_nok")),
                    ]
                )
            else:
                output.extend([0, 0, 0, "", ""])
        rows.append(output)

    if not headers[1:]:
        headers = ["Fecha", "Sin datos"]
    header_row, max_row, _ = _append_table(sheet, "tblPorDia", headers, rows)
    percent_cols = [5 + (idx * 5) for idx in range(len(stations))]
    percent_cols.extend([6 + (idx * 5) for idx in range(len(stations))])
    _format_percentage_columns(sheet, percent_cols, start_row=header_row + 1)
    sheet.freeze_panes = "A2"

    if rows and stations:
        chart = LineChart()
        chart.title = "Tasa de rechazo (% NOK) por dia"
        chart.y_axis.title = "% NOK"
        chart.x_axis.title = "Fecha"
        chart.height = 9
        chart.width = 18
        categories = Reference(sheet, min_col=1, min_row=header_row + 1, max_row=max_row)
        for idx, _station in enumerate(stations):
            col_idx = 6 + (idx * 5)
            values = Reference(sheet, min_col=col_idx, max_col=col_idx, min_row=header_row, max_row=max_row)
            chart.add_data(values, titles_from_data=True)
        chart.set_categories(categories)
        sheet.add_chart(chart, f"{get_column_letter(len(headers) + 2)}2")

    _fit_columns(sheet)
    return sheet


def _write_conditions_sheet(workbook, data):
    sheet = workbook.create_sheet("Per Condition")
    stations = _station_list(data)
    totals_by_station = _group_by(data.get("condition_totals") or [], "source_station")
    periods_by_station = _group_by(data.get("condition_periods") or [], "source_station")
    row_cursor = 1

    if not stations:
        _append_table(sheet, "tblConditionEmpty", ["Source Station", "Class Name", "NOK"], [])
        _fit_columns(sheet)
        return sheet

    for station_idx, station in enumerate(stations, start=1):
        label = _station_name(station)
        sheet.cell(row=row_cursor, column=1, value=f"{label} - Rechazos por clase")
        sheet.cell(row=row_cursor, column=1).font = Font(bold=True)
        row_cursor += 1

        totals = sorted(
            totals_by_station.get(station) or [],
            key=lambda item: (-_normalize_int(item.get("nok_pieces")), str(item.get("class_name") or "")),
        )
        total_rows = [
            [label, row.get("class_name") or "UNCLASSIFIED", _normalize_int(row.get("nok_pieces"))]
            for row in totals
        ]
        total_header, total_max_row, _ = _append_table(
            sheet,
            f"tblConditionTotals{station_idx}",
            ["Source Station", "Class Name", "NOK"],
            total_rows,
            start_row=row_cursor,
        )

        if total_rows:
            chart = PieChart()
            chart.title = f"{label} - Rechazos por clase"
            chart.height = 8
            chart.width = 12
            chart.add_data(Reference(sheet, min_col=3, min_row=total_header, max_row=total_max_row), titles_from_data=True)
            chart.set_categories(Reference(sheet, min_col=2, min_row=total_header + 1, max_row=total_max_row))
            sheet.add_chart(chart, "E" + str(total_header))

        row_cursor = total_max_row + 3
        sheet.cell(row=row_cursor, column=1, value=f"{label} - Defectos dia a dia")
        sheet.cell(row=row_cursor, column=1).font = Font(bold=True)
        row_cursor += 1

        periods = periods_by_station.get(station) or []
        classes = _condition_classes(periods)
        headers = ["Fecha", *classes, "Total NOK"] if classes else ["Fecha", "Total NOK"]
        daily_rows = _condition_daily_rows(periods, classes)
        _, daily_max_row, _ = _append_table(
            sheet,
            f"tblConditionDaily{station_idx}",
            headers,
            daily_rows,
            start_row=row_cursor,
        )
        row_cursor = daily_max_row + 3

    sheet.freeze_panes = "A2"
    _fit_columns(sheet)
    return sheet


def _write_top3_sheet(workbook, data):
    sheet = workbook.create_sheet("Top 3 Historico")
    stations = _station_list(data)
    history_by_station = _group_by(data.get("top3_history") or [], "source_station")
    row_cursor = 1

    if not stations:
        _append_table(sheet, "tblTop3Empty", ["Top", "Class Name", "NOK acumulado"], [])
        _fit_columns(sheet)
        return sheet

    for station_idx, station in enumerate(stations, start=1):
        label = _station_name(station)
        history = sorted(
            history_by_station.get(station) or [],
            key=lambda item: (
                _normalize_int(item.get("class_rank")) or 99,
                _date_label(item.get("reject_date")),
                str(item.get("class_name") or ""),
            ),
        )
        classes = []
        totals = {}
        ranks = {}
        for row in history:
            class_name = row.get("class_name")
            if not class_name or class_name in totals:
                continue
            classes.append(class_name)
            totals[class_name] = _normalize_int(row.get("total_nok_pieces"))
            ranks[class_name] = _normalize_int(row.get("class_rank"))

        sheet.cell(row=row_cursor, column=1, value=f"{label} - Top 3 NOK por dia")
        sheet.cell(row=row_cursor, column=1).font = Font(bold=True)
        row_cursor += 1

        summary_rows = [
            [ranks.get(name) or idx + 1, name, totals.get(name, 0)]
            for idx, name in enumerate(classes)
        ]
        _, summary_max_row, _ = _append_table(
            sheet,
            f"tblTop3Totals{station_idx}",
            ["Top", "Class Name", "NOK acumulado"],
            summary_rows,
            start_row=row_cursor,
        )

        row_cursor = summary_max_row + 2
        headers = ["Fecha", *classes] if classes else ["Fecha", "Sin datos"]
        chart_rows = _top_history_rows(history, classes)
        history_header, history_max_row, history_max_col = _append_table(
            sheet,
            f"tblTop3History{station_idx}",
            headers,
            chart_rows,
            start_row=row_cursor,
        )

        if chart_rows and classes:
            chart = BarChart()
            chart.title = f"{label} - Top 3 historico"
            chart.y_axis.title = "NOK"
            chart.x_axis.title = "Fecha"
            chart.height = 8
            chart.width = 16
            chart.add_data(
                Reference(sheet, min_col=2, max_col=history_max_col, min_row=history_header, max_row=history_max_row),
                titles_from_data=True,
            )
            chart.set_categories(Reference(sheet, min_col=1, min_row=history_header + 1, max_row=history_max_row))
            sheet.add_chart(chart, "E" + str(history_header))

        row_cursor = history_max_row + 4

    sheet.freeze_panes = "A2"
    _fit_columns(sheet)
    return sheet


def build_workbook(report_params, data):
    workbook = Workbook()
    _write_daily_sheet(workbook, data or {})
    _write_conditions_sheet(workbook, data or {})
    _write_top3_sheet(workbook, data or {})
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
    parser = argparse.ArgumentParser(description="Generate Vision Excel report based on the frontend reject summary.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--start-at")
    parser.add_argument("--end-at")
    parser.add_argument("--source-station")
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
