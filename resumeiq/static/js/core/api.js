// REST client: CSRF double-submit header, one silent token refresh on 401, typed errors.

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function cookie(name) {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

let refreshing = null;

async function refreshSession() {
  if (!refreshing) {
    refreshing = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-TOKEN": cookie("csrf_refresh_token") || "" },
    }).then((r) => r.ok).catch(() => false).finally(() => setTimeout(() => (refreshing = null), 0));
  }
  return refreshing;
}

const RETRYABLE_AUTH = new Set(["token_expired", "unauthorized", "invalid_token", "session_expired"]);

async function request(method, url, { body, form, retry = true, signal } = {}) {
  const headers = { Accept: "application/json" };
  if (method !== "GET") headers["X-CSRF-TOKEN"] = cookie("csrf_access_token") || "";
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: "same-origin", signal });
  } catch (err) {
    if (err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Network error - check your connection and try again.");
  }
  if (res.status === 204) return null;
  let data = null;
  const type = res.headers.get("content-type") || "";
  if (type.includes("application/json")) data = await res.json().catch(() => null);

  if (res.status === 401 && retry && RETRYABLE_AUTH.has(data?.error?.code) && !url.startsWith("/api/auth/")) {
    if (await refreshSession()) return request(method, url, { body, form, retry: false, signal });
    const next = encodeURIComponent(location.pathname + location.search);
    location.href = `/login?expired=1&next=${next}`;
    throw new ApiError(401, "session_expired", "Your session has expired.");
  }
  if (!res.ok) {
    const e = data?.error || {};
    const fallback = res.status === 413 ? "File is too large (maximum 16 MB)."
      : res.status === 429 ? "Too many requests - please wait a moment."
      : res.status >= 500 ? "The server had a problem. Please try again." : "Request failed.";
    throw new ApiError(res.status, e.code || `http_${res.status}`, e.message || fallback, e.details);
  }
  return data;
}

export const api = {
  get: (url, opts) => request("GET", url, opts),
  post: (url, body, opts = {}) => request("POST", url, { ...opts, body }),
  put: (url, body, opts = {}) => request("PUT", url, { ...opts, body }),
  patch: (url, body, opts = {}) => request("PATCH", url, { ...opts, body }),
  del: (url, body, opts = {}) => request("DELETE", url, { ...opts, body }),
  upload: (url, formData, opts = {}) => request("POST", url, { ...opts, form: formData }),
};

export function qs(params) {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || v === false) return;
    if (Array.isArray(v)) v.forEach((x) => u.append(k, x));
    else u.append(k, v);
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}
