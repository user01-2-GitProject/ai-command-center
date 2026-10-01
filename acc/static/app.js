"use strict";

const heading = document.querySelector("#connection-heading");
const reason = document.querySelector("#connection-reason");
const count = document.querySelector("#session-count");

async function loadSnapshot() {
  try {
    const response = await fetch("/api/snapshot", {
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Local dashboard request failed");
    const data = await response.json();
    if (data.status === "not_connected" && Array.isArray(data.sessions) && data.sessions.length === 0) {
      heading.textContent = "Not connected";
      reason.textContent = typeof data.reason === "string" ? data.reason : "No provider adapters are configured yet.";
      count.textContent = "No sessions are being shown.";
      return;
    }
    heading.textContent = "Dashboard unavailable";
    reason.textContent = "The local service returned an unsupported snapshot.";
    count.textContent = "No session data was rendered.";
  } catch {
    heading.textContent = "Dashboard unavailable";
    reason.textContent = "Could not read the local dashboard state.";
    count.textContent = "No session data was rendered.";
  }
}

loadSnapshot();
