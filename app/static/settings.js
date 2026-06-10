// settings.js — settings: CA cert (read-only + copy) and a 30s system-health refresh.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
"use strict";

(function () {
  if (!requireToken()) return;

  const caEl = document.getElementById("ca-cert");
  const caExpiry = document.getElementById("ca-expiry");

  async function loadCerts() {
    try {
      const body = await apiFetch("/api/v1/system/certs");
      const data = body.data || {};
      caEl.value = data.ca_cert_pem || "No CA certificate found. Run install.sh to generate one.";
      caExpiry.classList.remove("pill", "pill-warn");
      if (data.expires_in_days != null) {
        if (data.warning) {
          caExpiry.className = "pill pill-warn";
          caExpiry.textContent = `Expires in ${data.expires_in_days} day(s) — rotate soon`;
        } else {
          caExpiry.className = "small muted";
          caExpiry.textContent = `Expires in ${data.expires_in_days} day(s).`;
        }
      } else {
        caExpiry.textContent = "";
      }
    } catch (err) {
      if (err.message === "unauthorized") return;
      caEl.value = "";
      toast(`Could not load CA certificate: ${err.message}`, "danger");
    }
  }

  async function copyCert() {
    if (!caEl.value) return;
    try {
      await navigator.clipboard.writeText(caEl.value);
      toast("CA certificate copied.", "success");
    } catch (e) {
      // clipboard API unavailable (e.g. non-secure context) — fall back to selection.
      caEl.removeAttribute("readonly");
      caEl.select();
      caEl.setAttribute("readonly", "");
      toast("Select and copy manually.", "primary");
    }
  }

  function fmtUptime(seconds) {
    if (seconds == null) return "—";
    const d = Math.floor(seconds / 86400);
    const h = Math.floor((seconds % 86400) / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (d > 0) return `${d}d ${h}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  }

  function setText(id, value) {
    document.getElementById(id).textContent = value == null ? "—" : value;
  }

  async function loadHealth() {
    try {
      const body = await apiFetch("/api/v1/system/health");
      const d = body.data || {};
      const statusEl = document.getElementById("health-status");
      statusEl.innerHTML =
        d.status === "ok"
          ? `<span class="pill pill-online">ok</span>`
          : `<span class="pill pill-offline">${d.status || "unknown"}</span>`;
      setText("health-version", d.version);
      setText("health-online", d.devices_online);
      setText("health-uptime", fmtUptime(d.uptime_s));
    } catch (err) {
      if (err.message === "unauthorized") return;
      toast(`Could not load system health: ${err.message}`, "danger");
    }
  }

  document.getElementById("ca-copy-btn").addEventListener("click", copyCert);

  loadCerts();
  loadHealth();
  setInterval(loadHealth, 30000);
})();
