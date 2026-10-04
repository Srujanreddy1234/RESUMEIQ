// App shell behaviour shared by every signed-in page: sidebar, theme, global search, notifications, user menu.
import { api } from "./api.js";
import { applyTheme } from "./theme.js";
import { $, debounce, esc, icon, toast } from "./ui.js";

function initSidebar() {
  const sidebar = $("#sidebar"), scrim = $("#scrim"), toggle = $("#menu-toggle");
  if (!sidebar || !toggle) return;
  const set = (open) => {
    sidebar.classList.toggle("open", open);
    scrim.classList.toggle("show", open);
    toggle.setAttribute("aria-expanded", open);
  };
  toggle.onclick = () => set(!sidebar.classList.contains("open"));
  scrim.onclick = () => set(false);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
}

function initTheme() {
  const btn = $("#theme-toggle");
  if (!btn) return;
  const pref = document.documentElement.dataset.themePref || "dark";
  applyTheme(pref, false);
  btn.onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", () => {
    if (document.documentElement.dataset.themePref === "system") applyTheme("system", false);
  });
}

function initSearch() {
  const input = $("#global-search"), box = $("#search-results");
  if (!input) return;
  const groups = [["jobs", "Jobs", "briefcase"], ["skills", "Skills", "graph"], ["resources", "Learning resources", "book"],
    ["applications", "Applications", "kanban"], ["analyses", "Resume analyses", "scan"]];
  const close = () => { box.hidden = true; input.setAttribute("aria-expanded", "false"); };
  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) return close();
    try {
      const data = await api.get(`/api/search?q=${encodeURIComponent(q)}`);
      const html = groups.filter(([k]) => data[k]?.length).map(([k, label, ic]) => `<div class="group-label">${label}</div>` +
        data[k].map((r) => `<a href="${esc(r.link)}" ${r.external ? 'target="_blank" rel="noopener noreferrer"' : ""}>${icon(ic)}
          <span class="grow"><span class="break">${esc(r.title)}</span><br><span class="tiny muted">${esc(r.subtitle || "")}</span></span></a>`).join("")).join("");
      box.innerHTML = html || `<p class="small muted" style="padding:10px">No results for "${esc(q)}"</p>`;
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
    } catch { close(); }
  }, 250);
  input.addEventListener("input", run);
  input.addEventListener("focus", () => { if (box.innerHTML && input.value.trim().length >= 2) box.hidden = false; });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) close(); });
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); input.focus(); }
    if (e.key === "Escape") close();
  });
}

async function refreshUnread() {
  const badge = $("#notif-count");
  if (!badge) return;
  try {
    const { unread } = await api.get("/api/notifications/unread-count");
    badge.textContent = unread > 99 ? "99+" : unread;
    badge.hidden = !unread;
  } catch { /* non-critical */ }
}

function initUserMenu() {
  const chip = $("#user-chip"), menu = $("#user-menu");
  if (!chip) return;
  chip.onclick = (e) => { e.stopPropagation(); menu.hidden = !menu.hidden; chip.setAttribute("aria-expanded", !menu.hidden); };
  document.addEventListener("click", (e) => { if (!e.target.closest("#user-menu")) menu.hidden = true; });
  $("#logout-btn")?.addEventListener("click", logout);
}

export async function logout() {
  try { await api.post("/api/auth/logout"); } catch { /* cookies are cleared server-side anyway */ }
  try { localStorage.removeItem("riq-last-resume"); } catch { /* ignore */ }
  location.href = "/login";
}

function initAvatar() {
  const av = $("#nav-avatar");
  if (av?.dataset.hasAvatar === "1") {
    const img = new Image();
    img.alt = "";
    img.onload = () => { av.textContent = ""; av.appendChild(img); };
    img.src = "/api/profile/avatar";
  }
}

initSidebar();
initTheme();
initSearch();
initUserMenu();
initAvatar();
refreshUnread();
setInterval(refreshUnread, 60000);
window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.name === "AbortError") return;
  console.error(e.reason);
  if (e.reason?.message) toast(e.reason.message, "error");
});
