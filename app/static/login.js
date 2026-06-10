// login.js — sign in, store the JWT, redirect to the fleet. @company embediq.com | ritzylab.com
// SPDX-License-Identifier: Apache-2.0
"use strict";

(function () {
  // already signed in → skip the form
  if (Auth.get()) {
    window.location.replace("/ui/overview");
    return;
  }

  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("login-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.classList.add("hidden");
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    try {
      const resp = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      if (resp.status === 401) {
        errorBox.textContent = "Invalid username or password.";
        errorBox.classList.remove("hidden");
        return;
      }
      const body = await resp.json();
      if (!resp.ok || !body.data || !body.data.token) {
        throw new Error((body.error && body.error.message) || "login failed");
      }
      Auth.set(body.data.token);
      window.location.replace("/ui/overview");
    } catch (err) {
      errorBox.textContent = "Could not sign in. Please try again.";
      errorBox.classList.remove("hidden");
    }
  });
})();
