import { api } from "../core/api.js";
import { applyTheme } from "../core/theme.js";
import { $, $$, clearFieldErrors, confirmDialog, esc, modal, showFieldErrors, toast, toastError, withBusy } from "../core/ui.js";

const PREFS = [["notify_analysis", "Resume analysis completed"], ["notify_learning", "Learning milestones"],
  ["notify_applications", "Application reminders (follow-ups)"], ["notify_interviews", "Interview reminders"], ["notify_jobs", "Saved-job updates"]];

$("#account-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  clearFieldErrors(form);
  const payload = { full_name: $("#s-name").value.trim(), email: $("#s-email").value.trim(), current_password: $("#s-cur").value || null };
  await withBusy($("#account-btn"), async () => {
    try { await api.patch("/api/users/me", payload); toast("Account updated", "success"); $("#s-cur").value = ""; }
    catch (err) { if (!showFieldErrors(form, err)) toastError(err); }
  }, "Saving...");
});

$("#password-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  clearFieldErrors(form);
  const d = Object.fromEntries(new FormData(form).entries());
  if (d.new_password !== d.confirm_password) return showFieldErrors(form, { details: [{ field: "confirm_password", message: "Passwords do not match." }] });
  await withBusy($("#password-btn"), async () => {
    try { await api.post("/api/auth/change-password", d); toast("Password changed", "success"); form.reset(); }
    catch (err) {
      const details = (err.details || []).map((x) => (x.field === "password" ? { ...x, field: "new_password" } : x));
      if (!showFieldErrors(form, { details })) toastError(err);
    }
  }, "Updating...");
});

function markTheme() {
  const pref = document.documentElement.dataset.themePref || "dark";
  $$("#theme-seg button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.theme === pref));
}
$$("#theme-seg button").forEach((b) => b.addEventListener("click", () => { applyTheme(b.dataset.theme); markTheme(); toast(`Theme: ${b.textContent}`, "success", 1500); }));
markTheme();

async function loadPrefs() {
  const { profile } = await api.get("/api/profile");
  const n = profile.notifications;
  const map = { notify_analysis: n.analysis, notify_learning: n.learning, notify_applications: n.applications, notify_interviews: n.interviews, notify_jobs: n.jobs };
  $("#notif-prefs").innerHTML = PREFS.map(([k, label]) => `<label class="flex between" style="cursor:pointer"><span>${esc(label)}</span>
    <span class="switch"><input type="checkbox" data-pref="${k}" ${map[k] ? "checked" : ""}><span></span></span></label>`).join("");
  $$("[data-pref]").forEach((c) => c.addEventListener("change", async () => {
    try { await api.put("/api/profile", { [c.dataset.pref]: c.checked }); toast("Preference saved", "success", 1500); }
    catch (err) { c.checked = !c.checked; toastError(err); }
  }));
  if (profile.theme && profile.theme !== (document.documentElement.dataset.themePref || "dark")) { applyTheme(profile.theme, false); markTheme(); }
}

$("#del-history").onclick = async () => {
  if (!(await confirmDialog("Delete all analysis history?", "This permanently deletes every analysis. Your resumes are kept.", { danger: true, confirmLabel: "Delete history" }))) return;
  try { const r = await api.del("/api/analysis"); toast(`Deleted ${r.deleted} analyses`, "success"); } catch (err) { toastError(err); }
};

$("#del-account").onclick = () => modal({
  title: "Delete your account permanently?",
  body: `<p class="small mb-3">This deletes your account, every uploaded resume file, analyses, applications, learning progress and all other data. It cannot be undone.</p>
    <div class="field mb-2"><label for="d-pass">Password</label><input class="input" id="d-pass" type="password" autocomplete="current-password"></div>
    <div class="field"><label for="d-confirm">Type DELETE to confirm</label><input class="input" id="d-confirm" autocomplete="off"></div>`,
  actions: [{ label: "Cancel" }, { label: "Delete my account", class: "btn-danger", handler: async (m) => {
    try {
      await api.del("/api/users/me", { password: m.querySelector("#d-pass").value, confirm: m.querySelector("#d-confirm").value.trim() });
      location.href = "/?deleted=1";
    } catch (err) { toastError(err.code === "validation_error" ? { message: "Type DELETE exactly and enter your password." } : err); return false; }
  } }],
});

loadPrefs().catch(toastError);
