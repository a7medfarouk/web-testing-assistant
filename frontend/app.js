// Minimal test UI: send a URL to the backend, show the elements it returns.
// Page content is DATA: we always use textContent (never innerHTML) so
// text taken from the inspected page can never run as code in this UI.

const form = document.getElementById("inspect-form");
const urlInput = document.getElementById("url");
const scopeInput = document.getElementById("scope");
const button = document.getElementById("inspect-btn");
const statusEl = document.getElementById("status");
const summary = document.getElementById("summary");
const table = document.getElementById("results");
const tbody = table.querySelector("tbody");
const rawBox = document.getElementById("raw-box");
const rawEl = document.getElementById("raw");

function cell(text, className) {
  const td = document.createElement("td");
  td.textContent = text ?? "";
  if (className) td.className = className;
  return td;
}

function locatorCell(locators) {
  const td = document.createElement("td");
  if (!locators.length) {
    td.textContent = "none found";
    td.className = "none";
    return td;
  }
  for (const loc of locators) {
    const row = document.createElement("div");
    const badge = document.createElement("span");
    badge.className = "badge " + (loc.unique ? "ok" : "warn");
    badge.textContent = loc.unique ? "unique" : loc.match_count + " matches";
    const code = document.createElement("code");
    code.textContent = loc.code;
    row.append(badge, code);
    td.append(row);
  }
  return td;
}

function render(data) {
  const noUnique = data.elements.filter(
    (el) => !el.locators.some((l) => l.unique)
  ).length;

  summary.textContent =
    `Page: ${data.title}\n` +
    `URL: ${data.url}\n` +
    `Scanned: ${data.scanned_at}` +
    (data.scope ? `  |  Scope: ${data.scope}` : "") +
    `\nElements found: ${data.elements.length}` +
    `  |  Without a unique locator: ${noUnique}`;
  summary.style.whiteSpace = "pre-line";

  tbody.replaceChildren();
  for (const el of data.elements) {
    const tr = document.createElement("tr");
    const attrs = Object.entries(el.attributes)
      .map(([k, v]) => `${k}="${v}"`)
      .join("\n");
    const state =
      (el.visible ? "visible" : "hidden") + ", " +
      (el.enabled ? "enabled" : "disabled") +
      (el.form ? `\nform: ${el.form}` : "");
    tr.append(
      cell(el.id),
      cell(el.tag),
      cell([el.text, el.label && `(label: ${el.label})`].filter(Boolean).join(" ")),
      cell(attrs, "attrs"),
      locatorCell(el.locators),
      cell(state, "attrs")
    );
    tbody.append(tr);
  }
  table.hidden = false;

  rawEl.textContent = JSON.stringify(data, null, 2);
  rawBox.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  statusEl.className = "";
  statusEl.textContent = "Inspecting... a browser window will open.";

  try {
    const response = await fetch("/api/inspect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: urlInput.value.trim(),
        scope: scopeInput.value.trim() || null,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Inspection failed");
    render(data);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.className = "error";
    statusEl.textContent = "Error: " + err.message;
  } finally {
    button.disabled = false;
  }
});