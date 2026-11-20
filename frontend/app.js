const $ = (id) => document.getElementById(id);

const form = $("inspect-form");
const urlInput = $("url");
const scopeInput = $("scope");
const goalInput = $("goal");
const button = $("inspect-btn");
const statusEl = $("status");
const emptyEl = $("empty");
const reportEl = $("report");
const tbody = document.querySelector("#results tbody");
const filterInput = $("filter");
const selectAll = $("select-all");
const selectionCard = $("selection-card");

const state = { data: null, selected: new Set() };
const modelCard = $("model-card");
const askButton = $("ask-btn");

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function elementCell(item) {
  const td = el("td");
  td.append(el("div", "tag", `<${item.tag}>`));
  const text = [item.text, item.label && `(label: ${item.label})`]
    .filter(Boolean)
    .join(" ");
  if (text) td.append(el("div", "label-text", text));
  return td;
}

function attributesCell(item) {
  const lines = Object.entries(item.attributes).map(([k, v]) => `${k}="${v}"`);
  return el("td", "attrs", lines.join("\n"));
}

function locatorsCell(locators) {
  const td = el("td");
  if (!locators.length) {
    td.append(el("span", "none", "none found"));
    return td;
  }
  for (const loc of locators) {
    const row = el("div", "loc");
    const badge = el(
      "span",
      "badge " + (loc.unique ? "ok" : "warn"),
      loc.unique ? "unique" : `${loc.match_count} matches`
    );
    row.append(badge, el("code", "", loc.code));
    td.append(row);
  }
  return td;
}

function stateCell(item) {
  const lines = [
    item.visible ? "visible" : "hidden",
    item.enabled ? "enabled" : "disabled",
  ];
  if (item.form) lines.push(`form: ${item.form}`);
  return el("td", "attrs", lines.join("\n"));
}

function matchesFilter(item, query) {
  if (!query) return true;
  const haystack = [
    item.tag,
    item.text,
    item.label,
    ...Object.entries(item.attributes).flat(),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query);
}

function renderRows() {
  const query = filterInput.value.trim().toLowerCase();
  const rows = state.data.elements.filter((item) => matchesFilter(item, query));

  tbody.replaceChildren();
  for (const item of rows) {
    const tr = el("tr");
    tr.classList.toggle("selected", state.selected.has(item.id));

    const checkCell = el("td", "check");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.selected.has(item.id);
    box.setAttribute("aria-label", `Select element ${item.id}`);
    box.addEventListener("change", () => {
      if (box.checked) state.selected.add(item.id);
      else state.selected.delete(item.id);
      tr.classList.toggle("selected", box.checked);
      updateSelection(rows);
    });
    checkCell.append(box);

    tr.append(
      checkCell,
      el("td", "", String(item.id)),
      elementCell(item),
      attributesCell(item),
      locatorsCell(item.locators),
      stateCell(item)
    );
    tbody.append(tr);
  }

  $("count").textContent =
    `${rows.length} of ${state.data.elements.length} shown`;
  updateSelection(rows);
}

function updateSelection(visibleRows) {
  const count = state.selected.size;
  $("selection-summary").textContent = count
    ? `${count} element${count === 1 ? "" : "s"} selected`
    : "No elements selected: the model will use the first 40 elements.";

  const visibleSelected = visibleRows.filter((r) => state.selected.has(r.id)).length;
  selectAll.checked = visibleRows.length > 0 && visibleSelected === visibleRows.length;
  selectAll.indeterminate =
    visibleSelected > 0 && visibleSelected < visibleRows.length;
}

function renderReport(data) {
  state.data = data;
  state.selected.clear();

  const unique = data.elements.filter((e) => e.locators.some((l) => l.unique)).length;
  $("page-title").textContent = data.title || "(untitled page)";
  const link = $("page-url");
  link.textContent = data.url;
  link.href = data.url;
  $("page-meta").textContent =
    `HTTP ${data.http_status ?? "?"} · ${data.scan_seconds}s · ${data.browser}` +
    (data.scope ? ` · scope: ${data.scope}` : "");

  $("stat-total").textContent = data.element_count;
  $("stat-unique").textContent = unique;
  $("stat-weak").textContent = data.elements.length - unique;

  const warnings = $("warnings");
  warnings.replaceChildren(...data.warnings.map((w) => el("li", "", w)));
  warnings.hidden = data.warnings.length === 0;

  $("raw").textContent = JSON.stringify(data, null, 2);
  filterInput.value = "";
  emptyEl.hidden = true;
  reportEl.hidden = false;
  selectionCard.hidden = false;
  modelCard.hidden = true;
  renderRows();
}

function showModelResult(answer, usage, isError) {
  modelCard.className = "card model" + (isError ? " error" : "");
  $("model-answer").textContent = answer;
  $("model-usage").textContent = usage
    ? `Model: ${usage.model}${usage.model_digest ? ` (${usage.model_digest})` : ""}` +
      ` · Hardware: ${usage.hardware}` +
      ` · Prompt tokens: ${usage.prompt_tokens}` +
      ` · Output tokens: ${usage.output_tokens}` +
      ` · Response time: ${usage.response_time_s}s`
    : "";
  modelCard.hidden = false;
}

askButton.addEventListener("click", async () => {
  askButton.disabled = true;
  showModelResult("Asking the model...", null, false);
  try {
    const response = await fetch("/api/summarize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inspection_id: state.data.inspection_id,
        goal: goalInput.value.trim() || null,
        element_ids: [...state.selected],
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Model call failed");
    showModelResult(data.answer, data.usage, false);
  } catch (err) {
    showModelResult("Error: " + err.message, null, true);
  } finally {
    askButton.disabled = false;
  }
});

filterInput.addEventListener("input", renderRows);

selectAll.addEventListener("change", () => {
  const query = filterInput.value.trim().toLowerCase();
  for (const item of state.data.elements.filter((i) => matchesFilter(i, query))) {
    if (selectAll.checked) state.selected.add(item.id);
    else state.selected.delete(item.id);
  }
  renderRows();
});

$("clear-selection").addEventListener("click", () => {
  state.selected.clear();
  renderRows();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  button.disabled = true;
  statusEl.className = "";
  statusEl.textContent = "Inspecting...";

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
    renderReport(data);
    statusEl.textContent = "";
  } catch (err) {
    statusEl.className = "error";
    statusEl.textContent = "Error: " + err.message;
  } finally {
    button.disabled = false;
  }
});
