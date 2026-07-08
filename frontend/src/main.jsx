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
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { Activity, AlertTriangle, Calendar, CheckCircle2, ChevronDown, Download, Flag, Layers, ListChecks, Pencil, Plus, RefreshCw, Trash2, UserPlus, Users, X } from "lucide-react";
import "./styles.css";

const TABS = [
  { id: "daily", label: "By Day" },
  { id: "conditions", label: "Per Condition" },
  { id: "top3", label: "Top 3 History" }
];

const COLORS = ["#2f6f9f", "#c9564a", "#6f8f3f", "#d39b32", "#7259a4", "#3f8f88", "#8a5c3b", "#69717c"];
const PART_NUMBER_BAND_COLORS = ["#c7d2fe", "#bbf7d0", "#fde68a", "#fbcfe8", "#bfdbfe", "#fecaca", "#ddd6fe", "#a7f3d0"];
const MACHINE_ALL = "__all__";
const CHANGE_LOG_CATEGORIES = ["Lots", "Burger", "Chamfer", "RPMs", "Infeed Advance", "Outfeed Advance", "Other"];
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
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function percentFormat(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function dateLabel(value) {
  return String(value || "").slice(0, 10);
}

function hourLabel(value) {
  const text = String(value || "");
  if (!text) return "";
  return `${text.slice(5, 10)} ${text.slice(11, 16)}`;
}

function stationName(value) {
  const text = String(value || "").trim();
  if (!text) return "No station";
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
  return defectName(a).localeCompare(defectName(b), "en", { sensitivity: "base" });
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
  const getKey = typeof key === "function" ? key : (item) => item[key] || "";
  return items.reduce((acc, item) => {
    const groupKey = getKey(item);
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
    end_at: filters?.end_at || ""
  };
}

function partNumberValue(row) {
  return String(row?.part_number || "").trim();
}

function pct(numerator, denominator) {
  return denominator ? numerator / denominator : 0;
}

function aggregatePieceRows(rows = [], keyFields = [], options = {}) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFields.map((field) => row[field] || "").join("\u0001");
    if (!groups.has(key)) {
      const item = {};
      for (const field of keyFields) item[field] = row[field] || "";
      if (options.sourceStations) item.source_stations = new Set();
      groups.set(key, { ...item, ok_pieces: 0, nok_pieces: 0, total_pieces: 0 });
    }
    const item = groups.get(key);
    item.ok_pieces += Number(row.ok_pieces || 0);
    item.nok_pieces += Number(row.nok_pieces || 0);
    item.total_pieces += Number(row.total_pieces || 0);
    if (options.sourceStations) {
      for (const station of row.source_stations || []) item.source_stations.add(station);
    }
  }
  return [...groups.values()].map((item) => ({
    ...item,
    source_stations: item.source_stations ? [...item.source_stations].sort() : item.source_stations,
    pct_ok: pct(item.ok_pieces, item.total_pieces),
    pct_nok: pct(item.nok_pieces, item.total_pieces)
  }));
}

function aggregateConditionPeriods(rows = [], keyFields = []) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFields.map((field) => row[field] || "").join("\u0001");
    if (!groups.has(key)) {
      const item = {};
      for (const field of keyFields) item[field] = row[field] || "";
      groups.set(key, { ...item, period_start: row.period_start || "", period_end: row.period_end || "", ok_pieces: 0, nok_pieces: 0, total_pieces: 0 });
    }
    const item = groups.get(key);
    item.ok_pieces += Number(row.ok_pieces || 0);
    item.nok_pieces += Number(row.nok_pieces || 0);
    item.total_pieces += Number(row.total_pieces || 0);
    if (row.period_start && (!item.period_start || row.period_start < item.period_start)) item.period_start = row.period_start;
    if (row.period_end && (!item.period_end || row.period_end > item.period_end)) item.period_end = row.period_end;
  }
  return [...groups.values()];
}

function aggregateConditionTotals(rows = [], stationKey) {
  const groups = new Map();
  for (const row of rows) {
    const key = `${row[stationKey] || ""}\u0001${defectName(row.class_name)}`;
    if (!groups.has(key)) groups.set(key, { [stationKey]: row[stationKey] || "", class_name: defectName(row.class_name), nok_pieces: 0 });
    groups.get(key).nok_pieces += Number(row.nok_pieces || 0);
  }
  return [...groups.values()];
}

function rebuildTop3History(conditionPeriods = [], stationKey) {
  const byStation = groupBy(conditionPeriods, stationKey);
  const output = [];
  for (const [station, rows] of Object.entries(byStation)) {
    const totals = {};
    for (const row of rows) {
      const name = defectName(row.class_name);
      if (name === "OK") continue;
      totals[name] = (totals[name] || 0) + Number(row.nok_pieces || 0);
    }
    const topClasses = Object.entries(totals)
      .sort((a, b) => b[1] - a[1] || compareDefects(a[0], b[0]))
      .slice(0, 3);
    topClasses.forEach(([className, total], index) => {
      const byDate = {};
      for (const row of rows) {
        if (defectName(row.class_name) !== className) continue;
        const day = dateLabel(row.reject_date);
        if (!day) continue;
        byDate[day] = (byDate[day] || 0) + Number(row.nok_pieces || 0);
      }
      for (const day of Object.keys(byDate).sort()) {
        output.push({
          [stationKey]: station,
          class_name: className,
          total_nok_pieces: total,
          class_rank: index + 1,
          reject_date: day,
          nok_pieces: byDate[day]
        });
      }
    });
  }
  return output;
}

function filterReportData(data, stationPairs = [], partNumbers = []) {
  if (!data) return null;
  const selectedPairs = new Set(stationPairs);
  const selectedPartNumbers = new Set(partNumbers);
  const matchesPartNumber = (row) => !selectedPartNumbers.size || selectedPartNumbers.has(partNumberValue(row));
  const filterSideRows = (rows = []) => rows.filter((row) => matchesPartNumber(row) && (!selectedPairs.size || selectedPairs.has(stationPairFromStation(row.source_station || ""))));
  const filterCombinedRows = (rows = []) => rows.filter((row) => matchesPartNumber(row) && (!selectedPairs.size || selectedPairs.has(row.station_pair || "")));
  const sideConditionPeriods = aggregateConditionPeriods(filterSideRows(data.condition_periods), ["source_station", "reject_date", "class_name"]);
  const combinedConditionPeriods = aggregateConditionPeriods(filterCombinedRows(data.combined?.condition_periods), ["station_pair", "reject_date", "class_name"]);
  return {
    ...data,
    stations: aggregatePieceRows(filterSideRows(data.stations), ["source_station"]),
    daily: aggregatePieceRows(filterSideRows(data.daily), ["source_station", "reject_date"]),
    daily_by_part: aggregatePieceRows(filterSideRows(data.daily), ["source_station", "reject_date", "part_number"]),
    hourly: aggregatePieceRows(filterSideRows(data.hourly), ["source_station", "bucket_start"]),
    hourly_by_part: aggregatePieceRows(filterSideRows(data.hourly), ["source_station", "bucket_start", "part_number"]),
    condition_periods: sideConditionPeriods,
    condition_totals: aggregateConditionTotals(filterSideRows(data.condition_totals), "source_station"),
    top3_history: rebuildTop3History(sideConditionPeriods, "source_station"),
    combined: data.combined ? {
      stations: aggregatePieceRows(filterCombinedRows(data.combined.stations), ["station_pair"], { sourceStations: true }),
      daily: aggregatePieceRows(filterCombinedRows(data.combined.daily), ["station_pair", "reject_date"]),
      daily_by_part: aggregatePieceRows(filterCombinedRows(data.combined.daily), ["station_pair", "reject_date", "part_number"]),
      hourly: aggregatePieceRows(filterCombinedRows(data.combined.hourly), ["station_pair", "bucket_start"]),
      hourly_by_part: aggregatePieceRows(filterCombinedRows(data.combined.hourly), ["station_pair", "bucket_start", "part_number"]),
      condition_periods: combinedConditionPeriods,
      condition_totals: aggregateConditionTotals(filterCombinedRows(data.combined.condition_totals), "station_pair"),
      top3_history: rebuildTop3History(combinedConditionPeriods, "station_pair")
    } : undefined
  };
}

