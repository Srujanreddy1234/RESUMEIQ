import { api, qs } from "../core/api.js";
import { $, $$, emptyState, esc, icon, load, timeAgo, toastError } from "../core/ui.js";

const el = $("#notifs"), pager = $("#n-pager");
const ICON = { analysis: "scan", learning: "book", application: "kanban", interview: "mic", job: "briefcase" };
let unread = "";

function refresh(page = 1) {
  load(el, () => api.get(`/api/notifications${qs({ unread, page, per_page: 20 })}`), (d) => {
    el.innerHTML = d.items.length ? `<div class="list">${d.items.map((n) => `<div class="list-item notif ${n.is_read ? "" : "unread"}" data-id="${n.id}">
      <span class="list-icon">${icon(ICON[n.type] || "bell")}</span>
      <div class="grow">${n.link ? `<a href="${esc(n.link)}" data-open style="color:var(--text)"><strong>${esc(n.title)}</strong></a>` : `<strong>${esc(n.title)}</strong>`}
        ${n.body ? `<p class="small">${esc(n.body)}</p>` : ""}<span class="tiny faint">${timeAgo(n.created_at)}</span></div>
      ${n.is_read ? "" : `<button class="btn btn-ghost btn-sm" data-read aria-label="Mark as read">${icon("check")}</button>`}
      <button class="btn btn-ghost btn-sm" data-del aria-label="Delete">${icon("trash")}</button></div>`).join("")}</div>`
      : emptyState(unread ? "No unread notifications" : "No notifications", "You're all caught up.", "", "bell");
    pager.innerHTML = d.pages > 1 ? `<button class="btn btn-ghost btn-sm" ${page <= 1 ? "disabled" : ""} data-page="${page - 1}">Previous</button>
      <span class="small muted">Page ${page} of ${d.pages}</span><button class="btn btn-ghost btn-sm" ${page >= d.pages ? "disabled" : ""} data-page="${page + 1}">Next</button>` : "";
    const badge = $("#notif-count");
    if (badge) { badge.textContent = d.unread; badge.hidden = !d.unread; }
  });
}

el.addEventListener("click", async (e) => {
  const row = e.target.closest("[data-id]");
  if (!row) return;
  const id = row.dataset.id;
  try {
    if (e.target.closest("[data-read]")) { await api.post(`/api/notifications/${id}/read`); refresh(); }
    else if (e.target.closest("[data-del]")) { await api.del(`/api/notifications/${id}`); refresh(); }
    else if (e.target.closest("[data-open]") && row.classList.contains("unread")) { api.post(`/api/notifications/${id}/read`).catch(() => {}); }
  } catch (err) { toastError(err); }
});
pager.addEventListener("click", (e) => { const b = e.target.closest("[data-page]"); if (b) refresh(+b.dataset.page); });
$$("[data-filter]").forEach((b) => b.addEventListener("click", () => {
  unread = b.dataset.filter;
  $$("[data-filter]").forEach((x) => x.setAttribute("aria-pressed", x === b));
  refresh();
}));
$("#read-all").onclick = async () => { try { await api.post("/api/notifications/read-all"); refresh(); } catch (err) { toastError(err); } };
refresh();
