// UI kit: escaping, icons, toasts, modals, tabs, state blocks, formatting helpers.

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
/** Escape any value for safe HTML interpolation. ALWAYS use for user/AI/API data. */
export const esc = (v) => (v === null || v === undefined ? "" : String(v).replace(/[&<>"']/g, (c) => ESC[c]));

/** Only allow http(s) links (blocks javascript:/data: URLs). */
export const safeUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : "#");

export const icon = (name, cls = "") => `<svg class="ico ${cls}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;

// ── Toasts ──────────────────────────────────────────────
export function toast(message, type = "info", timeout = 4500) {
  let box = $("#toasts");
  if (!box) {
    box = document.createElement("div");
    box.id = "toasts";
    box.className = "toasts";
    box.setAttribute("aria-live", "polite");
    document.body.appendChild(box);
  }
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.setAttribute("role", type === "error" ? "alert" : "status");
  el.innerHTML = `<div class="grow">${esc(message)}</div><button aria-label="Dismiss">&times;</button>`;
  el.querySelector("button").onclick = () => el.remove();
  box.appendChild(el);
  if (timeout) setTimeout(() => el.remove(), timeout);
}

export function toastError(err, fallback = "Something went wrong.") {
  toast(err?.message || fallback, "error", 6500);
}

// ── Modal ───────────────────────────────────────────────
export function modal({ title, body = "", actions = [], wide = false, onOpen } = {}) {
  return new Promise((resolve) => {
    const prev = document.activeElement;
    const back = document.createElement("div");
    back.className = "modal-backdrop";
    back.innerHTML = `
      <div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <div class="modal-head"><h3 id="modal-title">${esc(title)}</h3>
          <button class="btn btn-ghost btn-icon btn-sm" data-close aria-label="Close">${icon("x")}</button></div>
        <div class="modal-body"></div>
        ${actions.length ? `<div class="modal-foot"></div>` : ""}
      </div>`;
    const bodyEl = back.querySelector(".modal-body");
    if (typeof body === "string") bodyEl.innerHTML = body;
    else bodyEl.appendChild(body);
    const close = (value) => {
      back.remove();
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
      resolve(value);
    };
    actions.forEach((a) => {
      const b = document.createElement("button");
      b.className = `btn ${a.class || "btn-ghost"}`;
      b.textContent = a.label;
      b.onclick = async () => {
        if (a.handler) {
          b.disabled = true;
          try {
            const r = await a.handler(back);
            if (r !== false) close(a.value ?? r ?? true);
          } finally { b.disabled = false; }
        } else close(a.value);
      };
      back.querySelector(".modal-foot").appendChild(b);
    });
    const onKey = (e) => { if (e.key === "Escape") close(null); };
    document.addEventListener("keydown", onKey);
    back.addEventListener("click", (e) => { if (e.target === back || e.target.closest("[data-close]")) close(null); });
    document.body.appendChild(back);
    (back.querySelector("input,textarea,select,button.btn-primary") || back.querySelector("[data-close]"))?.focus();
    onOpen?.(back, close);
  });
}

export const confirmDialog = (title, message, { danger = false, confirmLabel = "Confirm" } = {}) =>
  modal({ title, body: `<p>${esc(message)}</p>`, actions: [
    { label: "Cancel", value: false },
    { label: confirmLabel, value: true, class: danger ? "btn-danger" : "btn-primary" },
  ] }).then((v) => v === true);

// ── Tabs ────────────────────────────────────────────────
export function initTabs(root, onChange) {
  const tabs = $$('[role="tab"]', root);
  const activate = (tab, focus = false) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      const panel = document.getElementById(t.getAttribute("aria-controls"));
      if (panel) panel.hidden = !on;
    });
    if (focus) tab.focus();
    onChange?.(tab.dataset.tab);
  };
  tabs.forEach((t, i) => {
    t.addEventListener("click", () => activate(t));
    t.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") activate(tabs[(i + 1) % tabs.length], true);
      if (e.key === "ArrowLeft") activate(tabs[(i - 1 + tabs.length) % tabs.length], true);
    });
  });
  return { select: (name) => { const t = tabs.find((x) => x.dataset.tab === name); if (t) activate(t); } };
}

// ── States ─────────────────────────────────────────────
export const loadingState = (msg = "Loading...") => `<div class="state" aria-busy="true"><span class="spinner"></span><p>${esc(msg)}</p></div>`;
export const skeleton = (rows = 3) => `<div class="stack">${Array.from({ length: rows }, (_, i) =>
  `<div class="skeleton" style="height:${i === 0 ? 22 : 14}px;width:${90 - i * 12}%"></div>`).join("")}</div>`;
export const emptyState = (title, msg = "", actionHtml = "", ico = "layers") =>
  `<div class="state">${icon(ico, "xl")}<h3>${esc(title)}</h3>${msg ? `<p>${esc(msg)}</p>` : ""}${actionHtml}</div>`;

/** Render an error block with a Retry button wired to `retry`. */
export function errorState(el, err, retry) {
  el.innerHTML = `<div class="state error" role="alert">${icon("alert", "xl")}<h3>Couldn't load this</h3>
    <p>${esc(err?.message || "Something went wrong.")}</p>${retry ? `<button class="btn btn-ghost btn-sm" data-retry>${icon("refresh")} Retry</button>` : ""}</div>`;
  if (retry) el.querySelector("[data-retry]").onclick = retry;
}

/** Run an async loader with loading / error+retry states. */
export async function load(el, loader, render, { message } = {}) {
  el.innerHTML = loadingState(message);
  try {
    const data = await loader();
    render(data);
    return data;
  } catch (err) {
    errorState(el, err, () => load(el, loader, render, { message }));
    return null;
  }
}

// ── Buttons & forms ────────────────────────────────────
export async function withBusy(btn, fn, busyLabel) {
  const html = btn.innerHTML;
  btn.disabled = true;
  btn.classList.add("loading");
  btn.innerHTML = `<span class="spinner"></span> ${esc(busyLabel || "Working...")}`;
  try { return await fn(); } finally {
    btn.disabled = false;
    btn.classList.remove("loading");
    btn.innerHTML = html;
  }
}

export function formData(form) {
  const out = {};
  new FormData(form).forEach((v, k) => {
    if (typeof v === "string") v = v.trim();
    out[k] = v === "" ? null : v;
  });
  $$('input[type="checkbox"]', form).forEach((c) => { if (c.name) out[c.name] = c.checked; });
  return out;
}

export function clearFieldErrors(form) {
  $$(".invalid", form).forEach((el) => el.classList.remove("invalid"));
  $$(".field-error", form).forEach((el) => (el.textContent = ""));
}

/** Show API validation details next to the matching fields. Returns true if any were shown. */
export function showFieldErrors(form, err) {
  clearFieldErrors(form);
  let shown = false;
  (err?.details || []).forEach((d) => {
    const input = form.querySelector(`[name="${CSS.escape(d.field || "")}"]`);
    if (!input) return;
    input.classList.add("invalid");
    input.setAttribute("aria-invalid", "true");
    const slot = input.closest(".field")?.querySelector(".field-error");
    if (slot) slot.textContent = d.message;
    shown = true;
  });
  return shown;
}

// ── Formatting ─────────────────────────────────────────
export const fmtDate = (iso, opts = { day: "numeric", month: "short", year: "numeric" }) =>
  iso ? new Date(iso).toLocaleDateString(undefined, opts) : "-";
export function timeAgo(iso) {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  const units = [["year", 31536000], ["month", 2592000], ["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [u, sec] of units) { const n = Math.floor(s / sec); if (n >= 1) return `${n} ${u}${n > 1 ? "s" : ""} ago`; }
  return "";
}
export const fmtBytes = (b) => (b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(0)} KB` : `${(b / 1048576).toFixed(1)} MB`);
export const fmtMoney = (n, cur = "USD") => {
  if (n === null || n === undefined) return "-";
  try { return new Intl.NumberFormat(undefined, { style: "currency", currency: cur || "USD", maximumFractionDigits: 0 }).format(n); }
  catch { return `${cur || ""} ${Math.round(n).toLocaleString()}`; }
};
export const pct = (v) => (v === null || v === undefined ? "-" : `${Math.round(v)}%`);
export const scoreClass = (s) => (s >= 75 ? "high" : s >= 55 ? "mid" : "low");
export const progressBar = (v, cls = "") => `<div class="progress ${cls}" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(v || 0)}"><span style="width:${Math.max(0, Math.min(100, v || 0))}%"></span></div>`;
export const levelDots = (cur, req) => `<span class="level-dots" title="Level ${cur}${req ? ` / required ${req}` : ""}">${[1, 2, 3, 4, 5]
  .map((i) => `<i class="${i <= cur ? "on" : ""} ${req && i <= req && i > cur ? "req" : ""}"></i>`).join("")}</span>`;

export function scoreRing(score, sub = "/ 100", size = 132) {
  const r = 56, c = 2 * Math.PI * r, off = c - (Math.max(0, Math.min(100, score || 0)) / 100) * c;
  return `<div class="score-ring" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}" viewBox="0 0 132 132" aria-hidden="true">
      <circle class="ring-bg" cx="66" cy="66" r="${r}" fill="none" stroke-width="10"/>
      <circle class="ring-fg" cx="66" cy="66" r="${r}" fill="none" stroke-width="10" stroke-dasharray="${c}" stroke-dashoffset="${off}"/>
    </svg><div class="ring-val"><span class="ring-num">${score ?? "-"}</span><span class="ring-sub">${esc(sub)}</span></div></div>`;
}

/** Highlight "[add measurable result]" / "[X]" placeholders in escaped text. */
export const markPlaceholders = (text) => esc(text).replace(/\[(add measurable result|X|[^\]]{2,40})\]/g, '<mark class="placeholder">[$1]</mark>');

export function debounce(fn, ms = 300) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); toast("Copied to clipboard", "success", 2000); }
  catch { toast("Couldn't copy - select the text and copy manually.", "warn"); }
}

export const params = () => new URLSearchParams(location.search);
export const STAGE_LABELS = { wishlist: "Wishlist", applied: "Applied", assessment: "OA / Assessment", interview: "Interview", offer: "Offer", rejected: "Rejected" };
