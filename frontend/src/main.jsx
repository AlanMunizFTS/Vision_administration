import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Download, RefreshCw, Search } from "lucide-react";
import "./styles.css";

const TABS = [
  { id: "daily", label: "Por dia" },
  { id: "conditions", label: "Per Condition" },
  { id: "top3", label: "Top 3 Historico" }
];

const COLORS = ["#2f6f9f", "#c9564a", "#6f8f3f", "#d39b32", "#7259a4", "#3f8f88", "#8a5c3b", "#69717c"];

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

function dateLabel(value) {
  return String(value || "").slice(0, 10);
}

function stationName(value) {
  return value || "Sin estacion";
}

function groupBy(items = [], key) {
  return items.reduce((acc, item) => {
    const groupKey = item[key] || "";
    if (!acc[groupKey]) acc[groupKey] = [];
    acc[groupKey].push(item);
    return acc;
  }, {});
}

function stationList(data) {
  const names = new Set();
  for (const row of data?.stations || []) names.add(row.source_station || "");
  for (const row of data?.daily || []) names.add(row.source_station || "");
  for (const row of data?.condition_totals || []) names.add(row.source_station || "");
  for (const row of data?.top3_history || []) names.add(row.source_station || "");
  return [...names].sort((a, b) => stationName(a).localeCompare(stationName(b)));
}

function dailyChartRows(data, stations) {
  const byDate = {};
  for (const row of data?.daily || []) {
    const day = dateLabel(row.reject_date);
    if (!byDate[day]) byDate[day] = { reject_date: day };
    byDate[day][row.source_station || ""] = Number(row.pct_nok || 0) * 100;
  }
  return Object.values(byDate).sort((a, b) => a.reject_date.localeCompare(b.reject_date)).map((row) => {
    for (const station of stations) {
      if (row[station] === undefined) row[station] = null;
    }
    return row;
  });
}

function topHistoryRows(rows = []) {
  const byDate = {};
  for (const row of rows) {
    const day = dateLabel(row.reject_date);
    if (!byDate[day]) byDate[day] = { reject_date: day };
    byDate[day][row.class_name] = Number(row.nok_pieces || 0);
  }
  return Object.values(byDate).sort((a, b) => a.reject_date.localeCompare(b.reject_date));
}

function classNames(rows = []) {
  return [...new Set(rows.map((row) => row.class_name).filter(Boolean))];
}

function TabButton({ tab, active, onClick }) {
  return (
    <button type="button" className={`tab-button ${active ? "active" : ""}`} onClick={onClick}>
      {tab.label}
    </button>
  );
}

function Empty({ label = "Sin datos" }) {
  return <div className="empty">{label}</div>;
}

