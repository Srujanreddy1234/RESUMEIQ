import { api } from "../core/api.js";
import { barChart, lineChart } from "../core/charts.js";
import { $, confirmDialog, esc, fmtDate, load, timeAgo, toast, toastError } from "../core/ui.js";

const root = $("#admin");

function render(o, users) {
  const ai = o.ai_usage;
  root.innerHTML = `
    <section class="grid-4 mb-3">${[["Users", o.users.total, `${o.users.new_7d} new · ${o.users.active_7d} active (7d)`], ["Resumes", o.resumes, `${o.resume_versions} versions`],
      ["Analyses", o.analyses.total, `${o.analyses.last_7d} in the last 7 days`], ["AI requests", ai.total_requests, `${ai.total_failures} failed`],
      ["API failures (7d)", o.api_failures_7d, "Job APIs + AI"], ["Auth failures (7d)", o.auth_failures_7d, "Failed sign-ins"], ["Stored jobs", o.jobs_stored, ""],
      ["Errors (7d)", o.events_7d.error || 0, "Unhandled exceptions"]]
      .map(([l, v, n]) => `<div class="card stat"><span class="stat-label">${l}</span><span class="stat-value">${v}</span><span class="stat-note">${esc(n)}</span></div>`).join("")}</section>
    <section class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">AI requests (14 days)</h3><div class="chart-box"><canvas id="c-ai"></canvas></div></div>
      <div class="card"><h3 class="mb-2">AI usage by service</h3><div class="table-wrap"><table class="table"><thead><tr><th>Service</th><th>Requests</th><th>Tokens</th><th>Failures</th></tr></thead><tbody>
        ${ai.by_service.map((s) => `<tr><td>${esc(s.service)}</td><td>${s.requests}</td><td>${s.tokens.toLocaleString()}</td><td>${s.failures}</td></tr>`).join("") || `<tr><td colspan="4" class="faint">No AI usage yet</td></tr>`}</tbody></table></div></div>
      <div class="card"><h3 class="mb-2">Most common target roles</h3><div class="chart-box"><canvas id="c-roles"></canvas></div></div>
      <div class="card"><h3 class="mb-2">Most common missing skills</h3><div class="chart-box"><canvas id="c-missing"></canvas></div></div>
    </section>
    <section class="grid-2 mb-3">
      <div class="card"><h3 class="mb-2">Recent system errors</h3><div class="list">${o.recent_errors.map((e) => `<div class="list-item"><div class="grow"><strong class="small">${esc(e.category)}: ${esc(e.message)}</strong>
        <div class="tiny faint">${esc(e.path || "")} · ${timeAgo(e.created_at)} · request ${esc(e.request_id || "-")}</div></div></div>`).join("") || `<p class="small faint">No errors recorded.</p>`}</div></div>
      <div class="card"><h3 class="mb-2">Request latency (this worker)</h3><div class="table-wrap"><table class="table"><thead><tr><th>Endpoint</th><th>n</th><th>p50</th><th>p95</th></tr></thead><tbody>
        ${o.latency.endpoints.map((r) => `<tr><td class="small">${esc(r.endpoint)}</td><td>${r.count}</td><td>${r.p50_ms}ms</td><td>${r.p95_ms}ms</td></tr>`).join("") || `<tr><td colspan="4" class="faint">No data yet</td></tr>`}</tbody></table></div></div>
    </section>
    <section class="card"><h3 class="mb-2">Users</h3><div class="table-wrap"><table class="table responsive"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Joined</th><th>Last login</th><th>Resumes</th><th>Analyses</th><th>Status</th></tr></thead><tbody>
      ${users.items.map((u) => `<tr data-id="${u.id}"><td data-label="Name">${esc(u.full_name)}</td><td data-label="Email" class="break">${esc(u.email)}</td><td data-label="Role">${esc(u.role)}</td>
        <td data-label="Joined">${fmtDate(u.created_at)}</td><td data-label="Last login">${u.last_login_at ? timeAgo(u.last_login_at) : "-"}</td><td data-label="Resumes">${u.resumes}</td><td data-label="Analyses">${u.analyses}</td>
        <td data-label="Status"><button class="btn btn-sm ${u.is_active ? "btn-ghost" : "btn-danger"}" data-toggle="${u.is_active ? "0" : "1"}">${u.is_active ? "Active" : "Deactivated"}</button></td></tr>`).join("")}
    </tbody></table></div><p class="tiny faint mt-2">Showing ${users.items.length} of ${users.total} users.</p></section>`;
  lineChart($("#c-ai"), ai.daily.map((d) => d.date), ai.daily.map((d) => d.requests), { empty: "No AI requests in the last 14 days." });
  barChart($("#c-roles"), o.top_target_roles.map((r) => r.role), o.top_target_roles.map((r) => r.count), { horizontal: true, empty: "No target roles set yet." });
  barChart($("#c-missing"), o.top_missing_skills.map((r) => r.skill), o.top_missing_skills.map((r) => r.count), { horizontal: true, empty: "No skill-gap data yet." });
}

root.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-toggle]");
  if (!b) return;
  const active = b.dataset.toggle === "1";
  if (!(await confirmDialog(active ? "Reactivate user?" : "Deactivate user?", active ? "They will be able to sign in again." : "They will be signed out and unable to sign in.", { danger: !active }))) return;
  try { await api.patch(`/api/admin/users/${b.closest("[data-id]").dataset.id}`, { is_active: active }); toast("User updated", "success"); init(); }
  catch (err) { toastError(err); }
});

function init() {
  load(root, () => Promise.all([api.get("/api/admin/overview"), api.get("/api/admin/users?per_page=50")]), ([o, u]) => render(o, u));
}
init();
