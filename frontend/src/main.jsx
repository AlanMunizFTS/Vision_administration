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
import { ChevronDown, Download, RefreshCw, Search } from "lucide-react";
import "./styles.css";

const TABS = [
  { id: "daily", label: "Por dia" },
  { id: "conditions", label: "Per Condition" },
  { id: "top3", label: "Top 3 Historico" }
];

const COLORS = ["#2f6f9f", "#c9564a", "#6f8f3f", "#d39b32", "#7259a4", "#3f8f88", "#8a5c3b", "#69717c"];
const DAY_MS = 24 * 60 * 60 * 1000;
const STATION_DISPLAY_NAMES = {
  ART_ENDFORM_1859: "Tesla 1",
  ART_ENDFORM_1861: "Tesla 2",
  ART_ENDFORM_1862: "Tesla 3"
};

function buildQuery(filters, extra = {}) {
  const params = new URLSearchParams();
  const merged = { ...filters, ...extra };
  for (const [key, value] of Object.entries(merged)) {
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item !== undefined && item !== null && String(item).trim() !== "") params.append(key, item);
      }
    } else if (value !== undefined && value !== null && String(value).trim() !== "") {
      params.set(key, value);
    }
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

function sameFilters(left, right) {
  return sameDateFilters(left, right) && sameStationFilters(left, right) && samePartNumberFilters(left, right);
}

function sameDateFilters(left, right) {
  return ["start_at", "end_at"].every((key) => (left?.[key] || "") === (right?.[key] || ""));
}

function stationFilterList(filters) {
  if (Array.isArray(filters?.station_pairs)) return filters.station_pairs;
  if (Array.isArray(filters?.source_stations)) return filters.source_stations.map(stationPairFromStation);
  if (filters?.source_station) return [stationPairFromStation(filters.source_station)];
  return [];
}

function sameStationFilters(left, right) {
  const leftStations = [...stationFilterList(left)].sort();
  const rightStations = [...stationFilterList(right)].sort();
  return leftStations.length === rightStations.length && leftStations.every((station, index) => station === rightStations[index]);
}

function partNumberFilterList(filters) {
  return Array.isArray(filters?.part_numbers) ? filters.part_numbers : [];
}

