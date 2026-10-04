import { api } from "../core/api.js";
import { $, $$, confirmDialog, emptyState, esc, fmtBytes, fmtDate, icon, load, modal, timeAgo, toast, toastError, withBusy } from "../core/ui.js";

const list = $("#list");
const MAX = 16 * 1024 * 1024;
const ALLOWED = ["pdf", "docx", "txt"];

function validateFile(file) {
  if (!file) return "Choose a file first.";
  const ext = file.name.split(".").pop().toLowerCase();
  if (!ALLOWED.includes(ext)) return "Unsupported file type. Use PDF, DOCX or TXT.";
  if (file.size > MAX) return "File is too large. The maximum size is 16 MB.";
  if (!file.size) return "The file is empty.";
  return null;
}

// ── Upload ──────────────────────────────────────────────
const dz = $("#dropzone"), input = $("#file");
const showFile = (f) => {
  $("#dz-title").textContent = f ? f.name : "Drop your resume here or click to browse";
  $("#dz-sub").textContent = f ? `${fmtBytes(f.size)} · ${f.name.split(".").pop().toUpperCase()}` : "Text-based files work best.";
};
input.addEventListener("change", () => showFile(input.files[0]));
["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, () => dz.classList.remove("drag")));
dz.addEventListener("drop", (e) => { e.preventDefault(); if (e.dataTransfer.files[0]) { input.files = e.dataTransfer.files; showFile(input.files[0]); } });

$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const file = input.files[0];
  const problem = validateFile(file);
  if (problem) return toast(problem, "error");
  const fd = new FormData();
  fd.append("resume", file);
  if ($("#rname").value.trim()) fd.append("name", $("#rname").value.trim());
  await withBusy($("#upload-btn"), async () => {
    try {
      const res = await api.upload("/api/resumes", fd);
      toast(`Uploaded "${res.resume.name}" - ${res.version.skills.length} skills detected.`, "success");
      e.target.reset();
      showFile(null);
      refresh();
      offerAnalysis(res.version.id);
    } catch (err) { toastError(err); }
  }, "Uploading & reading...");
});

async function offerAnalysis(versionId) {
  const go = await confirmDialog("Analyze this resume now?", "Get a transparent score, skill extraction and improvement suggestions.", { confirmLabel: "Analyze" });
  if (go) location.href = `/analyzer?version=${versionId}`;
}

// ── List ────────────────────────────────────────────────
function row(r) {
  const v = r.latest_version;
  return `<div class="list-item" data-id="${r.id}">
    <span class="list-icon">${icon("file")}</span>
    <div class="grow stack" style="gap:6px">
      <div class="flex flex-wrap" style="gap:8px"><strong class="break">${esc(r.name)}</strong>
        ${r.is_primary ? `<span class="badge teal">${icon("star", "sm")} Primary</span>` : ""}
        <span class="badge">${esc(v.file_type.toUpperCase())}</span><span class="badge">v${v.version_number}${r.version_count > 1 ? ` of ${r.version_count}` : ""}</span>
        ${v.latest_score !== null ? `<span class="badge accent">Score ${v.latest_score}</span>` : `<span class="badge warn">Not analyzed</span>`}</div>
      <div class="meta"><span>${icon("file", "sm")} ${esc(v.original_filename)}</span><span>${fmtBytes(v.file_size)}</span>
        <span>${icon("calendar", "sm")} Uploaded ${fmtDate(v.uploaded_at)}</span>
        <span>${icon("clock", "sm")} ${v.last_analyzed_at ? `Analyzed ${timeAgo(v.last_analyzed_at)}` : "Never analyzed"}</span></div>
      <div class="flex flex-wrap" style="gap:6px">
        <a class="btn btn-primary btn-sm" href="/analyzer?version=${v.id}">${icon("scan")} Analyze</a>
        <button class="btn btn-ghost btn-sm" data-act="versions">${icon("layers")} Versions & compare</button>
        <button class="btn btn-ghost btn-sm" data-act="new-version">${icon("upload")} New version</button>
        <a class="btn btn-ghost btn-sm" href="/api/resumes/versions/${v.id}/download">${icon("download")} Download</a>
        ${r.is_primary ? "" : `<button class="btn btn-ghost btn-sm" data-act="primary">${icon("star")} Set primary</button>`}
        <button class="btn btn-ghost btn-sm" data-act="rename">${icon("edit")} Rename</button>
        <button class="btn btn-danger btn-sm" data-act="delete">${icon("trash")} Delete</button>
        <a class="btn btn-ghost btn-sm" href="/history?resume_id=${r.id}">${icon("clock")} History</a>
      </div>
    </div></div>`;
}

