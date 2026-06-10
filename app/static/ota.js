// ota.js — OTA management: upload firmware, list + deploy, and a 10s deployment-status poll.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
"use strict";

(function () {
  if (!requireToken()) return;

  const rowsEl = document.getElementById("firmware-rows");
  const uploadForm = document.getElementById("firmware-upload-form");
  const statusRowsEl = document.getElementById("ota-status-rows");
  const trackInput = document.getElementById("ota-status-device");
  let firmware = [];
  let trackedDevice = null;
  let statusTimer = null;

  const deployModalEl = document.getElementById("deploy-modal");
  const deployModal = createModal(deployModalEl);
  const kindSelect = document.getElementById("deploy-target-kind");
  const deviceWrap = document.getElementById("deploy-device-wrap");
  const groupWrap = document.getElementById("deploy-group-wrap");
  const deviceSelect = document.getElementById("deploy-device");
  const groupSelect = document.getElementById("deploy-group");
  let pendingFirmware = null;

  function fmtSize(bytes) {
    if (!bytes) return "—";
    const units = ["B", "KB", "MB", "GB"];
    let n = bytes;
    let i = 0;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i += 1;
    }
    return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  }

  // --- firmware list ---
  function skeletonRows(n = 4) {
    rowsEl.replaceChildren();
    for (let i = 0; i < n; i += 1) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td colspan="4"><span class="skeleton skeleton-line"></span></td>`;
      rowsEl.appendChild(tr);
    }
  }

  function renderFirmware() {
    if (firmware.length === 0) {
      rowsEl.replaceChildren();
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.innerHTML =
        '<div class="empty"><div class="icon-tile" aria-hidden="true">📦</div>' +
        "<p>No firmware uploaded yet. Add your first image with the upload card.</p></div>";
      tr.appendChild(td);
      rowsEl.appendChild(tr);
      return;
    }
    rowsEl.replaceChildren();
    for (const fw of firmware) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td></td><td class="mono"></td><td></td>` +
        `<td class="text-end"><button class="btn btn-ghost btn-sm" type="button">Deploy</button></td>`;
      const cells = tr.querySelectorAll("td");
      cells[0].textContent = fw.name;
      cells[1].textContent = fw.version;
      cells[2].textContent = fmtSize(fw.size_bytes);
      tr.querySelector("button").addEventListener("click", () => openDeploy(fw));
      rowsEl.appendChild(tr);
    }
  }

  async function loadFirmware() {
    skeletonRows();
    try {
      const body = await apiFetch("/api/v1/ota/firmware");
      firmware = body.data || [];
      renderFirmware();
    } catch (err) {
      if (err.message === "unauthorized") return;
      rowsEl.innerHTML = `<tr><td colspan="4" class="cell-center">Failed to load firmware.</td></tr>`;
      toast(`Could not load firmware: ${err.message}`, "danger");
    }
  }

  async function uploadFirmware(e) {
    e.preventDefault();
    const name = document.getElementById("fw-name").value.trim();
    const version = document.getElementById("fw-version").value.trim();
    const fileInput = document.getElementById("fw-file");
    if (!name || !version || !fileInput.files.length) {
      toast("Name, version and a file are required.", "danger");
      return;
    }
    const fd = new FormData();
    fd.append("name", name);
    fd.append("version", version);
    fd.append("file", fileInput.files[0]);
    const btn = document.getElementById("fw-upload-btn");
    btn.disabled = true;
    try {
      await apiFetch("/api/v1/ota/firmware", { method: "POST", body: fd });
      toast("Firmware uploaded.", "success");
      uploadForm.reset();
      document.getElementById("fw-file-name").textContent = "Choose a firmware file…";
      loadFirmware();
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Upload failed: ${err.message}`, "danger");
    } finally {
      btn.disabled = false;
    }
  }

  // --- deploy ---
  function fillOptions(select, values, placeholder) {
    select.replaceChildren();
    if (values.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = placeholder;
      opt.disabled = true;
      select.appendChild(opt);
      return;
    }
    for (const v of values) {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    }
  }

  async function openDeploy(fw) {
    pendingFirmware = fw;
    document.getElementById("deploy-fw-label").textContent = `${fw.name} ${fw.version}`;
    kindSelect.value = "device";
    syncTargetKind();
    try {
      const [devs, groups] = await Promise.all([
        apiFetch("/api/v1/devices"),
        apiFetch("/api/v1/groups"),
      ]);
      fillOptions(
        deviceSelect,
        (devs.data || []).map((d) => d.id),
        "No devices",
      );
      fillOptions(
        groupSelect,
        (groups.data || []).map((g) => g.id),
        "No groups",
      );
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Could not load deploy targets: ${err.message}`, "danger");
    }
    deployModal.show();
  }

  function syncTargetKind() {
    const byDevice = kindSelect.value === "device";
    deviceWrap.classList.toggle("hidden", !byDevice);
    groupWrap.classList.toggle("hidden", byDevice);
  }

  async function confirmDeploy() {
    if (!pendingFirmware) return;
    const payload = { firmware_id: pendingFirmware.id };
    if (kindSelect.value === "device") {
      if (!deviceSelect.value) {
        toast("Select a device.", "danger");
        return;
      }
      payload.device_id = deviceSelect.value;
    } else {
      if (!groupSelect.value) {
        toast("Select a group.", "danger");
        return;
      }
      payload.group_id = groupSelect.value;
    }
    try {
      await apiFetch("/api/v1/ota/deploy", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      toast("Deployment created.", "success");
      deployModal.hide();
      if (payload.device_id) {
        trackInput.value = payload.device_id;
        startTracking();
      }
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Deploy failed: ${err.message}`, "danger");
    }
  }

  // --- status poll (the only timer; every 10s) ---
  function renderStatus(device, s) {
    statusRowsEl.replaceChildren();
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td class="mono"></td><td></td><td></td><td class="mono"></td><td></td>`;
    const cells = tr.querySelectorAll("td");
    cells[0].textContent = device;
    cells[1].textContent = s.status || "unknown";
    cells[2].textContent = `${s.progress_pct == null ? 0 : s.progress_pct}%`;
    cells[3].textContent = s.version || "—";
    cells[4].textContent = s.updated_at ? new Date(s.updated_at).toLocaleString() : "—";
    statusRowsEl.appendChild(tr);
  }

  async function pollStatus() {
    if (!trackedDevice) return;
    try {
      const body = await apiFetch(`/api/v1/ota/status/${encodeURIComponent(trackedDevice)}`);
      renderStatus(trackedDevice, body.data || {});
    } catch (err) {
      if (err.message === "unauthorized") return;
      statusRowsEl.innerHTML = `<tr><td colspan="5" class="cell-center">Status unavailable: ${err.message}</td></tr>`;
    }
  }

  function startTracking() {
    const device = trackInput.value.trim();
    if (!device) {
      toast("Enter a device id to track.", "danger");
      return;
    }
    trackedDevice = device;
    pollStatus();
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = setInterval(pollStatus, 10000);
  }

  uploadForm.addEventListener("submit", uploadFirmware);
  document.getElementById("fw-file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    document.getElementById("fw-file-name").textContent = f ? f.name : "Choose a firmware file…";
  });
  document.getElementById("fw-refresh-btn").addEventListener("click", loadFirmware);
  kindSelect.addEventListener("change", syncTargetKind);
  document.getElementById("deploy-confirm-btn").addEventListener("click", confirmDeploy);
  document.getElementById("ota-status-track-btn").addEventListener("click", startTracking);

  loadFirmware();
})();
