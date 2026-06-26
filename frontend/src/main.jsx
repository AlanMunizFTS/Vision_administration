import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Download, RefreshCw, Search } from "lucide-react";
import "./styles.css";

const PAGE_SIZE = 100;

function buildQuery(filters, extra = {}) {
  const params = new URLSearchParams();
  const merged = { ...filters, ...extra };
  for (const [key, value] of Object.entries(merged)) {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, value);
    }
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function toInputDateTime(value) {
  if (!value) return "";
  return String(value).replace(" ", "T").slice(0, 16);
}

function toApiDateTime(value) {
  if (!value) return "";
  return value.length === 16 ? `${value}:00` : value;
}

function numberFormat(value) {
  return new Intl.NumberFormat("es-MX").format(Number(value || 0));
}

function percentFormat(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function stationName(value) {
  return value || "Sin estacion";
}

function chartRows(items = []) {
  return items.map((item) => ({
    ...item,
    label: String(item.bucket_start || "").slice(0, 16),
    total_pieces: Number(item.total_pieces || 0),
    ok_pieces: Number(item.ok_pieces || 0),
    nok_pieces: Number(item.nok_pieces || 0)
  }));
}

function topDefects(items = []) {
  return [...items]
    .sort((a, b) => Number(b.piece_count || 0) - Number(a.piece_count || 0))
    .slice(0, 3)
    .map((item) => ({
      ...item,
      piece_count: Number(item.piece_count || 0)
    }));
}

function groupByStation(items = []) {
  return items.reduce((acc, item) => {
    const key = item.source_station || "";
    if (!acc[key]) acc[key] = [];
    acc[key].push(item);
    return acc;
  }, {});
}

function KpiStrip({ summary }) {
  const total = Number(summary?.total_pieces || 0);
  return (
    <div className="kpi-strip">
      <Kpi label="Total" value={numberFormat(total)} />
      <Kpi label="OK" value={numberFormat(summary?.ok_pieces)} tone="ok" />
      <Kpi label="NOK" value={numberFormat(summary?.nok_pieces)} tone="nok" />
      <Kpi label="% OK" value={percentFormat(summary?.pct_ok)} />
      <Kpi label="% NOK" value={percentFormat(summary?.pct_nok)} />
    </div>
  );
}

function Kpi({ label, value, tone }) {
  return (
    <div className={`kpi ${tone || ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DataChart({ title, type, rows }) {
  const safeRows = chartRows(rows);
  return (
    <section className="panel chart-panel">
      <div className="panel-title">{title}</div>
      <div className="chart-wrap">
        {safeRows.length ? (
          <ResponsiveContainer width="100%" height="100%">
            {type === "line" ? (
              <LineChart data={safeRows} margin={{ top: 14, right: 18, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={18} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="ok_pieces" name="OK" stroke="#2f7d50" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="nok_pieces" name="NOK" stroke="#b94b48" strokeWidth={2} dot={false} />
              </LineChart>
            ) : (
              <BarChart data={safeRows} margin={{ top: 14, right: 18, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                <XAxis dataKey="label" tick={{ fontSize: 11 }} minTickGap={18} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Bar dataKey="ok_pieces" name="OK" fill="#2f7d50" stackId="pieces" />
                <Bar dataKey="nok_pieces" name="NOK" fill="#b94b48" stackId="pieces" />
              </BarChart>
            )}
          </ResponsiveContainer>
        ) : (
          <div className="empty">Sin datos</div>
        )}
      </div>
    </section>
  );
}

function DefectTopChart({ rows }) {
  const data = topDefects(rows);
  return (
    <section className="panel chart-panel">
      <div className="panel-title">Top 3 defectos</div>
      <div className="chart-wrap compact">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 12, right: 20, bottom: 8, left: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
              <XAxis type="number" tick={{ fontSize: 11 }} />
              <YAxis dataKey="class_name" type="category" width={96} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="piece_count" name="Piezas" fill="#557aa5" />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty">Sin defectos</div>
        )}
      </div>
    </section>
  );
}

function DefectsTable({ rows }) {
  return (
    <section className="panel">
      <div className="panel-title">Defectos</div>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Defecto</th>
              <th>Piezas</th>
              <th>Conf. max</th>
              <th>Conf. prom</th>
            </tr>
          </thead>
          <tbody>
            {(rows || []).length ? (
              rows.map((row) => (
                <tr key={`${row.source_station || "global"}-${row.class_name}`}>
                  <td>{row.class_name || "UNCLASSIFIED"}</td>
                  <td>{numberFormat(row.piece_count)}</td>
                  <td>{Number(row.max_confidence || 0).toFixed(3)}</td>
                  <td>{Number(row.avg_confidence || 0).toFixed(3)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="4" className="empty-cell">Sin datos</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PiecesTable({ rows }) {
  return (
    <section className="panel wide">
      <div className="panel-title">Piezas</div>
      <div className="table-wrap pieces">
        <table>
          <thead>
            <tr>
              <th>JSN</th>
              <th>Resultado</th>
              <th>Capturado</th>
              <th>Defecto principal</th>
              <th>Confianza</th>
              <th>Imagenes</th>
              <th>Detecciones</th>
            </tr>
          </thead>
          <tbody>
            {(rows || []).length ? (
              rows.map((row) => (
                <tr key={`${row.source_station || "global"}-${row.jsn}`}>
                  <td>{row.jsn}</td>
                  <td><span className={`status ${row.model_result}`}>{row.model_result}</span></td>
                  <td>{row.captured_at || ""}</td>
                  <td>{row.main_defect || ""}</td>
                  <td>{row.main_confidence ? Number(row.main_confidence).toFixed(3) : ""}</td>
                  <td>{numberFormat(row.image_count)}</td>
                  <td>{numberFormat(row.detections_count)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="7" className="empty-cell">Sin piezas</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StationSection({ report }) {
  return (
    <section className="station-section">
      <div className="station-header">
        <h2>{stationName(report.source_station)}</h2>
        <span>{numberFormat(report.summary?.total_pieces)} piezas</span>
      </div>
      <KpiStrip summary={report.summary} />
      <div className="grid two">
        <DataChart title="Por hora" type="bar" rows={report.hourRows} />
        <DataChart title="Por dia" type="line" rows={report.dayRows} />
      </div>
      <div className="grid two">
        <DefectTopChart rows={report.defects} />
        <DefectsTable rows={report.defects} />
      </div>
      <PiecesTable rows={report.pieces} />
    </section>
  );
}

function App() {
  const [options, setOptions] = useState({ source_stations: [] });
  const [filters, setFilters] = useState({
    start_at: "",
    end_at: "",
    source_station: "",
    source_id: "",
    jsn: ""
  });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchJson("/api/v1/options")
      .then((payload) => {
        setOptions(payload);
        setFilters((current) => ({
          ...current,
          start_at: toInputDateTime(payload.min_captured_at),
          end_at: toInputDateTime(payload.max_captured_at)
        }));
      })
      .catch((exc) => setError(exc.message));
  }, []);

  const apiFilters = useMemo(
    () => ({
      start_at: toApiDateTime(filters.start_at),
      end_at: toApiDateTime(filters.end_at),
      source_station: filters.source_station,
      source_id: filters.source_id,
      jsn: filters.jsn.trim()
    }),
    [filters]
  );

  async function loadData() {
    setLoading(true);
    setError("");
    try {
      const stationBaseFilters = { ...apiFilters };
      delete stationBaseFilters.source_station;
      const [
        summary,
        defects,
        hour,
        day,
        stationSummary,
        stationDefects,
        stationHour,
        stationDay
      ] = await Promise.all([
        fetchJson(`/api/v1/summary${buildQuery(apiFilters)}`),
        fetchJson(`/api/v1/defects${buildQuery(apiFilters)}`),
        fetchJson(`/api/v1/timeseries${buildQuery(apiFilters, { bucket: "hour" })}`),
        fetchJson(`/api/v1/timeseries${buildQuery(apiFilters, { bucket: "day" })}`),
        fetchJson(`/api/v1/stations/summary${buildQuery(stationBaseFilters)}`),
        fetchJson(`/api/v1/stations/defects${buildQuery(stationBaseFilters)}`),
        fetchJson(`/api/v1/stations/timeseries${buildQuery(stationBaseFilters, { bucket: "hour" })}`),
        fetchJson(`/api/v1/stations/timeseries${buildQuery(stationBaseFilters, { bucket: "day" })}`)
      ]);

      let stationRows = stationSummary.items || [];
      if (apiFilters.source_station) {
        stationRows = stationRows.filter((row) => row.source_station === apiFilters.source_station);
      }

      const defectsByStation = groupByStation(stationDefects.items);
      const hourByStation = groupByStation(stationHour.items);
      const dayByStation = groupByStation(stationDay.items);
      const piecesResponses = await Promise.all(
        stationRows.map((row) =>
          fetchJson(
            `/api/v1/pieces${buildQuery(apiFilters, {
              source_station: row.source_station || "",
              limit: PAGE_SIZE
            })}`
          )
        )
      );

      const stationReports = stationRows.map((row, index) => {
        const key = row.source_station || "";
        return {
          source_station: row.source_station,
          summary: row,
          defects: defectsByStation[key] || [],
          hourRows: hourByStation[key] || [],
          dayRows: dayByStation[key] || [],
          pieces: piecesResponses[index]?.items || []
        };
      });

      setData({
        summary,
        defects: defects.items || [],
        hourRows: hour.items || [],
        dayRows: day.items || [],
        stationReports
      });
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (filters.start_at || filters.end_at) {
      loadData();
    }
  }, [apiFilters]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function downloadExcel() {
    window.location.href = `/api/v1/reports/excel${buildQuery(apiFilters)}`;
  }

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>Vision Administration</h1>
          <p>Representacion local por hora, por dia y por source station</p>
        </div>
        <div className="actions">
          <button type="button" onClick={loadData} disabled={loading} title="Actualizar">
            <RefreshCw size={17} />
            Actualizar
          </button>
          <button type="button" onClick={downloadExcel} title="Descargar Excel">
            <Download size={17} />
            Excel
          </button>
        </div>
      </header>

      <section className="filters">
        <label>
          Inicio
          <input type="datetime-local" value={filters.start_at} onChange={(event) => updateFilter("start_at", event.target.value)} />
        </label>
        <label>
          Fin
          <input type="datetime-local" value={filters.end_at} onChange={(event) => updateFilter("end_at", event.target.value)} />
        </label>
        <label>
          Source station
          <select value={filters.source_station} onChange={(event) => updateFilter("source_station", event.target.value)}>
            <option value="">Todas</option>
            {(options.source_stations || []).map((station) => (
              <option key={station} value={station}>{stationName(station)}</option>
            ))}
          </select>
        </label>
        <label>
          Source id
          <input value={filters.source_id} onChange={(event) => updateFilter("source_id", event.target.value)} inputMode="numeric" />
        </label>
        <label className="search-label">
          JSN
          <span>
            <Search size={16} />
            <input value={filters.jsn} onChange={(event) => updateFilter("jsn", event.target.value)} />
          </span>
        </label>
      </section>

      {error ? <div className="error">{error}</div> : null}
      {loading ? <div className="loading">Cargando datos...</div> : null}

      {data ? (
        <>
          <section className="global">
            <div className="station-header">
              <h2>Global</h2>
              <span>{data.stationReports.length} estaciones</span>
            </div>
            <KpiStrip summary={data.summary} />
            <div className="grid two">
              <DataChart title="Por hora" type="bar" rows={data.hourRows} />
              <DataChart title="Por dia" type="line" rows={data.dayRows} />
            </div>
            <div className="grid two">
              <DefectTopChart rows={data.defects} />
              <DefectsTable rows={data.defects} />
            </div>
          </section>

          {data.stationReports.map((report) => (
            <StationSection key={report.source_station || "blank"} report={report} />
          ))}
        </>
      ) : null}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
