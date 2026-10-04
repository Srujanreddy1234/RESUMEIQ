// Helpers shared by several pages.
import { api } from "./api.js";
import { esc, fmtDate } from "./ui.js";

let resumesCache = null;

export async function getResumes(force = false) {
  if (!resumesCache || force) resumesCache = (await api.get("/api/resumes?per_page=50")).items;
  return resumesCache;
}

/** Fill a <select> with resume versions (latest version of each resume first). Returns resumes. */
export async function fillResumeSelect(select, { allVersions = false } = {}) {
  const resumes = await getResumes();
  if (!resumes.length) {
    select.innerHTML = `<option value="">No resumes yet - upload one first</option>`;
    select.disabled = true;
    return resumes;
  }
  const opts = [];
  for (const r of resumes) {
    const v = r.latest_version;
    if (!v) continue;
    opts.push(`<option value="${v.id}" ${r.is_primary ? "selected" : ""}>${esc(r.name)} · v${v.version_number}${r.is_primary ? " (primary)" : ""}</option>`);
    if (allVersions && r.version_count > 1) {
      const full = await api.get(`/api/resumes/${r.id}`);
      full.versions.slice(1).forEach((old) => opts.push(`<option value="${old.id}">${esc(r.name)} · v${old.version_number} (${fmtDate(old.uploaded_at)})</option>`));
    }
  }
  select.innerHTML = opts.join("");
  select.disabled = false;
  const remembered = localStorage.getItem("riq-last-resume");
  if (remembered && select.querySelector(`option[value="${CSS.escape(remembered)}"]`)) select.value = remembered;
  select.addEventListener("change", () => { try { localStorage.setItem("riq-last-resume", select.value); } catch { /* ignore */ } });
  return resumes;
}

let profileCache = null;
export async function getProfile() {
  if (!profileCache) profileCache = await api.get("/api/auth/me");
  return profileCache;
}

export async function targetRole() {
  try { return (await getProfile()).profile?.target_career || ""; } catch { return ""; }
}

export const aiBadge = (used) => (used ? `<span class="ai-label">AI-assisted</span>` : `<span class="data-label">Rule-based</span>`);

export function aiNote(note) {
  return note ? `<div class="callout warn small mt-2">${esc(note)}</div>` : "";
}
