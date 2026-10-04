import { api } from "../core/api.js";
import { aiBadge, fillResumeSelect } from "../core/common.js";
import { $, $$, clearFieldErrors, confirmDialog, copyText, emptyState, esc, fmtDate, icon, load, loadingState, params,
  showFieldErrors, toast, toastError, withBusy } from "../core/ui.js";

let tone = "formal", current = null;
const out = $("#cl-out");

$$("#tone button").forEach((b) => b.addEventListener("click", () => {
  tone = b.dataset.tone;
  $$("#tone button").forEach((x) => x.setAttribute("aria-pressed", x === b));
}));

async function init() {
  await fillResumeSelect($("#cl-version"), { allVersions: true });
  const jds = await api.get("/api/job-descriptions?per_page=50").catch(() => ({ items: [] }));
  $("#cl-jd-id").insertAdjacentHTML("beforeend", jds.items.map((j) => `<option value="${j.id}" data-title="${esc(j.title)}" data-company="${esc(j.company || "")}">${esc(j.title)}${j.company ? ` - ${esc(j.company)}` : ""}</option>`).join(""));
  $("#cl-jd-id").addEventListener("change", (e) => {
    const o = e.target.selectedOptions[0];
    if (o?.dataset.title && !$("#cl-position").value) $("#cl-position").value = o.dataset.title;
    if (o?.dataset.company && !$("#cl-company").value) $("#cl-company").value = o.dataset.company;
  });
  if (params().get("jd")) { $("#cl-jd-id").value = params().get("jd"); $("#cl-jd-id").dispatchEvent(new Event("change")); }
  list();
}

$("#cl-form").addEventListener("submit", (e) => { e.preventDefault(); generate(); });

async function generate() {
  const form = $("#cl-form");
  clearFieldErrors(form);
  const company = $("#cl-company").value.trim(), position = $("#cl-position").value.trim();
  const errs = [!company && { field: "company", message: "Required" }, !position && { field: "position", message: "Required" }].filter(Boolean);
  if (errs.length) return showFieldErrors(form, { details: errs });
  await withBusy($("#cl-btn"), async () => {
    out.innerHTML = loadingState("Writing from your resume facts...");
    try {
      current = await api.post("/api/cover-letter", { company, position, tone, resume_version_id: +$("#cl-version").value || null,
        job_description_id: +$("#cl-jd-id").value || null, job_description: $("#cl-jd").value.trim() || null });
      show(current);
      list();
    } catch (err) { out.innerHTML = ""; if (!showFieldErrors(form, err)) toastError(err); }
  }, "Generating...");
}

function show(letter) {
  current = letter;
  out.innerHTML = `<div class="flex between mb-2 flex-wrap"><h3>${esc(letter.position)} · ${esc(letter.company)}</h3>${aiBadge(letter.ai_used)}</div>
    ${letter.ai_note ? `<div class="callout warn small mb-2">${esc(letter.ai_note)}</div>` : ""}
    <div class="callout small mb-2">${icon("shield")} Review before sending: replace any [bracketed placeholders] and check every claim is true.</div>
    <div class="letter" id="letter" contenteditable="false">${esc(letter.content)}</div>
    <div class="flex flex-wrap mt-2">
      <button class="btn btn-ghost btn-sm" id="copy">${icon("copy")} Copy</button>
      <button class="btn btn-ghost btn-sm" id="edit">${icon("edit")} Edit</button>
      <button class="btn btn-primary btn-sm" id="save" hidden>${icon("check")} Save</button>
      <button class="btn btn-ghost btn-sm" id="regen">${icon("refresh")} Regenerate</button>
    </div>`;
  const el = $("#letter");
  $("#copy").onclick = () => copyText(el.innerText);
  $("#edit").onclick = () => { el.contentEditable = "true"; el.focus(); $("#save").hidden = false; $("#edit").hidden = true; };
  $("#save").onclick = async () => {
    try {
      current = await api.put(`/api/cover-letter/${letter.id}`, { content: el.innerText.trim() });
      el.contentEditable = "false"; $("#save").hidden = true; $("#edit").hidden = false;
      toast("Saved", "success"); list();
    } catch (err) { toastError(err); }
  };
  $("#regen").onclick = () => {
    $("#cl-company").value = letter.company; $("#cl-position").value = letter.position;
    $$("#tone button").forEach((b) => { if (b.dataset.tone === letter.tone) b.click(); });
    generate();
  };
}

function list() {
  const el = $("#cl-list");
  load(el, () => api.get("/api/cover-letter?per_page=30"), (d) => {
    el.innerHTML = d.items.length ? `<div class="list">${d.items.map((c) => `<div class="list-item" data-id="${c.id}">
      <div class="grow"><strong class="break">${esc(c.position)}</strong><div class="tiny muted">${esc(c.company)} · ${esc(c.tone)} · ${fmtDate(c.updated_at)}</div></div>
      <button class="btn btn-ghost btn-sm" data-open>${icon("eye")}</button><button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div>`).join("")}</div>`
      : emptyState("No letters yet", "Generated letters are saved here.", "", "mail");
    el.querySelectorAll("[data-open]").forEach((b) => (b.onclick = () => show(d.items.find((c) => c.id === +b.closest("[data-id]").dataset.id))));
    el.querySelectorAll("[data-del]").forEach((b) => (b.onclick = async () => {
      if (!(await confirmDialog("Delete cover letter?", "This can't be undone.", { danger: true, confirmLabel: "Delete" }))) return;
      try { await api.del(`/api/cover-letter/${b.closest("[data-id]").dataset.id}`); list(); } catch (err) { toastError(err); }
    }));
  });
}

init().catch(toastError);
