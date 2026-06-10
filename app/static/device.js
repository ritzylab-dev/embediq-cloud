// device.js — device detail: status, telemetry, shadow editor + drift, OTA status, commands.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
"use strict";

(function () {
  if (!requireToken()) return;

  const root = document.getElementById("device-detail");
  const deviceId = root.dataset.deviceId;
  const enc = encodeURIComponent(deviceId);

  // Grafana / Loki are deployment-local; default to the compose Grafana on :3000.
  // Override by setting window.GRAFANA_URL before this script if hosted elsewhere.
  const grafanaUrl = (window.GRAFANA_URL || "http://localhost:3000").replace(/\/$/, "");
  document.getElementById("grafana-link").href = `${grafanaUrl}/?var-device_id=${enc}`;
  document.getElementById("loki-link").href =
    `${grafanaUrl}/explore?left=` +
    encodeURIComponent(
      JSON.stringify({ datasource: "loki", queries: [{ expr: `{device_id="${deviceId}"}` }] }),
    );

  const desiredEl = document.getElementById("desired-json");
  const reportedEl = document.getElementById("reported-json");
  const deltaEl = document.getElementById("delta-json");
  const editBtn = document.getElementById("edit-desired-btn");
  const actions = document.getElementById("desired-actions");

  function setText(id, value) {
    document.getElementById(id).textContent = value === null || value === undefined ? "—" : value;
  }

  function renderStatus(d) {
    const s = d.state || {};
    const pillCls = s.online ? "pill-online" : "pill-offline";
    const label = s.online ? "online" : "offline";
    document.getElementById("status-online").innerHTML = `<span class="pill ${pillCls}">${label}</span>`;
    const header = document.getElementById("device-header-status");
    header.className = `pill ${pillCls}`;
    header.textContent = label;
    setText("status-ip", s.ip_address);
    setText("status-fw", s.firmware_version);
    setText("status-group", d.group_id);
    document.getElementById("status-lastseen").textContent = formatLastSeen(s.last_seen);
  }

  function renderShadow(shadow) {
    desiredEl.value = JSON.stringify(shadow.desired || {}, null, 2);
    reportedEl.value = JSON.stringify(shadow.reported || {}, null, 2);
    const delta = shadow.delta || {};
    deltaEl.value = JSON.stringify(delta, null, 2);
    const drift = document.getElementById("shadow-drift");
    const n = Object.keys(delta).length;
    if (n === 0) {
      drift.className = "pill pill-online";
      drift.textContent = "in sync";
    } else {
      drift.className = "pill pill-warn";
      drift.textContent = `drift: ${n} key${n === 1 ? "" : "s"}`;
    }
  }

  // Telemetry needs a metrics-history API (absent under dev.sh) → designed empty state, not a
  // broken chart. The canvas is present for when a history endpoint is wired; Grafana has full data.
  function renderTelemetry() {
    document.getElementById("chart-telemetry").classList.add("hidden");
    document.getElementById("chart-telemetry-empty").classList.remove("hidden");
  }

  function renderOtaEmpty(message) {
    const host = document.getElementById("ota-status-body");
    host.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.innerHTML = `<div class="icon-tile" aria-hidden="true">⇪</div><p>${message}</p>`;
    host.appendChild(empty);
  }

  async function loadOtaStatus() {
    try {
      const body = await apiFetch(`/api/v1/ota/status/${enc}`);
      const s = body.data || {};
      const host = document.getElementById("ota-status-body");
      const dl = document.createElement("dl");
      dl.className = "kv";
      const rows = [
        ["Status", s.status || "unknown"],
        ["Progress", `${s.progress_pct == null ? 0 : s.progress_pct}%`],
        ["Version", s.version || "—"],
        ["Updated", s.updated_at ? new Date(s.updated_at).toLocaleString() : "—"],
      ];
      for (const [k, v] of rows) {
        const dt = document.createElement("dt");
        dt.textContent = k;
        const dd = document.createElement("dd");
        dd.textContent = v;
        dl.append(dt, dd);
      }
      host.replaceChildren(dl);
    } catch (err) {
      if (err.message === "unauthorized") return;
      // Hawkbit is absent under dev.sh, or no deployment for this device — designed empty state.
      renderOtaEmpty("No active deployment. Deploy firmware from the OTA page.");
    }
  }

  async function load() {
    renderTelemetry();
    loadOtaStatus();
    try {
      const [dev, sh] = await Promise.all([
        apiFetch(`/api/v1/devices/${enc}`),
        apiFetch(`/api/v1/devices/${enc}/shadow`),
      ]);
      renderStatus(dev.data);
      renderShadow(sh.data);
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Could not load device: ${err.message}`, "danger");
    }
  }

  function enterEdit() {
    desiredEl.readOnly = false;
    desiredEl.focus();
    actions.classList.remove("hidden");
    editBtn.classList.add("hidden");
  }

  function leaveEdit() {
    desiredEl.readOnly = true;
    actions.classList.add("hidden");
    editBtn.classList.remove("hidden");
  }

  async function saveDesired() {
    let parsed;
    try {
      parsed = JSON.parse(desiredEl.value);
    } catch (e) {
      toast("Desired must be valid JSON.", "danger");
      return;
    }
    if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
      toast("Desired must be a JSON object.", "danger");
      return;
    }
    try {
      // PATCH semantics are a key-level merge; send the full edited object as the delta.
      await apiFetch(`/api/v1/devices/${enc}/shadow/desired`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(parsed),
      });
      toast("Desired state saved.", "success");
      leaveEdit();
      load();
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Save failed: ${err.message}`, "danger");
    }
  }

  editBtn.addEventListener("click", enterEdit);
  document.getElementById("cancel-desired-btn").addEventListener("click", () => {
    leaveEdit();
    load();
  });
  document.getElementById("save-desired-btn").addEventListener("click", saveDesired);

  // --- device commands (Reboot / Rotate Cert / Check OTA) → confirm modal → POST cmd ---
  const cmdLabels = { reboot: "Reboot", rotate_cert: "Rotate Cert", ota_check: "Check OTA" };
  const cmdModalEl = document.getElementById("cmd-modal");
  const cmdModal = createModal(cmdModalEl);
  let pendingCmd = null;

  function askCmd(cmd) {
    pendingCmd = cmd;
    document.getElementById("cmd-modal-label").textContent = cmdLabels[cmd] || cmd;
    cmdModal.show();
  }

  async function sendCmd() {
    if (!pendingCmd) return;
    try {
      await apiFetch(`/api/v1/devices/${enc}/cmd`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cmd: pendingCmd }),
      });
      toast(`${cmdLabels[pendingCmd] || pendingCmd} sent.`, "success");
    } catch (err) {
      cmdModal.hide();
      if (err.message === "unauthorized") return;
      toast(`Command failed: ${err.message}`, "danger");
      return;
    }
    cmdModal.hide();
    pendingCmd = null;
  }

  for (const btn of document.querySelectorAll("#device-commands button[data-cmd]")) {
    btn.addEventListener("click", () => askCmd(btn.dataset.cmd));
  }
  document.getElementById("cmd-confirm-btn").addEventListener("click", sendCmd);

  load();
})();
