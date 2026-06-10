// app.js — shared admin-UI helpers: theme, token handling, fetch wrapper, toasts, modal, drawer.
// @company embediq.com | ritzylab.com · SPDX-License-Identifier: Apache-2.0
// Vanilla JS, no framework, no build step (R-1). No secrets are logged (R-8).
"use strict";

const TOKEN_KEY = "embediq-token";
const THEME_KEY = "embediq-theme";

// --- token (sessionStorage; the JWT is the only credential the UI holds) ---
const Auth = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (t) => sessionStorage.setItem(TOKEN_KEY, t),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

// Redirect to login when there is no token. Call at the top of protected pages.
function requireToken() {
  if (!Auth.get()) {
    window.location.replace("/login");
    return false;
  }
  return true;
}

function logout() {
  Auth.clear();
  window.location.replace("/login");
}

// Authenticated fetch: attaches the Bearer token; a 401 clears the token and
// bounces to login. Returns the parsed envelope { data, error } on success.
async function apiFetch(path, options = {}) {
  const opts = Object.assign({ headers: {} }, options);
  opts.headers = Object.assign({ Authorization: `Bearer ${Auth.get()}` }, opts.headers);
  const resp = await fetch(path, opts);
  if (resp.status === 401) {
    Auth.clear();
    window.location.replace("/login");
    throw new Error("unauthorized");
  }
  const body = await resp.json().catch(() => ({ data: null, error: { message: resp.statusText } }));
  if (!resp.ok) {
    throw new Error((body.error && body.error.message) || `request failed (${resp.status})`);
  }
  return body;
}

// --- toasts (vanilla; tokenised .toast component) ---
function toast(message, variant = "info") {
  const tray = document.getElementById("toast-tray");
  if (!tray) return;
  const el = document.createElement("div");
  const cls = { success: "is-success", danger: "is-danger", warn: "is-warn" }[variant] || "";
  el.className = `toast ${cls}`.trim();
  el.setAttribute("role", "alert");
  el.textContent = message; // textContent: no HTML injection
  tray.appendChild(el);
  requestAnimationFrame(() => el.classList.add("show"));
  setTimeout(() => {
    el.classList.remove("show");
    setTimeout(() => el.remove(), 200);
  }, 3500);
}

// --- modal helper (framework-free; a small show/hide surface) ---
// Wires: any [data-close] element, a backdrop click, and Escape → hide.
function createModal(el) {
  if (!el) return { show() {}, hide() {} };
  function hide() {
    el.classList.remove("show");
  }
  function show() {
    el.classList.add("show");
  }
  el.addEventListener("click", (e) => {
    if (e.target === el || e.target.closest("[data-close]")) hide();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && el.classList.contains("show")) hide();
  });
  return { show, hide };
}

// --- theme toggle (persisted; the pre-paint script in base.html sets the initial value) ---
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem(THEME_KEY, next);
    document.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
  });
}

function initLogout() {
  const btn = document.getElementById("logout-btn");
  if (btn) btn.addEventListener("click", logout);
}

// --- mobile drawer ---
function initDrawer() {
  const toggle = document.getElementById("drawer-toggle");
  const scrim = document.getElementById("drawer-scrim");
  if (!toggle) return;
  const close = () => document.body.classList.remove("drawer-open");
  toggle.addEventListener("click", () => document.body.classList.toggle("drawer-open"));
  if (scrim) scrim.addEventListener("click", close);
  for (const link of document.querySelectorAll(".nav-item")) link.addEventListener("click", close);
}

// Resolve the current design-system token values so charts can match the theme.
function chartTokens() {
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();
  return {
    blue: v("--blue") || "#36bbde",
    lime: v("--lime2") || "#b5c420",
    muted: v("--muted") || "#5d7a85",
    line: v("--line") || "#d4eaf2",
    font: "Nunito",
  };
}

// small helper: epoch-seconds → human relative/absolute string
function formatLastSeen(epochSeconds) {
  if (!epochSeconds) return "never";
  return new Date(epochSeconds * 1000).toLocaleString();
}

document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initLogout();
  initDrawer();
});
