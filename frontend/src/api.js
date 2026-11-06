const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const STORAGE_KEY = "shophub.tokens";

export class ApiError extends Error {
  constructor(status, code, message, details = [], correlationId = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
  }

  // the server's message for one form field, if it has one
  fieldError(field) {
    const found = this.details.find((d) => d.field === field);
    return found ? found.message : null;
  }
}

let tokens = null;
try {
  tokens = JSON.parse(localStorage.getItem(STORAGE_KEY));
} catch {
  tokens = null;
}

let onAuthLost = () => {};
export function setOnAuthLost(fn) {
  onAuthLost = fn;
}

export function getTokens() {
  return tokens;
}

export function setTokens(value) {
  tokens = value;
  try {
    if (value) localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage can be blocked; the app still works until the page is closed */
  }
}

export function newIdempotencyKey() {
  return crypto.randomUUID();
}

function buildUrl(path, params) {
  const url = new URL(path, BASE);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  });
  return url.toString();
}

async function toApiError(res) {
  let body = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const correlationId = res.headers.get("x-correlation-id");
  const e = body && body.error;
  if (e) {
    return new ApiError(res.status, e.code, e.message, e.details || [], e.correlation_id || correlationId);
  }
  return new ApiError(res.status, "request_failed", "Something went wrong. Please try again.", [], correlationId);
}

// Only one refresh at a time (a refresh token can be used once)
let refreshPromise = null;

function refreshTokens() {
  if (!refreshPromise) {
    refreshPromise = fetch(buildUrl("/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh_token }),
    })
      .then(async (res) => {
        if (!res.ok) throw new Error("refresh failed");
        const data = await res.json();
        setTokens({ access_token: data.access_token, refresh_token: data.refresh_token });
      })
      .catch(() => {
        setTokens(null);
        onAuthLost();
        throw new ApiError(401, "session_expired", "Your session has expired. Please sign in again.");
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function request(path, { method = "GET", body, params, auth = true, headers = {}, signal } = {}) {
  const url = buildUrl(path, params);

  const send = () => {
    const h = { ...headers };
    const hasBody = body !== undefined;
    const isForm = typeof FormData !== "undefined" && body instanceof FormData;
    if (hasBody && !isForm) h["Content-Type"] = "application/json";
    if (auth && tokens && tokens.access_token) h.Authorization = `Bearer ${tokens.access_token}`;
    return fetch(url, { method, headers: h, body: hasBody ? (isForm ? body : JSON.stringify(body)) : undefined, signal });
  };

  let res;
  try {
    res = await send();
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new ApiError(0, "network_error", "We could not reach the server. Please check your connection and try again.");
  }

  // an expired login: get new tokens once and try again
  if (res.status === 401 && auth && tokens && tokens.refresh_token) {
    await refreshTokens();
    try {
      res = await send();
    } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new ApiError(0, "network_error", "We could not reach the server. Please check your connection and try again.");
    }
  }

  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return null;
  return res.json();
}