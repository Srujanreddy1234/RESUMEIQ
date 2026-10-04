import { api, qs } from "../core/api.js";
import { $, confirmDialog, emptyState, esc, fmtDate, icon, load, params, toast, toastError } from "../core/ui.js";

const el = $("#hist"), pager = $("#hist-pager");
const KIND = { resume: "Resume analysis", ats: "ATS check", jd_match: "JD match" };

function refresh(page = 1) {
  const q = { kind: $("#h-kind").value, role: $("#h-role").value.trim(), resume_id: params().get("resume_id"), page, per_page: 15 };
  load(el, () => api.get(`/api/analysis${qs(q)}`), (d) => {
    el.innerHTML = d.items.length ? `<div class="table-wrap"><table class="table responsive"><thead><tr><th>Date</th><th>Type</th><th>Resume</th><th>Target role</th><th>Job description</th><th>Score</th><th>Skills</th><th></th></tr></thead><tbody>
      ${d.items.map((a) => `<tr data-id="${a.id}"><td data-label="Date">${fmtDate(a.created_at)}</td><td data-label="Type"><span class="badge">${KIND[a.kind] || a.kind}</span></td>
        <td data-label="Resume">${a.resume ? `${esc(a.resume.name)} v${a.resume.version_number}` : `<span class="faint">deleted</span>`}</td>
        <td data-label="Target role">${esc(a.target_role || "")}</td><td data-label="Job description">${a.job_description ? esc(a.job_description.title) : "-"}</td>
        <td data-label="Score"><strong>${a.overall_score ?? "-"}</strong></td><td data-label="Skills">${a.skills_identified}</td>
        <td><div class="flex" style="gap:4px;justify-content:flex-end"><a class="btn btn-ghost btn-sm" href="/analyzer?analysis=${a.id}">Open</a>
          <a class="btn btn-ghost btn-sm" href="/reports/analysis?id=${a.id}" target="_blank" rel="noopener" aria-label="Export">${icon("printer")}</a>
          <button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div></td></tr>`).join("")}
      </tbody></table></div>`
      : emptyState("No analyses yet", "Run a resume analysis to start your history.", `<a class="btn btn-primary" href="/analyzer">Analyze resume</a>`, "clock");
    pager.innerHTML = d.pages > 1 ? `<button class="btn btn-ghost btn-sm" ${page <= 1 ? "disabled" : ""} data-page="${page - 1}">Previous</button>
      <span class="small muted">Page ${page} of ${d.pages}</span><button class="btn btn-ghost btn-sm" ${page >= d.pages ? "disabled" : ""} data-page="${page + 1}">Next</button>` : "";
  });
}

el.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-del]");
  if (!b) return;
  if (!(await confirmDialog("Delete analysis?", "This analysis will be permanently removed.", { danger: true, confirmLabel: "Delete" }))) return;
  try { await api.del(`/api/analysis/${b.closest("[data-id]").dataset.id}`); refresh(); } catch (err) { toastError(err); }
});
pager.addEventListener("click", (e) => { const b = e.target.closest("[data-page]"); if (b) refresh(+b.dataset.page); });
$("#hist-filter").addEventListener("submit", (e) => { e.preventDefault(); refresh(); });
$("#clear-all").onclick = async () => {
  if (!(await confirmDialog("Delete all analysis history?", "Every analysis, ATS check and JD match will be permanently deleted. Your resumes are kept.", { danger: true, confirmLabel: "Delete everything" }))) return;
  try { const r = await api.del("/api/analysis"); toast(`Deleted ${r.deleted} analyses`, "success"); refresh(); } catch (err) { toastError(err); }
};
refresh();