function DailyTab({ data, stations }) {
  const rows = dailyChartRows(data, stations);
  const byStation = groupBy(data?.daily || [], "source_station");

  return (
    <section className="tab-panel">
      <section className="panel">
        <div className="panel-title">Tasa de rechazo (% NOK) por dia</div>
        <div className="chart-wrap tall">
          {rows.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 14, right: 24, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                <XAxis dataKey="reject_date" tick={{ fontSize: 11 }} minTickGap={14} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(value) => `${value}%`} />
                <Tooltip formatter={(value) => (value === null ? "" : `${Number(value).toFixed(1)}%`)} />
                <Legend />
                {stations.map((station, index) => (
                  <Line
                    key={station || "blank"}
                    type="monotone"
                    dataKey={station}
                    name={stationName(station)}
                    stroke={COLORS[index % COLORS.length]}
                    strokeWidth={2}
                    dot={false}
                    connectNulls
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <Empty />
          )}
        </div>
      </section>

      <section className="panel">
        <div className="table-wrap daily">
          <table className="matrix-table">
            <thead>
              <tr>
                <th rowSpan="2">Date</th>
                {stations.map((station) => (
                  <th key={station || "blank"} colSpan="5">{stationName(station)}</th>
                ))}
              </tr>
              <tr>
                {stations.flatMap((station) => ["OK", "NOK", "Total", "% OK", "% NOK"].map((metric) => (
                  <th key={`${station}-${metric}`}>{metric}</th>
                )))}
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((chartRow) => (
                  <tr key={chartRow.reject_date}>
                    <td>{chartRow.reject_date}</td>
                    {stations.flatMap((station) => {
                      const row = (byStation[station] || []).find((item) => dateLabel(item.reject_date) === chartRow.reject_date);
                      return [
                        <td key={`${station}-ok-${chartRow.reject_date}`}>{numberFormat(row?.ok_pieces)}</td>,
                        <td key={`${station}-nok-${chartRow.reject_date}`}>{numberFormat(row?.nok_pieces)}</td>,
                        <td key={`${station}-total-${chartRow.reject_date}`}>{numberFormat(row?.total_pieces)}</td>,
                        <td key={`${station}-pct-ok-${chartRow.reject_date}`}>{row ? percentFormat(row.pct_ok) : ""}</td>,
                        <td key={`${station}-pct-nok-${chartRow.reject_date}`}>{row ? percentFormat(row.pct_nok) : ""}</td>
                      ];
                    })}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={1 + stations.length * 5} className="empty-cell">Sin datos</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function ConditionsTab({ data, stations }) {
  const periodsByStation = groupBy(data?.condition_periods || [], "source_station");
  const totalsByStation = groupBy(data?.condition_totals || [], "source_station");

  return (
    <section className="station-grid">
      {stations.length ? stations.map((station) => {
        const totals = totalsByStation[station] || [];
        const periods = periodsByStation[station] || [];
        return (
          <section className="panel station-card" key={station || "blank"}>
            <div className="panel-title">{stationName(station)}</div>
            <div className="condition-layout">
              <div className="chart-wrap pie">
                {totals.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={totals} dataKey="nok_pieces" nameKey="class_name" outerRadius={92} label>
                        {totals.map((_, index) => (
                          <Cell key={index} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value) => numberFormat(value)} />
                      <Legend />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <Empty label="Sin rechazos" />
                )}
              </div>
              <div className="table-wrap condition">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      <th>Periodo inicio</th>
                      <th>Periodo fin</th>
                      <th>Class Name</th>
                      <th>OK</th>
                      <th>NOK</th>
                      <th>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {periods.length ? periods.map((row, index) => (
                      <tr key={`${station}-${row.reject_date}-${row.class_name}-${index}`}>
                        <td>{dateLabel(row.reject_date)}</td>
                        <td>{String(row.period_start || "").slice(0, 19)}</td>
                        <td>{String(row.period_end || "").slice(0, 19)}</td>
                        <td>{row.class_name}</td>
                        <td>{numberFormat(row.ok_pieces)}</td>
                        <td>{numberFormat(row.nok_pieces)}</td>
                        <td>{numberFormat(row.total_pieces)}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="7" className="empty-cell">Sin datos</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        );
      }) : <Empty />}
    </section>
  );
}

function Top3Tab({ data, stations }) {
  const historyByStation = groupBy(data?.top3_history || [], "source_station");

  return (
    <section className="station-grid">
      {stations.length ? stations.map((station) => {
        const history = historyByStation[station] || [];
        const classes = classNames(history);
        const rows = topHistoryRows(history);
        const totals = classes.map((name) => {
          const first = history.find((row) => row.class_name === name);
          return { class_name: name, total_nok_pieces: Number(first?.total_nok_pieces || 0) };
        });
        return (
          <section className="panel station-card" key={station || "blank"}>
            <div className="panel-title">{stationName(station)} - Top 3 NOK por dia</div>
            <div className="chart-wrap top3">
              {rows.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={rows} margin={{ top: 14, right: 20, bottom: 8, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                    <XAxis dataKey="reject_date" tick={{ fontSize: 11 }} minTickGap={14} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip formatter={(value) => numberFormat(value)} />
                    <Legend />
                    {classes.map((name, index) => (
                      <Bar key={name} dataKey={name} name={name} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <Empty />
              )}
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Top</th>
                    <th>Class Name</th>
                    <th>NOK acumulado</th>
                  </tr>
                </thead>
                <tbody>
                  {totals.length ? totals.map((row, index) => (
                    <tr key={`${station}-${row.class_name}`}>
                      <td>{index + 1}</td>
                      <td>{row.class_name}</td>
                      <td>{numberFormat(row.total_nok_pieces)}</td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="3" className="empty-cell">Sin datos</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        );
      }) : <Empty />}
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
  const [activeTab, setActiveTab] = useState("daily");
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
      const payload = await fetchJson(`/api/v1/reject-summary${buildQuery(apiFilters)}`);
      setData(payload);
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

  const stations = stationList(data);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>Reject Summary</h1>
          <p>Analisis por Tesla / lado, condicion y Top 3 historico</p>
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

      <nav className="tabs" aria-label="Reject summary tabs">
        {TABS.map((tab) => (
          <TabButton key={tab.id} tab={tab} active={activeTab === tab.id} onClick={() => setActiveTab(tab.id)} />
        ))}
      </nav>

      {data && activeTab === "daily" ? <DailyTab data={data} stations={stations} /> : null}
      {data && activeTab === "conditions" ? <ConditionsTab data={data} stations={stations} /> : null}
      {data && activeTab === "top3" ? <Top3Tab data={data} stations={stations} /> : null}
      {!data && !loading ? <Empty label="Sin datos cargados" /> : null}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
