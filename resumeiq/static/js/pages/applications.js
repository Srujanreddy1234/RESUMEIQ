import { api } from "../core/api.js";
import { $, $$, STAGE_LABELS, confirmDialog, debounce, emptyState, esc, fmtDate, icon, load, modal, safeUrl, showFieldErrors,
  toast, toastError } from "../core/ui.js";

const board = $("#board");
let columns = [];

function cardHtml(a) {
  return `<div class="kcard" draggable="true" data-id="${a.id}" tabindex="0" aria-label="${esc(a.position)} at ${esc(a.company)}">
    <div class="kcard-title">${esc(a.position)}</div>
    <div class="small muted break">${esc(a.company)}${a.location ? ` · ${esc(a.location)}` : ""}</div>
    ${a.interview_date ? `<span class="badge info">${icon("calendar", "sm")} ${fmtDate(a.interview_date, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</span>` : ""}
    ${a.date_applied ? `<span class="tiny faint">Applied ${fmtDate(a.date_applied)}</span>` : ""}
    <div class="flex between" style="gap:6px">
      <select class="select" data-move aria-label="Move to stage" style="min-height:30px;padding:3px 6px;font-size:.78rem">
        ${Object.entries(STAGE_LABELS).map(([k, l]) => `<option value="${k}" ${k === a.stage ? "selected" : ""}>${l}</option>`).join("")}</select>
      <button class="btn btn-ghost btn-sm" data-edit aria-label="Edit">${icon("edit")}</button>
    </div></div>`;
}

function render() {
  const total = columns.reduce((n, c) => n + c.items.length, 0);
  board.innerHTML = total || $("#board-search").value ? `<div class="kanban">${columns.map((c) => `
    <section class="kcol" data-stage="${c.stage}" aria-label="${esc(c.label)}">
      <div class="kcol-head"><span>${esc(c.label)}</span><span class="badge">${c.items.length}</span></div>
      ${c.items.map(cardHtml).join("") || `<p class="tiny faint center" style="padding:10px">Drop here</p>`}
    </section>`).join("")}</div>`
    : `<div class="card">${emptyState("No applications yet", "Add one manually, or use 'Add to applications' on any job.", `<button class="btn btn-primary" id="empty-add">${icon("plus")} Add application</button>`, "kanban")}</div>`;
  $("#empty-add")?.addEventListener("click", () => edit());
}

function refresh() {
  const q = $("#board-search").value.trim();
  return load(board, () => api.get(`/api/applications${q ? `?q=${encodeURIComponent(q)}` : ""}`), (d) => { columns = d.columns; render(); });
}

const find = (id) => columns.flatMap((c) => c.items).find((a) => a.id === id);

async function move(id, stage, position = 0) {
  try { await api.post(`/api/applications/${id}/move`, { stage, position }); toast(`Moved to ${STAGE_LABELS[stage]}`, "success", 2000); }
  catch (err) { toastError(err); }
  refresh();
}

// Drag & drop
let dragId = null;
board.addEventListener("dragstart", (e) => { const c = e.target.closest(".kcard"); if (!c) return; dragId = +c.dataset.id; c.classList.add("dragging"); e.dataTransfer.effectAllowed = "move"; });
board.addEventListener("dragend", (e) => { e.target.closest(".kcard")?.classList.remove("dragging"); $$(".kcol").forEach((c) => c.classList.remove("drop-target")); });
board.addEventListener("dragover", (e) => { const col = e.target.closest(".kcol"); if (!col) return; e.preventDefault(); $$(".kcol").forEach((c) => c.classList.toggle("drop-target", c === col)); });
board.addEventListener("drop", (e) => {
  const col = e.target.closest(".kcol");
  if (!col || dragId === null) return;
  e.preventDefault();
  const cards = $$(".kcard", col).filter((c) => +c.dataset.id !== dragId);
  const idx = cards.findIndex((c) => e.clientY < c.getBoundingClientRect().top + c.offsetHeight / 2);
  move(dragId, col.dataset.stage, idx === -1 ? cards.length : idx);
  dragId = null;
});
board.addEventListener("change", (e) => { if (e.target.matches("[data-move]")) move(+e.target.closest(".kcard").dataset.id, e.target.value); });
board.addEventListener("click", (e) => { const b = e.target.closest("[data-edit]"); if (b) edit(find(+b.closest(".kcard").dataset.id)); });
board.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.matches(".kcard")) edit(find(+e.target.dataset.id)); });

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