let resumes = [];
function refresh() {
  return load(list, () => api.get("/api/resumes?per_page=50"), (data) => {
    resumes = data.items;
    list.innerHTML = resumes.length ? `<div class="list">${resumes.map(row).join("")}</div>`
      : emptyState("No resumes yet", "Upload your first resume above to get started.", "", "file");
  });
}

list.addEventListener("click", async (e) => {
  const btn = e.target.closest("[data-act]");
  if (!btn) return;
  const id = +btn.closest("[data-id]").dataset.id;
  const r = resumes.find((x) => x.id === id);
  const act = btn.dataset.act;
  try {
    if (act === "delete") {
      if (!(await confirmDialog("Delete resume?", `"${r.name}" and all ${r.version_count} version(s) will be permanently deleted. Past analyses stay in your history without the file.`, { danger: true, confirmLabel: "Delete" }))) return;
      await api.del(`/api/resumes/${id}`);
      toast("Resume deleted", "success");
      refresh();
    } else if (act === "primary") {
      await api.post(`/api/resumes/${id}/primary`);
      toast(`"${r.name}" is now your primary resume`, "success");
      refresh();
    } else if (act === "rename") {
      const name = await modal({ title: "Rename resume", body: `<div class="field"><label for="new-name">Name</label><input class="input" id="new-name" maxlength="120" value="${esc(r.name)}"></div>`,
        actions: [{ label: "Cancel", value: null }, { label: "Save", class: "btn-primary", handler: (m) => m.querySelector("#new-name").value.trim() || false }] });
      if (!name) return;
      await api.patch(`/api/resumes/${id}`, { name });
      refresh();
    } else if (act === "new-version") newVersion(r);
    else if (act === "versions") versions(r);
  } catch (err) { toastError(err); }
});

function newVersion(r) {
  modal({ title: `New version of "${r.name}"`, body: `<p class="small mb-2">Upload an updated file. Previous versions are kept so you can compare scores and changes.</p>
    <input type="file" class="input" id="nv-file" accept=".pdf,.docx,.txt">`,
  actions: [{ label: "Cancel", value: null }, { label: "Upload version", class: "btn-primary", handler: async (m) => {
    const file = m.querySelector("#nv-file").files[0];
    const problem = validateFile(file);
    if (problem) { toast(problem, "error"); return false; }
    const fd = new FormData();
    fd.append("resume", file);
    try {
      const res = await api.upload(`/api/resumes/${r.id}/versions`, fd);
      toast(`Version ${res.version.version_number} uploaded`, "success");
      refresh();
      offerAnalysis(res.version.id);
    } catch (err) { toastError(err); return false; }
  } }] });
}