function combinedAsStationData(data) {
  if (!data?.combined) return null;
  const mapRows = (rows = []) => rows.map((row) => ({ ...row, source_station: row.station_pair || row.source_station || "" }));
  return {
    stations: mapRows(data.combined.stations),
    daily: mapRows(data.combined.daily),
    daily_by_part: mapRows(data.combined.daily_by_part),
    hourly: mapRows(data.combined.hourly),
    hourly_by_part: mapRows(data.combined.hourly_by_part),
    condition_periods: mapRows(data.combined.condition_periods),
    condition_totals: mapRows(data.combined.condition_totals),
    top3_history: mapRows(data.combined.top3_history)
  };
}

const PLANT_WIDE_STATION = "ALL";

function plantWideData(stationData) {
  if (!stationData) return null;
  const asAll = (rows = []) => rows.map((row) => ({ ...row, source_station: PLANT_WIDE_STATION }));
  const conditionPeriods = aggregateConditionPeriods(asAll(stationData.condition_periods), ["source_station", "reject_date", "class_name"]);
  return {
    stations: aggregatePieceRows(asAll(stationData.stations), ["source_station"]),
    daily: aggregatePieceRows(asAll(stationData.daily), ["source_station", "reject_date"]),
    daily_by_part: aggregatePieceRows(asAll(stationData.daily_by_part), ["source_station", "reject_date", "part_number"]),
    hourly: aggregatePieceRows(asAll(stationData.hourly), ["source_station", "bucket_start"]),
    hourly_by_part: aggregatePieceRows(asAll(stationData.hourly_by_part), ["source_station", "bucket_start", "part_number"]),
    condition_periods: conditionPeriods,
    condition_totals: aggregateConditionTotals(asAll(stationData.condition_totals), "source_station"),
    top3_history: rebuildTop3History(conditionPeriods, "source_station")
  };
}

function findActiveSubprojects(projects, stations) {
  const stationSet = new Set((stations || []).filter(Boolean).map((s) => stationPairFromStation(s)));
  if (!stationSet.size) return [];
  const matches = [];
  for (const project of projects || []) {
    for (const subproject of project.subprojects || []) {
      if (subproject.status !== "active") continue;
      const covers = (subproject.station_pairs || []).some((pair) => stationSet.has(pair));
      if (covers) matches.push({ ...subproject, projectName: project.name });
    }
  }
  return matches;
}

function stationSide(value) {
  const text = String(value || "").trim();
  const match = text.match(/_(LEFT|RIGHT)$/i);
  return match ? match[1].toLowerCase() : null;
}

function findChangeLogEntries(entries, stations) {
  const cleanStations = (stations || []).filter(Boolean);
  if (!cleanStations.length) return [];
  const pairsWithAnySide = new Set(cleanStations.map((s) => stationPairFromStation(s)));
  const sidesByPair = {};
  for (const station of cleanStations) {
    const pair = stationPairFromStation(station);
    const side = stationSide(station);
    if (side) {
      if (!sidesByPair[pair]) sidesByPair[pair] = new Set();
      sidesByPair[pair].add(side);
    }
  }
  return (entries || []).filter((entry) => {
    if (!pairsWithAnySide.has(entry.station_pair)) return false;
    const requiredSides = sidesByPair[entry.station_pair];
    if (!requiredSides) return true;
    if (entry.side === "both") return true;
    return requiredSides.has(entry.side);
  });
}

function glidepathValueAt(subproject, isoDate) {
  if (!subproject) return null;
  const milestones = [...(subproject.milestones || [])].sort((a, b) => a.target_date.localeCompare(b.target_date));
  const points = [
    { date: subproject.start_date, value: Number(subproject.start_pct_nok) },
    ...milestones.map((m) => ({ date: m.target_date, value: Number(m.target_pct_nok) }))
  ];
  if (isoDate < points[0].date) return null;

  for (let i = 0; i < points.length - 1; i++) {
    const from = points[i];
    const to = points[i + 1];
    if (isoDate >= from.date && isoDate <= to.date) {
      const fromTime = new Date(`${from.date}T00:00:00`).getTime();
      const toTime = new Date(`${to.date}T00:00:00`).getTime();
      const currentTime = new Date(`${isoDate}T00:00:00`).getTime();
      if (toTime === fromTime) return to.value;
      const ratio = (currentTime - fromTime) / (toTime - fromTime);
      return from.value + (to.value - from.value) * ratio;
    }
  }
  return points[points.length - 1].value;
}

function glidepathChartRows(rows, subprojects, dateKey) {
  if (!subprojects || !subprojects.length) return rows;
  return rows.map((row) => {
    const isoDate = String(row[dateKey] || "").slice(0, 10);
    const extra = {};
    for (const subproject of subprojects) {
      extra[`__glidepath_${subproject.id}`] = isoDate ? glidepathValueAt(subproject, isoDate) : null;
    }
    return { ...row, ...extra };
  });
}

function changeLogMarkers(entries, chartRows, isHourly) {
  if (!entries || !entries.length || !chartRows.length) return [];
  const markers = [];
  if (isHourly) {
    const rowsByBucketHour = {};
    const firstRowByDate = {};
    for (const row of chartRows) {
      const bucketStart = String(row.bucket_start || "");
      const day = bucketStart.slice(0, 10);
      const hour = bucketStart.slice(11, 13);
      rowsByBucketHour[`${day}T${hour}`] = row;
      if (!firstRowByDate[day]) firstRowByDate[day] = row;
    }
    const byBucket = groupBy(
      entries,
      (entry) => `${entry.change_date}T${entry.change_time ? entry.change_time.slice(0, 2) : "__"}`
    );
    for (const [bucketKey, bucketEntries] of Object.entries(byBucket)) {
      const [day] = bucketKey.split("T");
      const row = rowsByBucketHour[bucketKey] || firstRowByDate[day];
      if (row) markers.push({ axisValue: row.reject_date, entries: bucketEntries });
    }
  } else {
    const byDate = groupBy(entries, "change_date");
    const validDates = new Set(chartRows.map((row) => row.reject_date));
    for (const [day, dayEntries] of Object.entries(byDate)) {
      if (validDates.has(day)) markers.push({ axisValue: day, entries: dayEntries });
    }
  }
  return markers;
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

function hourlyChartRows(data, stations) {
  const byHour = {};
  for (const row of data?.hourly || []) {
    const bucketStart = String(row.bucket_start || "");
    if (!bucketStart) continue;
    if (!byHour[bucketStart]) byHour[bucketStart] = { bucket_start: bucketStart, reject_date: hourLabel(bucketStart) };
    byHour[bucketStart][row.source_station || ""] = Number(row.pct_nok || 0) * 100;
  }
  return Object.values(byHour).sort((a, b) => a.bucket_start.localeCompare(b.bucket_start)).map((row) => {
    for (const station of stations) {
      if (row[station] === undefined) row[station] = null;
    }
    return row;
  });
}

function partNumberBands(rows, orderedLabels, getLabel) {
  const totalsByLabel = {};
  for (const row of rows || []) {
    const label = getLabel(row);
    const partNumber = String(row.part_number || "").trim();
    if (!label || !partNumber) continue;
    if (!totalsByLabel[label]) totalsByLabel[label] = {};
    totalsByLabel[label][partNumber] = (totalsByLabel[label][partNumber] || 0) + Number(row.total_pieces || 0);
  }

  const partNumbersByLabel = {};
  for (const [label, totals] of Object.entries(totalsByLabel)) {
    partNumbersByLabel[label] = Object.entries(totals)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([partNumber]) => partNumber);
  }

  const bands = [];
  let current = null;
  for (const label of orderedLabels) {
    const partNumbers = partNumbersByLabel[label] || null;
    const key = partNumbers ? partNumbers.join("") : null;
    if (key && current && current.key === key) {
      current.end = label;
    } else {
      if (current) bands.push(current);
      current = partNumbers ? { key, partNumbers, start: label, end: label } : null;
    }
  }
  if (current) bands.push(current);
  return bands;
}