function edit(a = null) {
  const v = (k) => esc(a?.[k] ?? "");
  const body = `<form id="app-form" class="form-grid" novalidate>
    <div class="field"><label>Company *</label><input class="input" name="company" required maxlength="200" value="${v("company")}"><span class="field-error"></span></div>
    <div class="field"><label>Position *</label><input class="input" name="position" required maxlength="200" value="${v("position")}"><span class="field-error"></span></div>
    <div class="field"><label>Stage</label><select class="select" name="stage">${Object.entries(STAGE_LABELS).map(([k, l]) => `<option value="${k}" ${k === (a?.stage || "wishlist") ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    <div class="field"><label>Location</label><input class="input" name="location" maxlength="160" value="${v("location")}"></div>
    <div class="field"><label>Salary</label><input class="input" name="salary" maxlength="80" value="${v("salary")}"></div>
    <div class="field"><label>Date applied</label><input class="input" type="date" name="date_applied" value="${v("date_applied")}"></div>
    <div class="field"><label>Interview date</label><input class="input" type="datetime-local" name="interview_date" value="${toLocalInput(a?.interview_date)}"></div>
    <div class="field"><label>Contact person</label><input class="input" name="contact_person" maxlength="160" value="${v("contact_person")}"></div>
    <div class="field"><label>Contact email</label><input class="input" type="email" name="contact_email" value="${v("contact_email")}"><span class="field-error"></span></div>
    <div class="field full"><label>Job URL</label><input class="input" type="url" name="job_url" value="${v("job_url")}" placeholder="https://..."><span class="field-error"></span></div>
    <div class="field full"><label>Notes</label><textarea class="textarea" name="notes" rows="3" maxlength="5000">${v("notes")}</textarea></div>
  </form>${a?.job_url ? `<p class="mt-2 small"><a href="${esc(safeUrl(a.job_url))}" target="_blank" rel="noopener noreferrer">${icon("external", "sm")} Open job posting</a></p>` : ""}`;
  const actions = [{ label: "Cancel" }];
  if (a) actions.push({ label: "Delete", class: "btn-danger", handler: async () => {
    if (!(await confirmDialog("Delete application?", `${a.position} at ${a.company} will be removed.`, { danger: true, confirmLabel: "Delete" }))) return false;
    await api.del(`/api/applications/${a.id}`); refresh();
  } });
  actions.push({ label: a ? "Save" : "Add application", class: "btn-primary", handler: async (m) => {
    const form = $("#app-form", m);
    const data = Object.fromEntries(new FormData(form).entries());
    Object.keys(data).forEach((k) => { data[k] = data[k].trim() || null; });
    if (!data.company || !data.position) { showFieldErrors(form, { details: [!data.company && { field: "company", message: "Required" }, !data.position && { field: "position", message: "Required" }].filter(Boolean) }); return false; }
    if (data.interview_date) data.interview_date = new Date(data.interview_date).toISOString();
    try {
      if (a) await api.patch(`/api/applications/${a.id}`, data); else await api.post("/api/applications", data);
      toast(a ? "Application updated" : "Application added", "success");
      refresh();
    } catch (err) { if (!showFieldErrors(form, err)) toastError(err); return false; }
  } });
  modal({ title: a ? "Edit application" : "Add application", body, wide: true, actions });
}

$("#add-btn").onclick = () => edit();
$("#board-search").addEventListener("input", debounce(refresh, 300));
refresh();
