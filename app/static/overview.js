// overview.js — the Overview dashboard: KPIs, firmware chart, needs-attention, recent activity.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
// All KPI/list/chart data comes from the registry + OTA REST APIs. It must look complete under
// scripts/dev.sh (SQLite, no broker/Influx): registry widgets show real data; telemetry-derived
// widgets render the designed empty state, never a broken chart.
"use strict";

(function () {
  if (!requireToken()) return;

  const CERT_WARN_DAYS = 30;
  const groupFilter = document.getElementById("overview-group");
  let devices = [];
  let firmware = [];
  let certInfo = null;
  let firmwareChart = null;

  const el = (id) => document.getElementById(id);

  // --- KPIs (all registry-derived → work without Docker) ---
  function visible() {
    const g = groupFilter.value;
    return g ? devices.filter((d) => d.group_id === g) : devices;
  }

  function attentionItems(list) {
    const items = list
      .filter((d) => !d.online)
      .map((d) => ({ id: d.id, kind: "offline", label: "offline" }));
    if (certInfo && certInfo.expires_in_days != null && certInfo.expires_in_days < CERT_WARN_DAYS) {
      items.unshift({
        id: null,
        kind: "cert",
        label: `CA cert expires in ${certInfo.expires_in_days}d`,
      });
    }
    return items;
  }

  function renderKpis() {
    const list = visible();
    const total = list.length;
    const online = list.filter((d) => d.online).length;
    const versions = new Set(list.map((d) => d.firmware_version).filter(Boolean));
    const attention = attentionItems(list);

    el("kpi-total").textContent = total;

    el("kpi-online").textContent = online;
    const pct = el("kpi-online-pct");
    if (total > 0) {
      pct.textContent = `${Math.round((online / total) * 100)}% of fleet`;
      pct.classList.remove("hidden");
    } else {
      pct.classList.add("hidden");
    }

    el("kpi-attention").textContent = attention.length;
    const note = el("kpi-attention-note");
    if (attention.length > 0) {
      note.textContent = "review below";
      note.classList.remove("hidden");
    } else {
      note.classList.add("hidden");
    }

    el("kpi-firmware").textContent = versions.size;
  }

  // --- needs-attention list ---
  function pill(kind) {
    const cls = kind === "offline" ? "pill-offline" : "pill-warn";
    return cls;
  }

  function renderNeedsAttention() {
    const items = attentionItems(visible());
    const host = el("needs-attention");
    const count = el("needs-count");
    count.textContent = items.length ? `${items.length} item(s)` : "";
    host.replaceChildren();
    if (items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.innerHTML =
        '<div class="icon-tile" aria-hidden="true">✓</div><p>All clear — every device is online and certificates are healthy.</p>';
      host.appendChild(empty);
      return;
    }
    const wrap = document.createElement("div");
    wrap.className = "flex-col";
    for (const it of items) {
      const row = document.createElement("div");
      row.className = "flex";
      const left = document.createElement("div");
      left.className = "flex push";
      if (it.id) {
        const a = document.createElement("a");
        a.className = "mono";
        a.href = `/ui/devices/${encodeURIComponent(it.id)}`;
        a.textContent = it.id;
        left.appendChild(a);
      } else {
        const span = document.createElement("span");
        span.className = "small";
        span.textContent = "CA certificate";
        left.appendChild(span);
      }
      const tag = document.createElement("span");
      tag.className = `pill ${pill(it.kind)}`;
      tag.textContent = it.label;
      row.appendChild(left);
      row.appendChild(tag);
      wrap.appendChild(row);
    }
    host.appendChild(wrap);
  }

  // --- firmware distribution chart (registry-derived; works without Docker) ---
  function firmwareCounts(list) {
    const counts = new Map();
    for (const d of list) {
      const key = d.firmware_version || "unknown";
      counts.set(key, (counts.get(key) || 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }

  function renderFirmwareChart() {
    const canvas = el("chart-firmware");
    const empty = el("chart-firmware-empty");
    const entries = firmwareCounts(visible());
    if (typeof Chart === "undefined" || entries.length === 0) {
      empty.classList.toggle("hidden", entries.length !== 0);
      if (entries.length === 0) canvas.classList.add("hidden");
      return;
    }
    canvas.classList.remove("hidden");
    empty.classList.add("hidden");
    const t = chartTokens();
    const data = {
      labels: entries.map((e) => e[0]),
      datasets: [
        {
          label: "Devices",
          data: entries.map((e) => e[1]),
          backgroundColor: t.blue,
          hoverBackgroundColor: t.lime,
          borderRadius: 6,
          maxBarThickness: 26,
        },
      ],
    };
    const opts = {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { color: t.muted, font: { family: t.font }, precision: 0 },
          grid: { color: t.line },
        },
        y: {
          ticks: { color: t.muted, font: { family: t.font, weight: "700" } },
          grid: { display: false },
        },
      },
    };
    if (firmwareChart) firmwareChart.destroy();
    firmwareChart = new Chart(canvas.getContext("2d"), { type: "bar", data, options: opts });
  }

  // The devices-online-over-time chart needs a telemetry history API (not present under dev.sh);
  // it intentionally stays on the designed empty state until the metrics stack is wired.
  function renderOnlineChart() {
    el("chart-online").classList.add("hidden");
    el("chart-online-empty").classList.remove("hidden");
  }

  // --- recent OTA / activity (OTA API; unavailable under dev.sh → graceful empty) ---
  function renderRecentOta() {
    const host = el("recent-ota");
    host.replaceChildren();
    if (firmware.length === 0) {
      const line = document.createElement("div");
      line.className = "line ts";
      line.textContent = "› no firmware uploaded yet — upload one from the OTA page";
      host.appendChild(line);
      return;
    }
    const recent = [...firmware]
      .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
      .slice(0, 8);
    for (const fw of recent) {
      const line = document.createElement("div");
      line.className = "line";
      const ts = fw.created_at ? new Date(fw.created_at).toLocaleString() : "—";
      line.textContent = `› ${fw.name} ${fw.version}`;
      const tsSpan = document.createElement("span");
      tsSpan.className = "ts";
      tsSpan.textContent = `  ${ts}`;
      line.appendChild(tsSpan);
      host.appendChild(line);
    }
  }

  function renderAll() {
    renderKpis();
    renderNeedsAttention();
    renderFirmwareChart();
    renderOnlineChart();
    renderRecentOta();
  }

  function populateGroups() {
    const groups = [...new Set(devices.map((d) => d.group_id))].sort();
    const current = groupFilter.value;
    groupFilter.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All groups";
    groupFilter.appendChild(all);
    for (const g of groups) {
      const opt = document.createElement("option");
      opt.value = g;
      opt.textContent = g;
      groupFilter.appendChild(opt);
    }
    groupFilter.value = current;
  }

  async function load() {
    try {
      const body = await apiFetch("/api/v1/devices");
      devices = body.data || [];
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Could not load devices: ${err.message}`, "danger");
      devices = [];
    }
    // Cert + firmware are best-effort: the dashboard is complete without them.
    try {
      const certs = await apiFetch("/api/v1/system/certs");
      certInfo = certs.data || null;
    } catch (err) {
      certInfo = null;
    }
    try {
      const fw = await apiFetch("/api/v1/ota/firmware");
      firmware = fw.data || [];
    } catch (err) {
      firmware = []; // OTA backend (Hawkbit) absent under dev.sh — show the empty state
    }
    populateGroups();
    renderAll();
  }

  el("overview-refresh").addEventListener("click", load);
  groupFilter.addEventListener("change", renderAll);
  document.addEventListener("themechange", () => renderFirmwareChart());

  load();
})();
