import { api } from "../core/api.js";
import { $, $$, clearFieldErrors, formData, icon, params, showFieldErrors, withBusy } from "../core/ui.js";

function message(form, text, type = "error") {
  const el = $("#form-msg", form);
  el.textContent = text;
  el.className = `form-msg ${type}`;
  el.hidden = !text;
}

// Mirrors security.password_strength on the server.
function strength(pw) {
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) s++;
  return Math.min(s, 4);
}

function clientChecks(form, data) {
  const errors = [];
  if ("email" in data && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email || "")) errors.push({ field: "email", message: "Enter a valid email address." });
  if (form.id !== "login-form" && "password" in data) {
    if ((data.password || "").length < 8) errors.push({ field: "password", message: "Use at least 8 characters." });
    else if (!/[A-Za-z]/.test(data.password) || !/\d/.test(data.password)) errors.push({ field: "password", message: "Include at least one letter and one number." });
    if (data.confirm_password !== data.password) errors.push({ field: "confirm_password", message: "Passwords do not match." });
  }
  if (form.id === "login-form" && !data.password) errors.push({ field: "password", message: "Enter your password." });
  if ("full_name" in data && (data.full_name || "").length < 2) errors.push({ field: "full_name", message: "Enter your full name." });
  return errors;
}

async function submit(form, handler) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearFieldErrors(form);
    message(form, "");
    const data = formData(form);
    const errors = clientChecks(form, data);
    if (errors.length) return showFieldErrors(form, { details: errors });
    await withBusy(form.querySelector('button[type="submit"]'), async () => {
      try { await handler(data); } catch (err) {
        if (!showFieldErrors(form, err) || err.code !== "validation_error") message(form, err.message);
      }
    }, "Please wait...");
  });
}

$$("[data-toggle-password]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = document.getElementById(btn.dataset.togglePassword);
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.innerHTML = icon(show ? "eye-off" : "eye");
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
});

const pw = $("#password"), meter = $("#strength");
if (pw && meter) pw.addEventListener("input", () => (meter.dataset.score = strength(pw.value)));

const next = () => {
  const n = params().get("next");
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/dashboard";
};

const login = $("#login-form");
if (login) {
  if (params().get("expired")) message(login, "Your session expired. Please sign in again.", "error");
  if (params().get("registered")) message(login, "Account created - you can sign in now.", "success");
  if (params().get("reset")) message(login, "Password updated - sign in with your new password.", "success");
  submit(login, async (data) => {
    await api.post("/api/auth/login", { email: data.email, password: data.password, remember_me: !!data.remember_me });
    location.href = next();
  });
}

const register = $("#register-form");
if (register) submit(register, async (data) => {
  await api.post("/api/auth/register", data);
  await api.post("/api/auth/login", { email: data.email, password: data.password, remember_me: false });
  location.href = "/profile?welcome=1";
});

const forgot = $("#forgot-form");
if (forgot) submit(forgot, async (data) => {
  const res = await api.post("/api/auth/forgot-password", data);
  message(forgot, res.message, "success");
});

const reset = $("#reset-form");
if (reset) {
  const token = params().get("token");
  if (!token) message(reset, "This reset link is missing its token. Request a new one.");
  submit(reset, async (data) => {
    await api.post("/api/auth/reset-password", { ...data, token });
    location.href = "/login?reset=1";
  });
}