async function versions(r) {
  const full = await api.get(`/api/resumes/${r.id}`);
  const body = document.createElement("div");
  body.innerHTML = `<p class="small mb-2">Select two versions to compare.</p><div class="list version-list">${full.versions.map((v) => `
    <label class="list-item" style="cursor:pointer"><input type="checkbox" value="${v.id}" style="margin-top:4px;accent-color:var(--accent)">
      <div class="grow"><strong>v${v.version_number}</strong> · ${esc(v.original_filename)}<div class="tiny muted">${fmtDate(v.uploaded_at)} · ${fmtBytes(v.file_size)} · ${v.word_count} words</div></div>
      ${v.latest_score !== null ? `<span class="badge accent">${v.latest_score}</span>` : `<span class="badge">-</span>`}
      <a class="btn btn-ghost btn-sm" href="/api/resumes/versions/${v.id}/download" aria-label="Download v${v.version_number}">${icon("download")}</a>
      ${full.versions.length > 1 ? `<button type="button" class="btn btn-ghost btn-sm" data-del-version="${v.id}" aria-label="Delete v${v.version_number}">${icon("trash")}</button>` : ""}
    </label>`).join("")}</div><div id="cmp" class="mt-3"></div>`;
  modal({ title: `Versions of "${r.name}"`, body, wide: true, actions: [{ label: "Close" }, { label: "Compare selected", class: "btn-primary", handler: async (m) => {
    const ids = $$("input:checked", m).map((c) => c.value);
    if (ids.length !== 2) { toast("Select exactly two versions.", "warn"); return false; }
    try { renderCompare($("#cmp", m), await api.get(`/api/resumes/compare?from=${ids[0]}&to=${ids[1]}`)); } catch (err) { toastError(err); }
    return false;
  } }] });
  body.addEventListener("click", async (e) => {
    const del = e.target.closest("[data-del-version]");
    if (!del) return;
    e.preventDefault();
    if (!(await confirmDialog("Delete version?", "This file version will be permanently deleted.", { danger: true, confirmLabel: "Delete" }))) return;
    try { await api.del(`/api/resumes/versions/${del.dataset.delVersion}`); del.closest(".list-item").remove(); refresh(); } catch (err) { toastError(err); }
  });
}

function renderCompare(el, c) {
  const delta = c.score_change;
  const tags = (arr, cls) => (arr.length ? `<div class="tags">${arr.map((s) => `<span class="tag ${cls}">${esc(s)}</span>`).join("")}</div>` : `<span class="small faint">None</span>`);
  el.innerHTML = `<div class="grid-3 mb-3">
      <div class="card flat stat"><span class="stat-label">v${c.from.version_number} score</span><span class="stat-value">${c.from.latest_score ?? "-"}</span></div>
      <div class="card flat stat"><span class="stat-label">v${c.to.version_number} score</span><span class="stat-value">${c.to.latest_score ?? "-"}</span></div>
      <div class="card flat stat"><span class="stat-label">Change</span><span class="stat-value" style="color:${delta > 0 ? "var(--teal)" : delta < 0 ? "var(--danger)" : "inherit"}">${delta === null ? "Analyze both" : (delta > 0 ? "+" : "") + delta}</span></div></div>
    <div class="grid-2">
      <div><h4 class="mb-2">Added skills</h4>${tags(c.added_skills, "matched")}</div>
      <div><h4 class="mb-2">Removed skills</h4>${tags(c.removed_skills, "missing")}</div>
      <div><h4 class="mb-2">Bullets with metrics</h4><p>${c.bullets_with_metrics.from} → ${c.bullets_with_metrics.to} ${c.added_metrics ? `<span class="badge teal">+${c.added_metrics}</span>` : ""}</p></div>
      <div><h4 class="mb-2">Sections</h4><p class="small">Added: ${esc(c.sections_added.join(", ") || "none")} · Removed: ${esc(c.sections_removed.join(", ") || "none")}</p>
        <p class="small">Words ${c.word_count.from} → ${c.word_count.to} · Projects ${c.projects.from} → ${c.projects.to} · Experience ${c.experience.from} → ${c.experience.to}</p></div>
    </div>
    <h4 class="mt-3 mb-2">New or rewritten bullets</h4>
    ${c.added_bullets.length ? `<ul class="bullets">${c.added_bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>` : `<p class="small faint">No new bullets.</p>`}
    <h4 class="mt-3 mb-2">Removed content</h4>
    ${c.removed_bullets.length ? `<ul class="bullets">${c.removed_bullets.map((b) => `<li style="text-decoration:line-through">${esc(b)}</li>`).join("")}</ul>` : `<p class="small faint">Nothing removed.</p>`}`;
}

refresh();
