import { api } from "../core/api.js";
import { aiBadge, fillResumeSelect, targetRole } from "../core/common.js";
import { $, $$, copyText, emptyState, errorState, esc, icon, loadingState, markPlaceholders, params, toast, toastError, withBusy } from "../core/ui.js";

let scope = "entire";
const out = $("#out");

$$("#scope button").forEach((b) => b.addEventListener("click", () => {
  scope = b.dataset.scope;
  $$("#scope button").forEach((x) => x.setAttribute("aria-pressed", x === b));
  $("#bullet-field").hidden = scope !== "bullet";
}));

async function init() {
  $("#i-role").value = await targetRole();
  await fillResumeSelect($("#i-version"), { allVersions: true });
  if (params().get("version")) $("#i-version").value = params().get("version");
  if ($("#i-version").disabled) out.innerHTML = emptyState("Upload a resume first", "", `<a class="btn btn-primary" href="/resumes">Upload resume</a>`, "file");
}

$("#improve-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (scope === "bullet" && $("#i-bullet").value.trim().length < 5) return toast("Paste the bullet you want to improve.", "warn");
  await withBusy($("#improve-btn"), async () => {
    out.innerHTML = loadingState("Reviewing your bullets...");
    try {
      const r = await api.post("/api/analysis/improve", { resume_version_id: +$("#i-version").value, scope,
        bullet: scope === "bullet" ? $("#i-bullet").value.trim() : null, target_role: $("#i-role").value.trim() || null });
      render(r);
    } catch (err) { errorState(out, err, () => $("#improve-btn").click()); }
  }, "Working...");
});

function render(r) {
  const items = r.items.map((it, i) => `
    <div class="card mb-2">
      <div class="flex between mb-2 flex-wrap"><span class="badge">${esc(it.section)}</span>
        ${it.needs_metric ? `<span class="badge warn">${icon("info", "sm")} Add a measurable result here</span>` : ""}</div>
      <div class="diff">
        <div class="diff-col diff-old"><span class="label">Current</span>${esc(it.original)}</div>
        <div class="diff-col diff-new"><span class="label">Improved</span><span data-improved="${i}">${markPlaceholders(it.improved)}</span></div>
      </div>
      <p class="small mt-2">${esc(it.explanation)}</p>
      <button class="btn btn-ghost btn-sm mt-2" data-copy="${i}">${icon("copy")} Copy improved</button>
    </div>`).join("");
  const weak = (r.weak_bullets || []).length ? `<div class="card mb-3"><h3 class="mb-2">Why these bullets were flagged</h3><div class="list">${r.weak_bullets.map((b) => `
      <div class="list-item"><div class="grow"><p style="color:var(--text)">${esc(b.text)}</p><div class="tags mt-1">${b.reasons.map((x) => `<span class="tag partial">${esc(x)}</span>`).join("")}</div></div></div>`).join("")}</div></div>` : "";
  out.innerHTML = `
    <div class="flex between mb-2 flex-wrap"><h2>Suggestions</h2>${aiBadge(r.ai_used)}</div>
    <div class="callout mb-3">${icon("shield")} <span>${esc(r.rule)}</span></div>
    ${r.ai_note ? `<div class="callout warn small mb-3">${esc(r.ai_note)}</div>` : ""}
    ${r.improved_summary ? `<div class="card mb-3"><h3 class="mb-2">Improved summary</h3><p style="color:var(--text)">${markPlaceholders(r.improved_summary)}</p>
      <button class="btn btn-ghost btn-sm mt-2" id="copy-summary">${icon("copy")} Copy</button></div>` : ""}
    ${r.skills_section_advice?.length ? `<div class="card mb-3"><h3 class="mb-2">Skills section</h3><ul class="bullets">${r.skills_section_advice.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
    ${items || (r.improved_summary || r.skills_section_advice?.length ? "" : emptyState("Nothing to improve here", "Your bullets in this section already lead with action verbs and include results.", "", "check"))}
    ${weak}`;
  out.querySelectorAll("[data-copy]").forEach((b) => (b.onclick = () => copyText(r.items[+b.dataset.copy].improved)));
  $("#copy-summary")?.addEventListener("click", () => copyText(r.improved_summary));
}

init().catch(toastError);