function partNumberBandColor(partNumber, knownPartNumbers) {
  const index = knownPartNumbers.indexOf(partNumber);
  return PART_NUMBER_BAND_COLORS[(index < 0 ? 0 : index) % PART_NUMBER_BAND_COLORS.length];
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

function overallTotals(data) {
  const rows = data?.stations || [];
  const totals = rows.reduce(
    (acc, row) => {
      acc.ok += Number(row.ok_pieces || 0);
      acc.nok += Number(row.nok_pieces || 0);
      acc.total += Number(row.total_pieces || 0);
      return acc;
    },
    { ok: 0, nok: 0, total: 0 }
  );
  return {
    ...totals,
    pct_ok: pct(totals.ok, totals.total),
    pct_nok: pct(totals.nok, totals.total)
  };
}

function KpiRow({ data, stationCount }) {
  const totals = overallTotals(data);
  return (
    <section className="kpi-row">
      <div className="kpi-card">
        <span className="kpi-label"><span className="dot" style={{ background: "#4f46e5" }} /><Layers size={13} /> Total Pieces</span>
        <span className="kpi-value">{numberFormat(totals.total)}</span>
        <span className="kpi-sub">{stationCount} station{stationCount === 1 ? "" : "s"} in range</span>
      </div>
      <div className="kpi-card good">
        <span className="kpi-label"><span className="dot" style={{ background: "#16a34a" }} /><CheckCircle2 size={13} /> OK</span>
        <span className="kpi-value">{numberFormat(totals.ok)}</span>
        <span className="kpi-sub">{percentFormat(totals.pct_ok)} of total</span>
      </div>
      <div className="kpi-card bad">
        <span className="kpi-label"><span className="dot" style={{ background: "#dc2626" }} /><AlertTriangle size={13} /> NOK</span>
        <span className="kpi-value">{numberFormat(totals.nok)}</span>
        <span className="kpi-sub">{percentFormat(totals.pct_nok)} of total</span>
      </div>
      <div className="kpi-card">
        <span className="kpi-label"><span className="dot" style={{ background: "#0ea5e9" }} /><Activity size={13} /> Reject Rate</span>
        <span className="kpi-value">{percentFormat(totals.pct_nok)}</span>
        <span className="kpi-sub">Over inspected pieces</span>
      </div>
    </section>
  );
}

function TabButton({ tab, active, onClick }) {
  return (
    <button type="button" className={`tab-button ${active ? "active" : ""}`} onClick={onClick}>
      {tab.label}
    </button>
  );
}

function Empty({ label = "No data" }) {
  return <div className="empty">{label}</div>;
}

function SectionTitle({ children }) {
  return <h2 className="section-title">{children}</h2>;
}

function TableToggle({ label, children }) {
  return (
    <details className="table-toggle">
      <summary>
        <ChevronDown size={15} className="chevron" />
        {label}
      </summary>
      {children}
    </details>
  );
}

function DailyTab({ data, stations, title, showPartNumberBands = true, glidepathSubprojects = [], changeLogEntries = [] }) {
  const [granularity, setGranularity] = useState("day");
  const isHourly = granularity === "hour";
  const rawRows = isHourly ? hourlyChartRows(data, stations) : dailyChartRows(data, stations);
  const rows = useMemo(
    () => glidepathChartRows(rawRows, glidepathSubprojects, isHourly ? "bucket_start" : "reject_date"),
    [rawRows, glidepathSubprojects, isHourly]
  );
  const byStation = groupBy(data?.daily || [], "source_station");
  const orderedDates = rows.map((row) => row.reject_date);
  const bands = useMemo(() => {
    if (!showPartNumberBands) return [];
    return isHourly
      ? partNumberBands(data?.hourly_by_part, orderedDates, (row) => hourLabel(row.bucket_start))
      : partNumberBands(data?.daily_by_part, orderedDates, (row) => dateLabel(row.reject_date));
  }, [data, orderedDates.join("|"), isHourly, showPartNumberBands]);
  const knownPartNumbers = [...new Set(bands.flatMap((band) => band.partNumbers))];
  const mixedBands = bands.filter((band) => band.partNumbers.length > 1);
  const changeMarkers = useMemo(
    () => changeLogMarkers(changeLogEntries, rows, isHourly),
    [changeLogEntries, rows, isHourly]
  );

  return (
    <section className="tab-panel">
      {title ? <SectionTitle>{title}</SectionTitle> : null}
      <section className="panel">
        <div className="panel-title">
          <span>Reject Rate (% NOK) by {isHourly ? "hour" : "day"}</span>
          <div className="granularity-toggle">
            <button type="button" className={!isHourly ? "active" : ""} onClick={() => setGranularity("day")}>Day</button>
            <button type="button" className={isHourly ? "active" : ""} onClick={() => setGranularity("hour")}>Hour</button>
          </div>
        </div>
        <div className="chart-wrap tall">
          {rows.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={rows} margin={{ top: 14, right: 24, bottom: 8, left: 0 }}>
                <defs>
                  {mixedBands.map((band) => (
                    <pattern
                      key={band.key}
                      id={`pn-stripe-${band.key.replace(/[^a-zA-Z0-9]/g, "")}`}
                      patternUnits="userSpaceOnUse"
                      width="10"
                      height="10"
                      patternTransform="rotate(45)"
                    >
                      {band.partNumbers.map((partNumber, stripeIndex) => (
                        <rect
                          key={partNumber}
                          x={stripeIndex * (10 / band.partNumbers.length)}
                          y="0"
                          width={10 / band.partNumbers.length}
                          height="10"
                          fill={partNumberBandColor(partNumber, knownPartNumbers)}
                        />
                      ))}
                    </pattern>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8dde3" />
                <XAxis dataKey="reject_date" tick={{ fontSize: 11 }} minTickGap={isHourly ? 24 : 14} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(value) => `${value}%`} />
                <Tooltip formatter={(value) => (value === null ? "" : `${Number(value).toFixed(1)}%`)} />
                <Legend />
                {bands.map((band, index) => (
                  <ReferenceArea
                    key={`${band.key}-${band.start}-${index}`}
                    x1={band.start}
                    x2={band.end}
                    fill={
                      band.partNumbers.length > 1
                        ? `url(#pn-stripe-${band.key.replace(/[^a-zA-Z0-9]/g, "")})`
                        : partNumberBandColor(band.partNumbers[0], knownPartNumbers)
                    }
                    fillOpacity={band.partNumbers.length > 1 ? 0.65 : 0.45}
                    ifOverflow="visible"
                  />
                ))}
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
                {glidepathSubprojects.map((subproject) => (
                  <Line
                    key={`glidepath-${subproject.id}`}
                    type="linear"
                    dataKey={`__glidepath_${subproject.id}`}
                    name={`Glidepath: ${subproject.name}`}
                    stroke="#16a34a"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                    dot={false}
                    connectNulls
                    isAnimationActive={false}
                  />
                ))}
                {changeMarkers.map((marker) => (
                  <ReferenceLine
                    key={`change-${marker.axisValue}`}
                    x={marker.axisValue}
                    stroke="#9aa1ab"
                    strokeDasharray="3 3"
                    ifOverflow="visible"
                    label={{
                      value: marker.entries.length > 1 ? `${marker.entries.length} changes` : marker.entries[0].label,
                      position: "top",
                      fill: "#6b7280",
                      fontSize: 10,
                      fontWeight: 650
                    }}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <Empty />
          )}
        </div>
        {changeMarkers.length ? (
          <div className="change-log-legend">
            {changeMarkers.flatMap((marker) => marker.entries).map((entry) => (
              <span className="change-log-legend-item" key={entry.id} title={entry.description || ""}>
                <span className="change-log-legend-dot" />
                {entry.change_date}{entry.change_time ? ` ${entry.change_time.slice(0, 5)}` : ""} - {entry.label}
              </span>
            ))}
          </div>
        ) : null}
        {knownPartNumbers.length ? (
          <div className="pn-legend">
            {knownPartNumbers.map((partNumber) => (
              <span className="pn-legend-item" key={partNumber}>
                <span className="pn-legend-swatch" style={{ background: partNumberBandColor(partNumber, knownPartNumbers) }} />
                {partNumber}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <section className="panel">
        <TableToggle label="View data table">
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
                    <td colSpan={1 + stations.length * 5} className="empty-cell">No data</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </TableToggle>
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
              <div className="panel-title">{stationName(station)} - Rejects by Class</div>
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
                  <Empty label="No rejects" />
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
              <TableToggle label={`${stationName(station)} - Defects Day by Day`}>
                <div className="table-wrap condition-daily">
                  <table>
                    <thead>
                      <tr>
                        <th>Date</th>
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
                          <td colSpan={2 + classes.length} className="empty-cell">No defects</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </TableToggle>
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
              <div className="panel-title">{stationName(station)} - Top 3 NOK by Day</div>
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
              <TableToggle label="View data table">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Top</th>
                        <th>Class Name</th>
                        <th>Cumulative NOK</th>
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
                          <td colSpan="3" className="empty-cell">No data</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </TableToggle>
            </section>
          );
        }) : <Empty />}
      </section>
    </section>
  );
}

function headOptions(options) {
  const stations = [...(options?.source_stations || [])].filter(Boolean);
  const byPair = groupBy(stations.map((station) => ({ station, pair: stationPairFromStation(station) })), "pair");
  return Object.entries(byPair)
    .map(([pair, items]) => ({ pair, stations: items.map((item) => item.station).sort() }))
    .sort((a, b) => stationPairName(a.pair).localeCompare(stationPairName(b.pair)));
}

function Sidebar({
  options,
  activeScreen,
  viewLevel,
  onSelectOverall,
  onSelectMachine,
  onSelectHead,
  filters,
  onUpdateFilter,
  onApplyFilters,
  loading,
  onOpenGlidepath,
  onOpenChangeLog,
  onOpenEmployees,
  onOpenChanges
}) {
  const [machineOpen, setMachineOpen] = useState(true);
  const [headOpen, setHeadOpen] = useState(false);
  const pairs = stationPairOptions(options);
  const heads = headOptions(options);

  return (
    <nav className="sidebar" aria-label="View level">
      <div className="sidebar-brand">
        <Activity size={17} />
        Vision
      </div>

      <div className="nav-group">
        <button type="button" className={`nav-item ${activeScreen === "summary" && viewLevel.type === "overall" ? "active" : ""}`} onClick={onSelectOverall}>
          <span className="nav-item-label"><Layers size={15} /> Overall</span>
        </button>

        <button type="button" className="nav-item" onClick={() => setMachineOpen((v) => !v)}>
          <span className="nav-item-label">Machine</span>
          <ChevronDown size={14} style={{ transform: machineOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }} />
        </button>
        {machineOpen ? (
          <div className="nav-subgroup">
            <button
              type="button"
              className={`nav-subitem ${activeScreen === "summary" && viewLevel.type === "machine" && viewLevel.pair === MACHINE_ALL ? "active" : ""}`}
              onClick={() => onSelectMachine(MACHINE_ALL)}
            >
              <span>All</span>
            </button>
            {pairs.length ? pairs.map((pair) => (
              <button
                key={pair}
                type="button"
                className={`nav-subitem ${activeScreen === "summary" && viewLevel.type === "machine" && viewLevel.pair === pair ? "active" : ""}`}
                onClick={() => onSelectMachine(pair)}
              >
                <span>{stationPairName(pair)}</span>
              </button>
            )) : <span className="nav-subitem">No data</span>}
          </div>
        ) : null}

        <button type="button" className="nav-item" onClick={() => setHeadOpen((v) => !v)}>
          <span className="nav-item-label">Head</span>
          <ChevronDown size={14} style={{ transform: headOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }} />
        </button>
        {headOpen ? (
          <div className="nav-subgroup">
            {heads.length ? heads.map((group) => (
              <button
                key={group.pair}
                type="button"
                className={`nav-subitem ${activeScreen === "summary" && viewLevel.type === "head" && viewLevel.pair === group.pair ? "active" : ""}`}
                onClick={() => onSelectHead(group.pair)}
              >
                <span>{stationPairName(group.pair)}</span>
              </button>
            )) : <span className="nav-subitem">No data</span>}
          </div>
        ) : null}
      </div>

      <div className="sidebar-filters">
        <label>
          Start
          <input type="datetime-local" value={filters.start_at} onChange={(event) => onUpdateFilter("start_at", event.target.value)} />
        </label>
        <label>
          End
          <input type="datetime-local" value={filters.end_at} onChange={(event) => onUpdateFilter("end_at", event.target.value)} />
        </label>
        <div className="filter-actions">
          <button type="button" className="button-primary" onClick={onApplyFilters} disabled={loading} title="Apply filters">
            <RefreshCw size={17} />
            {loading ? "Applying" : "Apply"}
          </button>
        </div>
      </div>

      <div className="sidebar-glidepath">
        <button type="button" className="nav-item" onClick={onOpenGlidepath}>
          <span className="nav-item-label"><Flag size={15} /> Glidepath Projects</span>
        </button>
        <button type="button" className="nav-item" onClick={onOpenChangeLog}>
          <span className="nav-item-label"><Calendar size={15} /> Add Log</span>
        </button>
        <button type="button" className={`nav-item ${activeScreen === "employees" ? "active" : ""}`} onClick={onOpenEmployees}>
          <span className="nav-item-label"><Users size={15} /> Employees</span>
        </button>
        <button type="button" className={`nav-item ${activeScreen === "changes" ? "active" : ""}`} onClick={onOpenChanges}>
          <span className="nav-item-label"><ListChecks size={15} /> Changes</span>
        </button>
      </div>
    </nav>
  );
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) }
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function NewMilestoneForm({ onCreate }) {
  const [targetDate, setTargetDate] = useState("");
  const [targetPct, setTargetPct] = useState("");
  const [label, setLabel] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event) {
    event.preventDefault();
    if (!targetDate || targetPct === "") return;
    setSaving(true);
    try {
      await onCreate({ target_date: targetDate, target_pct_nok: Number(targetPct), label: label || null });
      setTargetDate("");
      setTargetPct("");
      setLabel("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="milestone-form" onSubmit={submit}>
      <input type="date" value={targetDate} onChange={(e) => setTargetDate(e.target.value)} required />
      <input type="number" step="0.1" min="0" placeholder="Target % NOK" value={targetPct} onChange={(e) => setTargetPct(e.target.value)} required />
      <input type="text" placeholder="Label (optional)" value={label} onChange={(e) => setLabel(e.target.value)} />
      <button type="submit" className="small-button button-primary" disabled={saving}>
        <Plus size={13} /> Add
      </button>
    </form>
  );
}

function SubprojectCard({ subproject, pairOptions, onUpdate, onDelete, onAddMilestone, onDeleteMilestone }) {
  const milestones = [...(subproject.milestones || [])].sort((a, b) => a.target_date.localeCompare(b.target_date));

  function toggleStation(pair) {
    const current = new Set(subproject.station_pairs || []);
    if (current.has(pair)) current.delete(pair);
    else current.add(pair);
    onUpdate({ station_pairs: [...current] });
  }

  return (
    <div className="subproject-card">
      <div className="subproject-card-head">
        <input
          className="inline-input"
          value={subproject.name}
          onChange={(e) => onUpdate({ name: e.target.value })}
          onBlur={(e) => onUpdate({ name: e.target.value })}
        />
        <select value={subproject.status} onChange={(e) => onUpdate({ status: e.target.value })}>
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="archived">Archived</option>
        </select>
        <button type="button" className="icon-button" onClick={onDelete} aria-label="Delete subproject">
          <Trash2 size={15} />
        </button>
      </div>

      <div className="subproject-field">
        <span className="subproject-field-label">Machines</span>
        <div className="station-chip-row">
          {pairOptions.map((pair) => (
            <button
              type="button"
              key={pair}
              className={`station-chip ${(subproject.station_pairs || []).includes(pair) ? "active" : ""}`}
              onClick={() => toggleStation(pair)}
            >
              {stationPairName(pair)}
            </button>
          ))}
        </div>
      </div>

      <div className="subproject-field-row">
        <label>
          Start date
          <input type="date" value={subproject.start_date} onChange={(e) => onUpdate({ start_date: e.target.value })} />
        </label>
        <label>
          Start % NOK
          <input
            type="number"
            step="0.1"
            min="0"
            value={subproject.start_pct_nok}
            onChange={(e) => onUpdate({ start_pct_nok: Number(e.target.value) })}
          />
        </label>
      </div>

      <div className="subproject-field">
        <span className="subproject-field-label">Milestones</span>
        {milestones.length ? (
          <ul className="milestone-list">
            {milestones.map((milestone) => (
              <li key={milestone.id}>
                <span className="milestone-date">{milestone.target_date}</span>
                <span className="milestone-target">{milestone.target_pct_nok}% NOK</span>
                {milestone.label ? <span className="milestone-label">{milestone.label}</span> : null}
                <button type="button" className="icon-button" onClick={() => onDeleteMilestone(milestone.id)} aria-label="Delete milestone">
                  <X size={13} />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <span className="milestone-empty">No milestones yet</span>
        )}
        <NewMilestoneForm onCreate={onAddMilestone} />
      </div>
    </div>
  );
}

function NewSubprojectForm({ pairOptions, onCreate }) {
  const [name, setName] = useState("");
  const [selectedPairs, setSelectedPairs] = useState([]);
  const [startDate, setStartDate] = useState("");
  const [startPct, setStartPct] = useState("");
  const [saving, setSaving] = useState(false);

  function toggleStation(pair) {
    setSelectedPairs((current) => (current.includes(pair) ? current.filter((p) => p !== pair) : [...current, pair]));
  }

  async function submit(event) {
    event.preventDefault();
    if (!name.trim() || !selectedPairs.length || !startDate || startPct === "") return;
    setSaving(true);
    try {
      await onCreate({
        name: name.trim(),
        station_pairs: selectedPairs,
        start_date: startDate,
        start_pct_nok: Number(startPct)
      });
      setName("");
      setSelectedPairs([]);
      setStartDate("");
      setStartPct("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="new-subproject-form" onSubmit={submit}>
      <input type="text" placeholder="Subproject name" value={name} onChange={(e) => setName(e.target.value)} required />
      <div className="station-chip-row">
        {pairOptions.map((pair) => (
          <button
            type="button"
            key={pair}
            className={`station-chip ${selectedPairs.includes(pair) ? "active" : ""}`}
            onClick={() => toggleStation(pair)}
          >
            {stationPairName(pair)}
          </button>
        ))}
      </div>
      <div className="subproject-field-row">
        <label>
          Start date
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
        </label>
        <label>
          Start % NOK
          <input type="number" step="0.1" min="0" placeholder="e.g. 4.8" value={startPct} onChange={(e) => setStartPct(e.target.value)} required />
        </label>
      </div>
      <button type="submit" className="button-primary" disabled={saving}>
        <Plus size={15} /> Add Subproject
      </button>
    </form>
  );
}

function ProjectCard({ project, pairOptions, onRefresh }) {
  const [expanded, setExpanded] = useState(true);

  async function updateSubproject(subprojectId, patch) {
    await apiRequest(`/api/v1/glidepath/subprojects/${subprojectId}`, { method: "PATCH", body: JSON.stringify(patch) });
    onRefresh();
  }

  async function deleteSubproject(subprojectId) {
    await apiRequest(`/api/v1/glidepath/subprojects/${subprojectId}`, { method: "DELETE" });
    onRefresh();
  }

  async function addMilestone(subprojectId, payload) {
    await apiRequest(`/api/v1/glidepath/subprojects/${subprojectId}/milestones`, { method: "POST", body: JSON.stringify(payload) });
    onRefresh();
  }

  async function deleteMilestone(milestoneId) {
    await apiRequest(`/api/v1/glidepath/milestones/${milestoneId}`, { method: "DELETE" });
    onRefresh();
  }

  async function createSubproject(payload) {
    await apiRequest(`/api/v1/glidepath/projects/${project.id}/subprojects`, { method: "POST", body: JSON.stringify(payload) });
    onRefresh();
  }

  async function deleteProject() {
    await apiRequest(`/api/v1/glidepath/projects/${project.id}`, { method: "DELETE" });
    onRefresh();
  }

  return (
    <div className="project-card">
      <div className="project-card-head">
        <button type="button" className="project-card-title" onClick={() => setExpanded((v) => !v)}>
          <ChevronDown size={15} style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.15s ease" }} />
          <span>{project.name}</span>
          <span className="nav-badge">{(project.subprojects || []).length}</span>
        </button>
        <button type="button" className="icon-button" onClick={deleteProject} aria-label="Delete project">
          <Trash2 size={15} />
        </button>
      </div>
      {expanded ? (
        <div className="project-card-body">
          {(project.subprojects || []).map((subproject) => (
            <SubprojectCard
              key={subproject.id}
              subproject={subproject}
              pairOptions={pairOptions}
              onUpdate={(patch) => updateSubproject(subproject.id, patch)}
              onDelete={() => deleteSubproject(subproject.id)}
              onAddMilestone={(payload) => addMilestone(subproject.id, payload)}
              onDeleteMilestone={deleteMilestone}
            />
          ))}
          <NewSubprojectForm pairOptions={pairOptions} onCreate={createSubproject} />
        </div>
      ) : null}
    </div>
  );
}

function GlidepathManager({ projects, pairOptions, onClose, onRefresh }) {
  const [newProjectName, setNewProjectName] = useState("");
  const [saving, setSaving] = useState(false);

  async function createProject(event) {
    event.preventDefault();
    if (!newProjectName.trim()) return;
    setSaving(true);
    try {
      await apiRequest("/api/v1/glidepath/projects", { method: "POST", body: JSON.stringify({ name: newProjectName.trim() }) });
      setNewProjectName("");
      onRefresh();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="multi-select-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="glidepath-modal">
        <div className="multi-select-modal-head">
          <span>Glidepath Projects</span>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        <form className="new-project-form" onSubmit={createProject}>
          <input type="text" placeholder="New project name" value={newProjectName} onChange={(e) => setNewProjectName(e.target.value)} />
          <button type="submit" className="button-primary" disabled={saving}>
            <Plus size={15} /> Add Project
          </button>
        </form>

        <div className="project-list">
          {projects.length ? projects.map((project) => (
            <ProjectCard key={project.id} project={project} pairOptions={pairOptions} onRefresh={onRefresh} />
          )) : <div className="empty-option">No projects yet. Create one above.</div>}
        </div>
      </div>
    </div>
  );
}

function employeeDisplay(employee) {
  if (!employee) return "";
  return `${employee.employee_number} - ${employee.full_name}`;
}

function NewChangeLogForm({ pairOptions, optionsLoading, employees, employeesLoading, onCreate, onSuccessMessageClear }) {
  const [stationPair, setStationPair] = useState(pairOptions[0] || "");
  const [employeeId, setEmployeeId] = useState(employees[0]?.id ? String(employees[0].id) : "");
  const [side, setSide] = useState("both");
  const [changeDate, setChangeDate] = useState("");
  const [changeTime, setChangeTime] = useState("");
  const [category, setCategory] = useState(CHANGE_LOG_CATEGORIES[0]);
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const isOther = category === "Other";
  const descriptionMinLength = 20;

  function descriptionError(value) {
    const trimmed = value.trim();
    if (!trimmed) return "Description is required.";
    if (trimmed.length < descriptionMinLength) return `Description must have at least ${descriptionMinLength} non-space characters.`;
    return "";
  }

  function syncDescriptionValidation(input) {
    input.setCustomValidity(descriptionError(input.value));
  }

  useEffect(() => {
    if (!stationPair && pairOptions.length) {
      setStationPair(pairOptions[0]);
    }
  }, [pairOptions, stationPair]);

  useEffect(() => {
    if (!employeeId && employees.length) {
      setEmployeeId(String(employees[0].id));
    }
  }, [employees, employeeId]);

  async function submit(event) {
    event.preventDefault();
    if (!stationPair || !changeDate || !employeeId) return;
    if (isOther && !label.trim()) return;
    const descriptionInput = event.currentTarget.elements.description;
    syncDescriptionValidation(descriptionInput);
    if (!event.currentTarget.reportValidity()) return;
    setSaving(true);
    try {
      await onCreate({
        station_pair: stationPair,
        side,
        change_date: changeDate,
        change_time: changeTime || null,
        employee_id: Number(employeeId),
        category,
        label: isOther ? label.trim() : null,
        description: description.trim()
      });
      setChangeDate("");
      setChangeTime("");
      setLabel("");
      setDescription("");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="new-change-log-form" onSubmit={submit}>
      <div className="subproject-field-row">
        <label>
          Machine
          <select
            value={stationPair}
            onChange={(e) => {
              onSuccessMessageClear();
              setStationPair(e.target.value);
            }}
            disabled={optionsLoading || !pairOptions.length}
          >
            {pairOptions.map((pair) => (
              <option key={pair} value={pair}>{stationPairName(pair)}</option>
            ))}
          </select>
        </label>
        <label>
          Employee
          <select
            value={employeeId}
            onChange={(e) => {
              onSuccessMessageClear();
              setEmployeeId(e.target.value);
            }}
            disabled={employeesLoading || !employees.length}
            required
          >
            {employees.map((employee) => (
              <option key={employee.id} value={employee.id}>{employeeDisplay(employee)}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="subproject-field-row">
        <label>
          Side
          <select value={side} onChange={(e) => {
            onSuccessMessageClear();
            setSide(e.target.value);
          }}>
            <option value="both">Both</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
          </select>
        </label>
        <label>
          Date
          <input type="date" value={changeDate} onChange={(e) => {
            onSuccessMessageClear();
            setChangeDate(e.target.value);
          }} required />
        </label>
      </div>
      <div className="subproject-field-row">
        <label>
          Time (optional)
          <input type="time" value={changeTime} onChange={(e) => {
            onSuccessMessageClear();
            setChangeTime(e.target.value);
          }} />
        </label>
        <span className="form-spacer" aria-hidden="true" />
      </div>
      <label>
        Category
        <select value={category} onChange={(e) => {
          onSuccessMessageClear();
          setCategory(e.target.value);
        }}>
          {CHANGE_LOG_CATEGORIES.map((option) => (
            <option key={option} value={option}>{option}</option>
          ))}
        </select>
      </label>
      {isOther ? (
        <label>
          Label
          <input
            type="text"
            placeholder="e.g. Fixture swap"
            value={label}
            onChange={(e) => {
              onSuccessMessageClear();
              setLabel(e.target.value);
            }}
            required
          />
        </label>
      ) : null}
      <label>
        Description
        <input
          type="text"
          name="description"
          placeholder="Details, work order, etc."
          value={description}
          onChange={(e) => {
            onSuccessMessageClear();
            setDescription(e.target.value);
            syncDescriptionValidation(e.target);
          }}
          onInvalid={(e) => syncDescriptionValidation(e.target)}
          required
        />
      </label>
      <button type="submit" className="button-primary" disabled={saving || optionsLoading || employeesLoading || !pairOptions.length || !employees.length}>
        <Plus size={15} /> Log Change
      </button>
    </form>
  );
}

function ChangeLogManager({ pairOptions, optionsLoading, employees, employeesLoading, onClose, onRefresh }) {
  const [successMessage, setSuccessMessage] = useState("");

  async function createEntry(payload) {
    await apiRequest("/api/v1/change-log", { method: "POST", body: JSON.stringify(payload) });
    onRefresh();
    setSuccessMessage("New log added.");
  }

  return (
    <div className="multi-select-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="glidepath-modal">
        <div className="multi-select-modal-head">
          <span>Add Logs</span>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {optionsLoading ? <div className="loading add-log-loading">Loading machines...</div> : null}
        {employeesLoading ? <div className="loading add-log-loading">Loading employees...</div> : null}
        {!employeesLoading && !employees.length ? <div className="error add-log-loading">Add an employee before creating a log.</div> : null}
        {successMessage ? <div className="success add-log-success">{successMessage}</div> : null}

        <NewChangeLogForm
          pairOptions={pairOptions}
          optionsLoading={optionsLoading}
          employees={employees}
          employeesLoading={employeesLoading}
          onCreate={createEntry}
          onSuccessMessageClear={() => setSuccessMessage("")}
        />
      </div>
    </div>
  );
}

function AddEmployeeModal({ employee, onClose, onRefresh }) {
  const isEditing = Boolean(employee);
  const [employeeNumber, setEmployeeNumber] = useState(employee?.employee_number || "");
  const [fullName, setFullName] = useState(employee?.full_name || "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function createEmployee(event) {
    event.preventDefault();
    if (!employeeNumber.trim() || !fullName.trim()) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      await apiRequest(isEditing ? `/api/v1/employees/${employee.id}` : "/api/v1/employees", {
        method: isEditing ? "PATCH" : "POST",
        body: JSON.stringify({
          employee_number: employeeNumber.trim(),
          full_name: fullName.trim()
        })
      });
      onRefresh();
      if (isEditing) {
        onClose();
      } else {
        setEmployeeNumber("");
        setFullName("");
        setMessage("Employee added.");
      }
    } catch (exc) {
      setError(exc.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="multi-select-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="glidepath-modal">
        <div className="multi-select-modal-head">
          <span>{isEditing ? "Edit Employee" : "Add Employee"}</span>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {error ? <div className="error add-log-loading">{error}</div> : null}
        {message ? <div className="success add-log-success">{message}</div> : null}

        <form className="employee-form" onSubmit={createEmployee}>
          <div className="subproject-field-row">
            <label>
              Employee number
              <input
                type="text"
                value={employeeNumber}
                maxLength={10}
                onChange={(event) => {
                  setEmployeeNumber(event.target.value);
                  setError("");
                  setMessage("");
                }}
                required
              />
            </label>
            <label>
              Full name
              <input
                type="text"
                value={fullName}
                maxLength={50}
                onChange={(event) => {
                  setFullName(event.target.value);
                  setError("");
                  setMessage("");
                }}
                required
              />
            </label>
          </div>
          <button type="submit" className="button-primary" disabled={saving}>
            {isEditing ? <Pencil size={15} /> : <UserPlus size={15} />}
            {isEditing ? "Save Employee" : "Add Employee"}
          </button>
        </form>
      </div>
    </div>
  );
}

function EmployeeScreen({ employees, loading, onOpenCreate, onOpenEdit, onRefresh }) {
  const [error, setError] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const sortedEmployees = [...employees].sort((a, b) => {
    const nameCompare = String(a.full_name || "").localeCompare(String(b.full_name || ""));
    if (nameCompare !== 0) return nameCompare;
    return String(a.employee_number || "").localeCompare(String(b.employee_number || ""));
  });

  async function deleteEmployee(employee) {
    const confirmed = window.confirm(`Delete employee ${employeeDisplay(employee)}? Logs will remain as Unassigned.`);
    if (!confirmed) return;
    setDeletingId(employee.id);
    setError("");
    try {
      await apiRequest(`/api/v1/employees/${employee.id}`, { method: "DELETE" });
      onRefresh();
    } catch (exc) {
      setError(exc.message);
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <>
      <header className="topbar">
        <div>
          <span className="eyebrow">Vision - Quality Analytics</span>
          <h1>Employees</h1>
          <p>Employee directory for process change logs</p>
        </div>
        <div className="actions">
          <button type="button" className="button-primary" onClick={onOpenCreate}>
            <UserPlus size={17} /> Add Employee
          </button>
        </div>
      </header>

      {loading ? <div className="loading">Loading employees...</div> : null}
      {error ? <div className="error">{error}</div> : null}

      <section className="employee-screen">
        <table className="employee-table">
          <thead>
            <tr>
              <th>Employee number</th>
              <th>Full name</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {sortedEmployees.length ? sortedEmployees.map((employee) => (
              <tr className="employee-table-row" key={employee.id}>
                <td className="employee-table-number">{employee.employee_number}</td>
                <td className="employee-table-name">{employee.full_name}</td>
                <td className="employee-table-actions">
                  <button type="button" className="icon-button" onClick={() => onOpenEdit(employee)} aria-label="Edit employee">
                    <Pencil size={14} />
                  </button>
                  <button type="button" className="icon-button" onClick={() => deleteEmployee(employee)} disabled={deletingId === employee.id} aria-label="Delete employee">
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td className="empty-option" colSpan="3">No employees yet. Add one from this screen.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}

function ChangeLogScreen({ entries, onRefresh }) {
  async function deleteEntry(entryId) {
    await apiRequest(`/api/v1/change-log/${entryId}`, { method: "DELETE" });
    onRefresh();
  }

  const sortedEntries = [...entries].sort((a, b) => {
    const dateCompare = b.change_date.localeCompare(a.change_date);
    if (dateCompare !== 0) return dateCompare;
    return (b.change_time || "").localeCompare(a.change_time || "");
  });

  return (
    <>
      <header className="topbar">
        <div>
          <span className="eyebrow">Vision - Quality Analytics</span>
          <h1>Changes</h1>
          <p>Process change log</p>
        </div>
      </header>

      <section className="change-log-screen">
        <table className="change-log-table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Machine</th>
              <th>Side</th>
              <th>Employee</th>
              <th>Category</th>
              <th>Label</th>
              <th>Description</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {sortedEntries.length ? sortedEntries.map((entry) => (
              <tr className="change-log-row" key={entry.id}>
                <td className="change-log-row-date">{entry.change_date}{entry.change_time ? ` ${entry.change_time.slice(0, 5)}` : ""}</td>
                <td className="change-log-row-machine">{stationPairName(entry.station_pair)}</td>
                <td className="change-log-row-side">{entry.side}</td>
                <td className="change-log-row-employee">{entry.employee_number && entry.employee_name ? `${entry.employee_number} - ${entry.employee_name}` : "Unassigned"}</td>
                <td><span className="change-log-row-category">{entry.category}</span></td>
                <td className="change-log-row-label">{entry.category === "Other" ? entry.label : ""}</td>
                <td className="change-log-row-desc">{entry.description || "No description"}</td>
                <td className="change-log-row-actions">
                  <button type="button" className="icon-button" onClick={() => deleteEntry(entry.id)} aria-label="Delete entry">
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            )) : (
              <tr>
                <td className="empty-option" colSpan="8">No logs yet. Add one from Add Log.</td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </>
  );
}

function filterDataToStations(data, allowedStations) {
  if (!data) return data;
  const allowed = new Set(allowedStations);
  const keep = (rows = [], key = "source_station") => rows.filter((row) => allowed.has(row[key] || ""));
  return {
    ...data,
    stations: keep(data.stations),
    daily: keep(data.daily),
    condition_periods: keep(data.condition_periods),
    condition_totals: keep(data.condition_totals),
    top3_history: keep(data.top3_history)
  };
}

function App() {
  const [options, setOptions] = useState({ source_stations: [], station_pairs: [], part_numbers: [] });
  const [optionsLoading, setOptionsLoading] = useState(true);
  const [filters, setFilters] = useState(() => ({
    ...defaultDateRange(),
    station_pairs: [],
    part_numbers: []
  }));
  const [appliedFilters, setAppliedFilters] = useState(null);
  const [loadedData, setLoadedData] = useState(null);
  const [loadedServerFilters, setLoadedServerFilters] = useState(null);
  const [activeScreen, setActiveScreen] = useState("summary");
  const [activeTab, setActiveTab] = useState("daily");
  const [viewLevel, setViewLevel] = useState({ type: "overall" });
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [projects, setProjects] = useState([]);
  const [showGlidepathManager, setShowGlidepathManager] = useState(false);
  const [changeLogEntries, setChangeLogEntries] = useState([]);
  const [showChangeLogManager, setShowChangeLogManager] = useState(false);
  const [employees, setEmployees] = useState([]);
  const [employeesLoading, setEmployeesLoading] = useState(true);
  const [showEmployeeManager, setShowEmployeeManager] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);

  useEffect(() => {
    setOptionsLoading(true);
    fetchJson("/api/v1/options")
      .then((payload) => {
        setOptions(payload);
      })
      .catch((exc) => setError(exc.message))
      .finally(() => setOptionsLoading(false));
  }, []);

  const reloadProjects = () => {
    fetchJson("/api/v1/glidepath/projects")
      .then((payload) => setProjects(payload.items || []))
      .catch(() => {});
  };

  const reloadChangeLog = () => {
    return fetchJson("/api/v1/change-log")
      .then((payload) => setChangeLogEntries(payload.items || []))
      .catch(() => {});
  };

  const reloadEmployees = () => {
    setEmployeesLoading(true);
    return fetchJson("/api/v1/employees")
      .then((payload) => setEmployees(payload.items || []))
      .catch(() => {})
      .finally(() => setEmployeesLoading(false));
  };

  const reloadEmployeesAndChangeLog = () => Promise.all([reloadEmployees(), reloadChangeLog()]);

  useEffect(() => {
    reloadProjects();
    reloadChangeLog();
    reloadEmployees();
  }, []);

  const apiFilters = useMemo(() => dashboardFilters(filters), [filters]);
  const visibleData = useMemo(
    () => filterReportData(loadedData, appliedFilters?.station_pairs || [], appliedFilters?.part_numbers || []),
    [loadedData, appliedFilters]
  );

  async function applyFilters(targetFilters = filters) {
    const nextFilters = dashboardFilters(targetFilters);
    const nextServerFilters = serverFilters(nextFilters);
    if (loadedData && sameDateFilters(nextServerFilters, loadedServerFilters)) {
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

  const stations = stationList(visibleData);
  const combinedData = useMemo(() => combinedAsStationData(visibleData), [visibleData]);
  const combinedStations = stationList(combinedData);
  const canDownloadExcel = Boolean(visibleData) && !loading && !exporting && sameFilters(apiFilters, appliedFilters);

  function selectMachine(pair) {
    setActiveScreen("summary");
    setViewLevel({ type: "machine", pair });
    const nextStationPairs = pair && pair !== MACHINE_ALL ? [pair] : [];
    setFilters((current) => ({ ...current, station_pairs: nextStationPairs }));
    applyFilters({ ...filters, station_pairs: nextStationPairs });
  }

  function selectHead(pair) {
    setActiveScreen("summary");
    setViewLevel({ type: "head", pair });
    setFilters((current) => ({ ...current, station_pairs: [pair] }));
    applyFilters({ ...filters, station_pairs: [pair] });
  }

  function selectOverall() {
    setActiveScreen("summary");
    setViewLevel({ type: "overall" });
    setFilters((current) => ({ ...current, station_pairs: [] }));
    applyFilters({ ...filters, station_pairs: [] });
  }

  function closeEmployeeManager() {
    setShowEmployeeManager(false);
    setEditingEmployee(null);
  }

  const showByHead = viewLevel.type === "head";
  const showAllMachines = viewLevel.type === "machine" && viewLevel.pair === MACHINE_ALL;
  const showOverall = viewLevel.type === "overall";
  const leftStation = showByHead ? stations.find((s) => /LEFT$/i.test(s)) : null;
  const rightStation = showByHead ? stations.find((s) => /RIGHT$/i.test(s)) : null;
  const leftData = useMemo(() => (showByHead ? filterDataToStations(visibleData, [leftStation]) : null), [showByHead, visibleData, leftStation]);
  const rightData = useMemo(() => (showByHead ? filterDataToStations(visibleData, [rightStation]) : null), [showByHead, visibleData, rightStation]);
  const overallData = useMemo(() => (showOverall ? plantWideData(combinedData) : null), [showOverall, combinedData]);
  const overallStations = stationList(overallData);
  const colorsByDefect = useMemo(() => defectColorMap(visibleData), [visibleData]);
  const combinedColorsByDefect = useMemo(() => defectColorMap(combinedData), [combinedData]);
  const overallColorsByDefect = useMemo(() => defectColorMap(overallData), [overallData]);

  const levelTitle = showOverall
    ? "Overall - Whole Plant"
    : viewLevel.type === "machine"
      ? `Machine - ${showAllMachines ? "All Machines" : stationPairName(viewLevel.pair)}`
      : `Head - ${stationPairName(viewLevel.pair)}`;

  const displayData = showByHead ? visibleData : showOverall ? overallData : combinedData;
  const displayStations = showByHead ? stations : showOverall ? overallStations : combinedStations;
  const displayColors = showByHead ? colorsByDefect : showOverall ? overallColorsByDefect : combinedColorsByDefect;

  const glidepathScopeStations = showByHead ? stations : combinedStations;
  const activeSubprojects = useMemo(
    () => findActiveSubprojects(projects, glidepathScopeStations),
    [projects, glidepathScopeStations.join("|")]
  );
  const leftSubprojects = showByHead ? findActiveSubprojects(projects, [leftStation]) : [];
  const rightSubprojects = showByHead ? findActiveSubprojects(projects, [rightStation]) : [];

  const scopedChangeLogEntries = useMemo(
    () => findChangeLogEntries(changeLogEntries, glidepathScopeStations),
    [changeLogEntries, glidepathScopeStations.join("|")]
  );
  const leftChangeLogEntries = showByHead ? findChangeLogEntries(changeLogEntries, [leftStation]) : [];
  const rightChangeLogEntries = showByHead ? findChangeLogEntries(changeLogEntries, [rightStation]) : [];

  return (
    <div className="app-shell">
      <Sidebar
        options={options}
        activeScreen={activeScreen}
        viewLevel={viewLevel}
        onSelectOverall={selectOverall}
        onSelectMachine={selectMachine}
        onSelectHead={selectHead}
        filters={filters}
        onUpdateFilter={updateFilter}
        onApplyFilters={() => applyFilters()}
        loading={loading}
        onOpenGlidepath={() => setShowGlidepathManager(true)}
        onOpenChangeLog={() => setShowChangeLogManager(true)}
        onOpenEmployees={() => setActiveScreen("employees")}
        onOpenChanges={() => setActiveScreen("changes")}
      />
      {showGlidepathManager ? (
        <GlidepathManager
          projects={projects}
          pairOptions={stationPairOptions(options)}
          onClose={() => setShowGlidepathManager(false)}
          onRefresh={reloadProjects}
        />
      ) : null}
      {showChangeLogManager ? (
        <ChangeLogManager
          pairOptions={stationPairOptions(options)}
          optionsLoading={optionsLoading}
          employees={employees}
          employeesLoading={employeesLoading}
          onClose={() => setShowChangeLogManager(false)}
          onRefresh={reloadChangeLog}
        />
      ) : null}
      {showEmployeeManager ? (
        <AddEmployeeModal
          employee={editingEmployee}
          onClose={closeEmployeeManager}
          onRefresh={reloadEmployeesAndChangeLog}
        />
      ) : null}
      <main>
        {activeScreen === "changes" ? (
          <ChangeLogScreen entries={changeLogEntries} onRefresh={reloadChangeLog} />
        ) : activeScreen === "employees" ? (
          <EmployeeScreen
            employees={employees}
            loading={employeesLoading}
            onOpenCreate={() => {
              setEditingEmployee(null);
              setShowEmployeeManager(true);
            }}
            onOpenEdit={(employee) => {
              setEditingEmployee(employee);
              setShowEmployeeManager(true);
            }}
            onRefresh={reloadEmployeesAndChangeLog}
          />
        ) : (
          <>
        <header className="topbar">
          <div>
            <span className="eyebrow">Vision - Quality Analytics</span>
            <h1>Reject Summary</h1>
            <p>{levelTitle}</p>
          </div>
          <div className="actions">
            <button type="button" className="button-success" onClick={downloadExcel} disabled={!canDownloadExcel} title="Download Excel">
              <Download size={17} />
              {exporting ? "Exporting" : "Excel"}
            </button>
          </div>
        </header>

        {visibleData && !showByHead ? <KpiRow data={displayData} stationCount={displayStations.length} /> : null}

        {viewLevel.type === "overall" && visibleData ? (
          <section className="overview-grid">
            {combinedStations.map((pair) => {
              const row = (combinedData?.stations || []).find((item) => item.source_station === pair);
              const pctNok = Number(row?.pct_nok || 0);
              const status = pctNok === 0 ? "ok" : pctNok < 0.02 ? "warn" : "bad";
              return (
                <button type="button" key={pair} className="overview-card" onClick={() => selectMachine(pair)}>
                  <div className="overview-card-head">
                    <span className="overview-card-title">{stationPairName(pair)}</span>
                    <span className={`status-dot ${status}`} />
                  </div>
                  <span className="overview-card-rate">{percentFormat(1 - pctNok)} OK</span>
                  <div className="overview-card-bar">
                    <div className="overview-card-bar-fill" style={{ width: `${Math.max(0, Math.min(100, (1 - pctNok) * 100))}%` }} />
                  </div>
                  <div className="overview-card-sub">
                    <span>{numberFormat(row?.total_pieces)} pieces</span>
                    <span>{numberFormat(row?.nok_pieces)} NOK</span>
                  </div>
                </button>
              );
            })}
          </section>
        ) : null}

        {error ? <div className="error">{error}</div> : null}
        {loading ? <div className="loading">Loading data...</div> : null}

        <nav className="tabs" aria-label="Reject summary tabs">
          {TABS.map((tab) => (
            <TabButton key={tab.id} tab={tab} active={activeTab === tab.id} onClick={() => setActiveTab(tab.id)} />
          ))}
        </nav>

        {visibleData && showByHead ? (
          <div className="head-columns">
            <div className="head-column">
              <SectionTitle>{stationName(leftStation) || "Left"}</SectionTitle>
              <KpiRow data={leftData} stationCount={leftStation ? 1 : 0} />
              {activeTab === "daily" ? <DailyTab data={leftData} stations={[leftStation]} glidepathSubprojects={leftSubprojects} changeLogEntries={leftChangeLogEntries} /> : null}
              {activeTab === "conditions" ? <ConditionsTab data={leftData} stations={[leftStation]} colorsByDefect={colorsByDefect} /> : null}
              {activeTab === "top3" ? <Top3Tab data={leftData} stations={[leftStation]} colorsByDefect={colorsByDefect} /> : null}
            </div>
            <div className="head-column">
              <SectionTitle>{stationName(rightStation) || "Right"}</SectionTitle>
              <KpiRow data={rightData} stationCount={rightStation ? 1 : 0} />
              {activeTab === "daily" ? <DailyTab data={rightData} stations={[rightStation]} glidepathSubprojects={rightSubprojects} changeLogEntries={rightChangeLogEntries} /> : null}
              {activeTab === "conditions" ? <ConditionsTab data={rightData} stations={[rightStation]} colorsByDefect={colorsByDefect} /> : null}
              {activeTab === "top3" ? <Top3Tab data={rightData} stations={[rightStation]} colorsByDefect={colorsByDefect} /> : null}
            </div>
          </div>
        ) : null}

        {visibleData && !showByHead && activeTab === "daily" ? (
          <DailyTab
            data={displayData}
            stations={displayStations}
            showPartNumberBands={viewLevel.type !== "overall"}
            glidepathSubprojects={activeSubprojects}
            changeLogEntries={scopedChangeLogEntries}
          />
        ) : null}
        {visibleData && !showByHead && activeTab === "conditions" ? (
          <ConditionsTab data={displayData} stations={displayStations} colorsByDefect={displayColors} />
        ) : null}
        {visibleData && !showByHead && activeTab === "top3" ? (
          <Top3Tab data={displayData} stations={displayStations} colorsByDefect={displayColors} />
        ) : null}
        {!visibleData && !loading ? <Empty label="No data loaded" /> : null}
          </>
        )}
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