function samePartNumberFilters(left, right) {
  const leftPartNumbers = [...partNumberFilterList(left)].sort();
  const rightPartNumbers = [...partNumberFilterList(right)].sort();
  return leftPartNumbers.length === rightPartNumbers.length && leftPartNumbers.every((partNumber, index) => partNumber === rightPartNumbers[index]);
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function formatInputDateTime(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultDateRange() {
  const end = new Date();
  end.setHours(23, 59, 0, 0);
  const start = new Date(end.getTime() - 7 * DAY_MS);
  start.setHours(0, 0, 0, 0);
  return {
    start_at: formatInputDateTime(start),
    end_at: formatInputDateTime(end)
  };
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
  const text = String(value || "").trim();
  if (!text) return "Sin estacion";
  const match = text.match(/(?:\s*-\s*|_)(LEFT|RIGHT)$/i);
  const rawBase = match ? text.slice(0, match.index).trim().replace(/[ _-]+$/g, "") : text;
  const displayBase = STATION_DISPLAY_NAMES[rawBase];
  if (!displayBase) return text;
  if (!match) return displayBase;
  return `${displayBase} - ${match[1].toUpperCase() === "LEFT" ? "Left" : "Right"}`;
}

function stationPairFromStation(value) {
  return String(value || "").replace(/_(LEFT|RIGHT)$/i, "");
}

function stationPairName(value) {
  return stationName(value);
}

function defectName(value) {
  const text = String(value || "").trim().toUpperCase();
  return text || "UNCLASSIFIED";
}

function compareDefects(a, b) {
  return defectName(a).localeCompare(defectName(b), "es", { sensitivity: "base" });
}

function reportDefectNames(data) {
  const names = new Set();
  for (const collection of ["condition_totals", "condition_periods", "top3_history"]) {
    for (const row of data?.[collection] || []) {
      const name = defectName(row.class_name);
      if (name !== "OK") names.add(name);
    }
  }
  return [...names].sort(compareDefects);
}

function defectColorMap(data) {
  return reportDefectNames(data).reduce((acc, name, index) => {
    acc[name] = COLORS[index % COLORS.length];
    return acc;
  }, {});
}

function defectColor(colorsByDefect, name) {
  return colorsByDefect[defectName(name)] || COLORS[0];
}

function niceAxisMax(values = []) {
  const maxValue = Math.max(0, ...values.map((value) => Number(value || 0)));
  if (maxValue <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(maxValue));
  const normalized = maxValue / magnitude;
  const niceNormalized = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return niceNormalized * magnitude;
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

function stationPairOptions(options) {
  const pairs = new Set(options?.station_pairs || []);
  for (const station of options?.source_stations || []) pairs.add(stationPairFromStation(station));
  return [...pairs].filter(Boolean).sort((a, b) => stationPairName(a).localeCompare(stationPairName(b)));
}

function dashboardFilters(filters) {
  return {
    start_at: toApiDateTime(filters.start_at),
    end_at: toApiDateTime(filters.end_at),
    station_pairs: stationFilterList(filters),
    part_numbers: partNumberFilterList(filters)
  };
}

function serverFilters(filters) {
  return {
    start_at: filters?.start_at || "",
    end_at: filters?.end_at || "",
    part_numbers: partNumberFilterList(filters)
  };
}

function filterReportData(data, stationPairs = []) {
  if (!data) return null;
  const selectedPairs = new Set(stationPairs);
  if (!selectedPairs.size) return data;
  const filterSideRows = (rows = []) => rows.filter((row) => selectedPairs.has(stationPairFromStation(row.source_station || "")));
  const filterCombinedRows = (rows = []) => rows.filter((row) => selectedPairs.has(row.station_pair || ""));
  return {
    ...data,
    stations: filterSideRows(data.stations),
    daily: filterSideRows(data.daily),
    condition_periods: filterSideRows(data.condition_periods),
    condition_totals: filterSideRows(data.condition_totals),
    top3_history: filterSideRows(data.top3_history),
    combined: data.combined ? {
      stations: filterCombinedRows(data.combined.stations),
      daily: filterCombinedRows(data.combined.daily),
      condition_periods: filterCombinedRows(data.combined.condition_periods),
      condition_totals: filterCombinedRows(data.combined.condition_totals),
      top3_history: filterCombinedRows(data.combined.top3_history)
    } : undefined
  };
}

function combinedAsStationData(data) {
  if (!data?.combined) return null;
  const mapRows = (rows = []) => rows.map((row) => ({ ...row, source_station: row.station_pair || row.source_station || "" }));
  return {
    stations: mapRows(data.combined.stations),
    daily: mapRows(data.combined.daily),
    condition_periods: mapRows(data.combined.condition_periods),
    condition_totals: mapRows(data.combined.condition_totals),
    top3_history: mapRows(data.combined.top3_history)
  };
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
    byDate[day][defectName(row.class_name)] = Number(row.nok_pieces || 0);
  }
  return Object.values(byDate).sort((a, b) => a.reject_date.localeCompare(b.reject_date));
}

function classNames(rows = []) {
  return [...new Set(rows.map((row) => defectName(row.class_name)).filter(Boolean))].sort(compareDefects);
}

function conditionClasses(rows = []) {
  const totals = {};
  for (const row of rows) {
    const name = defectName(row.class_name);
    if (name === "OK" || Number(row.nok_pieces || 0) <= 0) continue;
    totals[name] = (totals[name] || 0) + Number(row.nok_pieces || 0);
  }
  return Object.entries(totals)
    .sort((a, b) => compareDefects(a[0], b[0]))
    .map(([name]) => name);
}

function conditionDailyRows(rows = [], classes = []) {
  const byDate = {};
  for (const row of rows) {
    const name = defectName(row.class_name);
    if (name === "OK" || Number(row.nok_pieces || 0) <= 0) continue;
    const day = dateLabel(row.reject_date);
    if (!byDate[day]) byDate[day] = { reject_date: day, total_nok: 0 };
    byDate[day][name] = (byDate[day][name] || 0) + Number(row.nok_pieces || 0);
    byDate[day].total_nok += Number(row.nok_pieces || 0);
  }
  return Object.values(byDate).sort((a, b) => a.reject_date.localeCompare(b.reject_date)).map((row) => {
    for (const name of classes) {
      if (row[name] === undefined) row[name] = 0;
    }
    return row;
  });
}

function conditionTotals(rows = []) {
  const totals = {};
  for (const row of rows) {
    const name = defectName(row.class_name);
    if (name === "OK") continue;
    totals[name] = (totals[name] || 0) + Number(row.nok_pieces || 0);
  }
  return Object.entries(totals)
    .sort((a, b) => compareDefects(a[0], b[0]))
    .map(([class_name, nok_pieces]) => ({ class_name, nok_pieces }));
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

function SectionTitle({ children }) {
  return <h2 className="section-title">{children}</h2>;
}

function DailyTab({ data, stations, title }) {
  const rows = dailyChartRows(data, stations);
  const byStation = groupBy(data?.daily || [], "source_station");

  return (
    <section className="tab-panel">
      {title ? <SectionTitle>{title}</SectionTitle> : null}
      <section className="panel">
        <div className="panel-title">Tasa de rechazo (% NOK) por dia</div>
        <div className="chart-wrap tall">
          {rows.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 14, right: 24, bottom: 8, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                <XAxis dataKey="reject_date" tick={{ fontSize: 11 }} minTickGap={14} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(value) => `${value}%`} />
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
                  <th className="station-group" key={station || "blank"} colSpan="5">{stationName(station)}</th>
                ))}
              </tr>
              <tr>
                {stations.flatMap((station) => ["OK", "NOK", "Total", "% OK", "% NOK"].map((metric) => (
                  <th
                    key={`${station}-${metric}`}
                    className={`${metric === "OK" ? "group-start" : ""} ${metric === "% NOK" ? "group-end" : ""}`}
                  >
                    {metric}
                  </th>
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
                        <td className="group-start" key={`${station}-ok-${chartRow.reject_date}`}>{numberFormat(row?.ok_pieces)}</td>,
                        <td key={`${station}-nok-${chartRow.reject_date}`}>{numberFormat(row?.nok_pieces)}</td>,
                        <td key={`${station}-total-${chartRow.reject_date}`}>{numberFormat(row?.total_pieces)}</td>,
                        <td key={`${station}-pct-ok-${chartRow.reject_date}`}>{row ? percentFormat(row.pct_ok) : ""}</td>,
                        <td className="group-end" key={`${station}-pct-nok-${chartRow.reject_date}`}>{row ? percentFormat(row.pct_nok) : ""}</td>
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

function ConditionsTab({ data, stations, colorsByDefect, title }) {
  const periodsByStation = groupBy(data?.condition_periods || [], "source_station");
  const totalsByStation = groupBy(data?.condition_totals || [], "source_station");

  return (
    <section className="tab-panel">
      {title ? <SectionTitle>{title}</SectionTitle> : null}
      <section className="station-grid">
        {stations.length ? stations.map((station) => {
          const totals = conditionTotals(totalsByStation[station] || []);
          return (
            <section className="panel station-card" key={station || "blank"}>
              <div className="panel-title">{stationName(station)} - Rechazos por clase</div>
              <div className="chart-wrap pie">
                {totals.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={totals} dataKey="nok_pieces" nameKey="class_name" outerRadius={92} label>
                        {totals.map((_, index) => (
                          <Cell key={index} fill={defectColor(colorsByDefect, totals[index].class_name)} />
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
            </section>
          );
        }) : <Empty />}
      </section>

      <section className="daily-defects">
        {stations.length ? stations.map((station) => {
          const periods = periodsByStation[station] || [];
          const classes = conditionClasses(periods);
          const rows = conditionDailyRows(periods, classes);
          return (
            <section className="panel station-card" key={`${station || "blank"}-daily`}>
              <div className="panel-title">{stationName(station)} - Defectos dia a dia</div>
              <div className="table-wrap condition-daily">
                <table>
                  <thead>
                    <tr>
                      <th>Fecha</th>
                      {classes.map((name) => (
                        <th key={`${station}-${name}`}>{name}</th>
                      ))}
                      <th>Total NOK</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.length ? rows.map((row) => (
                      <tr key={`${station}-${row.reject_date}`}>
                        <td>{dateLabel(row.reject_date)}</td>
                        {classes.map((name) => (
                          <td key={`${station}-${row.reject_date}-${name}`}>{numberFormat(row[name])}</td>
                        ))}
                        <td>{numberFormat(row.total_nok)}</td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan={2 + classes.length} className="empty-cell">Sin defectos</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          );
        }) : null}
      </section>
    </section>
  );
}

function Top3Tab({ data, stations, colorsByDefect, title }) {
  const historyByStation = groupBy(data?.top3_history || [], "source_station");
  const countAxisMax = niceAxisMax((data?.top3_history || []).map((row) => row.nok_pieces));

  return (
    <section className="tab-panel">
      {title ? <SectionTitle>{title}</SectionTitle> : null}
      <section className="station-grid">
        {stations.length ? stations.map((station) => {
          const history = historyByStation[station] || [];
          const classes = classNames(history);
          const rows = topHistoryRows(history);
          const totals = classes.map((name) => {
            const first = history.find((row) => defectName(row.class_name) === name);
            return {
              class_name: name,
              class_rank: Number(first?.class_rank || 0),
              total_nok_pieces: Number(first?.total_nok_pieces || 0)
            };
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
                      <YAxis domain={[0, countAxisMax]} tick={{ fontSize: 11 }} />
                      <Tooltip formatter={(value) => numberFormat(value)} />
                      <Legend />
                      {classes.map((name) => (
                        <Bar key={name} dataKey={name} name={name} fill={defectColor(colorsByDefect, name)} />
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
                        <td>{row.class_rank || index + 1}</td>
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
    </section>
  );
}

function MultiSelect({ options, value, onChange, getLabel = (item) => item, searchPlaceholder, selectedText = "seleccionados" }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const selected = new Set(value || []);
  const filtered = options.filter((item) => getLabel(item).toLowerCase().includes(search.trim().toLowerCase()));
  const label = selected.size ? `${selected.size} ${selectedText}` : "Todas";

  function toggle(item) {
    const next = new Set(selected);
    if (next.has(item)) next.delete(item);
    else next.add(item);
    onChange([...next].sort((a, b) => getLabel(a).localeCompare(getLabel(b))));
  }

  return (
    <div className="multi-select" onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      <button type="button" className="multi-select-trigger" onClick={() => setOpen((current) => !current)} aria-expanded={open}>
        <span>{label}</span>
        <ChevronDown size={16} />
      </button>
      {open ? (
        <div className="multi-select-menu">
          <label className="search-box">
            <Search size={15} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={searchPlaceholder} />
          </label>
          <div className="multi-select-actions">
            <button type="button" className="small-button" onClick={() => onChange([])}>Todas</button>
            <button type="button" className="small-button" onClick={() => onChange(options)}>Seleccionar todas</button>
          </div>
          <div className="multi-select-options">
            {filtered.length ? filtered.map((item) => (
              <label className="check-option" key={item}>
                <input type="checkbox" checked={selected.has(item)} onChange={() => toggle(item)} />
                <span>{getLabel(item)}</span>
              </label>
            )) : <div className="empty-option">Sin coincidencias</div>}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function App() {
  const [options, setOptions] = useState({ source_stations: [], station_pairs: [], part_numbers: [] });
  const [filters, setFilters] = useState(() => ({
    ...defaultDateRange(),
    station_pairs: [],
    part_numbers: []
  }));
  const [appliedFilters, setAppliedFilters] = useState(null);
  const [loadedData, setLoadedData] = useState(null);
  const [loadedServerFilters, setLoadedServerFilters] = useState(null);
  const [activeTab, setActiveTab] = useState("daily");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchJson("/api/v1/options")
      .then((payload) => {
        setOptions(payload);
      })
      .catch((exc) => setError(exc.message));
  }, []);

  const apiFilters = useMemo(() => dashboardFilters(filters), [filters]);
  const visibleData = useMemo(
    () => filterReportData(loadedData, appliedFilters?.station_pairs || []),
    [loadedData, appliedFilters]
  );

  async function applyFilters(targetFilters = filters) {
    const nextFilters = dashboardFilters(targetFilters);
    const nextServerFilters = serverFilters(nextFilters);
    if (loadedData && sameDateFilters(nextServerFilters, loadedServerFilters) && samePartNumberFilters(nextServerFilters, loadedServerFilters)) {
      setAppliedFilters(nextFilters);
      setError("");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const payload = await fetchJson(`/api/v1/reject-summary${buildQuery(nextServerFilters)}`);
      setLoadedData(payload);
      setLoadedServerFilters(nextServerFilters);
      setAppliedFilters(nextFilters);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    applyFilters();
  }, []);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  async function downloadExcel() {
    if (!visibleData || !appliedFilters || !sameFilters(apiFilters, appliedFilters)) return;
    setExporting(true);
    setError("");
    try {
      const response = await fetch("/api/v1/reports/excel", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters: appliedFilters, data: visibleData })
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "vision_report.xlsx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (exc) {
      setError(exc.message);
    } finally {
      setExporting(false);
    }
  }

  const pairOptions = useMemo(() => stationPairOptions(options), [options]);
  const partNumberOptions = useMemo(() => [...(options?.part_numbers || [])].filter(Boolean).sort(), [options]);
  const stations = stationList(visibleData);
  const combinedData = useMemo(() => combinedAsStationData(visibleData), [visibleData]);
  const combinedStations = stationList(combinedData);
  const colorsByDefect = useMemo(() => defectColorMap(visibleData), [visibleData]);
  const combinedColorsByDefect = useMemo(() => defectColorMap(combinedData), [combinedData]);
  const canDownloadExcel = Boolean(visibleData) && !loading && !exporting && sameFilters(apiFilters, appliedFilters);

  return (
    <main>
      <header className="topbar">
        <div>
          <h1>Reject Summary</h1>
          <p>Analisis por Tesla / lado, condicion y Top 3 historico</p>
        </div>
        <div className="actions">
          <button type="button" className="button-success" onClick={downloadExcel} disabled={!canDownloadExcel} title="Descargar Excel">
            <Download size={17} />
            {exporting ? "Exportando" : "Excel"}
          </button>
        </div>
      </header>

      <section className="filters compact">
        <label>
          Inicio
          <input type="datetime-local" value={filters.start_at} onChange={(event) => updateFilter("start_at", event.target.value)} />
        </label>
        <label>
          Fin
          <input type="datetime-local" value={filters.end_at} onChange={(event) => updateFilter("end_at", event.target.value)} />
        </label>
        <div className="station-filter">
          <span>Estacion</span>
          <MultiSelect
            options={pairOptions}
            value={filters.station_pairs}
            onChange={(value) => updateFilter("station_pairs", value)}
            getLabel={stationPairName}
            searchPlaceholder="Buscar estacion"
            selectedText="seleccionadas"
          />
          <span className="filter-hint">Selecciona estaciones base; cada una incluye LEFT y RIGHT.</span>
        </div>
        <div className="station-filter">
          <span>Part Number</span>
          <MultiSelect
            options={partNumberOptions}
            value={filters.part_numbers}
            onChange={(value) => updateFilter("part_numbers", value)}
            searchPlaceholder="Buscar part number"
          />
          <span className="filter-hint">Selecciona uno o mas numeros de parte.</span>
        </div>
      </section>
      <div className="filter-actions">
        <button type="button" className="button-primary" onClick={() => applyFilters()} disabled={loading} title="Aplicar filtros">
          <RefreshCw size={17} />
          {loading ? "Aplicando" : "Aplicar"}
        </button>
      </div>

      {error ? <div className="error">{error}</div> : null}
      {loading ? <div className="loading">Cargando datos...</div> : null}

      <nav className="tabs" aria-label="Reject summary tabs">
        {TABS.map((tab) => (
          <TabButton key={tab.id} tab={tab} active={activeTab === tab.id} onClick={() => setActiveTab(tab.id)} />
        ))}
      </nav>

      {visibleData && activeTab === "daily" ? (
        <>
          <DailyTab data={visibleData} stations={stations} title="Por lado" />
          {combinedData ? <DailyTab data={combinedData} stations={combinedStations} title="Combinado LEFT+RIGHT" /> : null}
        </>
      ) : null}
      {visibleData && activeTab === "conditions" ? (
        <>
          <ConditionsTab data={visibleData} stations={stations} colorsByDefect={colorsByDefect} title="Por lado" />
          {combinedData ? <ConditionsTab data={combinedData} stations={combinedStations} colorsByDefect={combinedColorsByDefect} title="Combinado LEFT+RIGHT" /> : null}
        </>
      ) : null}
      {visibleData && activeTab === "top3" ? (
        <>
          <Top3Tab data={visibleData} stations={stations} colorsByDefect={colorsByDefect} title="Por lado" />
          {combinedData ? <Top3Tab data={combinedData} stations={combinedStations} colorsByDefect={combinedColorsByDefect} title="Combinado LEFT+RIGHT" /> : null}
        </>
      ) : null}
      {!visibleData && !loading ? <Empty label="Sin datos cargados" /> : null}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
