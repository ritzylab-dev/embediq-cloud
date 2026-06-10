// fleet.js — fleet: health strip, device list, group filter, refresh, row → device detail.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
"use strict";

(function () {
  if (!requireToken()) return;

  const rowsEl = document.getElementById("device-rows");
  const groupFilter = document.getElementById("group-filter");
  const el = (id) => document.getElementById(id);
  let devices = [];

  function statusPill(online) {
    const cls = online ? "pill-online" : "pill-offline";
    return `<span class="pill ${cls}">${online ? "online" : "offline"}</span>`;
  }

  function visible() {
    const g = groupFilter.value;
    return g ? devices.filter((d) => d.group_id === g) : devices;
  }

  // --- fleet-health KPI strip (computed from the filtered view) ---
  function renderKpis(shown) {
    const total = shown.length;
    const online = shown.filter((d) => d.online).length;
    const attention = shown.filter((d) => !d.online).length;
    el("fleet-kpi-total").textContent = total;
    el("fleet-kpi-online").textContent = online;
    const pct = el("fleet-kpi-online-pct");
    if (total > 0) {
      pct.textContent = `${Math.round((online / total) * 100)}% of fleet`;
      pct.classList.remove("hidden");
    } else {
      pct.classList.add("hidden");
    }
    el("fleet-kpi-attention").textContent = attention;
    const note = el("fleet-kpi-attention-note");
    note.classList.toggle("hidden", attention === 0);
    if (attention > 0) note.textContent = "offline";
  }

  function skeletonRows(n = 5) {
    rowsEl.replaceChildren();
    for (let i = 0; i < n; i += 1) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="5"><span class="skeleton skeleton-line"></span></td>`;
      rowsEl.appendChild(tr);
    }
  }

  function emptyState() {
    rowsEl.replaceChildren();
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 5;
    td.innerHTML =
      '<div class="empty"><div class="icon-tile" aria-hidden="true">📡</div>' +
      "<p>No devices yet. Register your first device with the admin API:</p>" +
      "<p><code>POST /api/v1/devices {&quot;id&quot;:&quot;sensor-001&quot;,&quot;password&quot;:&quot;…&quot;}</code></p></div>";
    tr.appendChild(td);
    rowsEl.appendChild(tr);
  }

  function render() {
    const shown = visible();
    renderKpis(shown);
    if (shown.length === 0) {
      emptyState();
      return;
    }
    rowsEl.replaceChildren();
    for (const d of shown) {
      const tr = document.createElement("tr");
      tr.className = "clickable";
      tr.addEventListener("click", () => {
        window.location.href = `/ui/devices/${encodeURIComponent(d.id)}`;
      });
      tr.innerHTML =
        `<td class="mono"></td><td>${statusPill(d.online)}</td>` +
        `<td></td><td></td><td class="mono"></td>`;
      const cells = tr.querySelectorAll("td");
      cells[0].textContent = d.id; // textContent: ids are untrusted, never inject as HTML
      cells[2].textContent = formatLastSeen(d.last_seen);
      cells[3].textContent = d.group_id;
      cells[4].textContent = d.firmware_version || "—";
      rowsEl.appendChild(tr);
    }
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
    skeletonRows();
    try {
      const body = await apiFetch("/api/v1/devices");
      devices = body.data || [];
      populateGroups();
      render();
    } catch (err) {
      if (err.message === "unauthorized") return; // already redirected
      rowsEl.innerHTML = `<tr><td colspan="5" class="cell-center">Failed to load devices.</td></tr>`;
      toast("Failed to load devices.", "danger");
    }
  }

  el("refresh-btn").addEventListener("click", load);
  groupFilter.addEventListener("change", render);
  load();
})();
