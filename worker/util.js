// Small helpers shared by the accounts API. Web-standard APIs only, so the same
// code runs on Cloudflare Workers and under the local Node test server.

export class HttpError extends Error {
  constructor(status, code, message) {
    super(message || code);
    this.status = status;
    this.code = code;
  }
}

export function json(data, status = 200, headers = {}) {
  const h = new Headers({ "content-type": "application/json; charset=utf-8", "cache-control": "no-store" });
  for (const [k, v] of Object.entries(headers)) {
    if (Array.isArray(v)) v.forEach(x => h.append(k, x));
    else h.set(k, v);
  }
  return new Response(JSON.stringify(data), { status, headers: h });
}

export function redirect(location, cookies = []) {
  const h = new Headers({ location, "cache-control": "no-store" });
  cookies.forEach(c => h.append("set-cookie", c));
  return new Response(null, { status: 302, headers: h });
}

export const now = () => Math.floor(Date.now() / 1000);

export function b64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomToken(n = 32) {
  const a = new Uint8Array(n);
  crypto.getRandomValues(a);
  return b64url(a);
}

export async function sha256(s) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return b64url(new Uint8Array(d));
}

export function parseCookies(request) {
  const out = {};
  const raw = request.headers.get("cookie") || "";
  for (const part of raw.split(";")) {
    const i = part.indexOf("=");
    if (i < 0) continue;
    const k = part.slice(0, i).trim();
    if (k && !(k in out)) out[k] = part.slice(i + 1).trim();
  }
  return out;
}

// Session cookies are HttpOnly + Secure + SameSite=Lax. `httpOnly:false` is used
// only for the "signed in" marker the page script reads; it carries no secret.
export function cookie(name, value, { maxAge, path = "/", httpOnly = true } = {}) {
  let c = `${name}=${value}; Path=${path}; Secure; SameSite=Lax`;
  if (httpOnly) c += "; HttpOnly";
  if (maxAge !== undefined) c += `; Max-Age=${maxAge}`;
  return c;
}

export async function readJson(request) {
  const type = request.headers.get("content-type") || "";
  if (!type.toLowerCase().startsWith("application/json")) throw new HttpError(415, "json_required", "Send JSON.");
  const text = await request.text();
  if (text.length > 20000) throw new HttpError(413, "too_large", "That request is too large.");
  try {
    const v = JSON.parse(text || "{}");
    if (!v || typeof v !== "object" || Array.isArray(v)) throw new Error();
    return v;
  } catch {
    throw new HttpError(400, "bad_json", "That request could not be read.");
  }
}

// ---- validation -----------------------------------------------------------

const RESERVED = new Set(["admin", "administrator", "logpose", "log_pose", "support", "help", "moderator", "mod",
  "staff", "system", "official", "bandai", "null", "undefined", "me", "you", "account", "anonymous", "deleted"]);

export function cleanUsername(v) {
  const s = String(v || "").trim();
  if (!/^[A-Za-z0-9_]{3,20}$/.test(s)) {
    throw new HttpError(400, "bad_username", "Usernames are 3–20 characters: letters, numbers and underscores.");
  }
  if (RESERVED.has(s.toLowerCase())) throw new HttpError(400, "bad_username", "That username is not available.");
  return s;
}

// Accepts "@name", "name" or an instagram.com profile URL; stores the bare handle.
export function cleanInstagram(v) {
  let s = String(v ?? "").trim();
  if (!s) return "";
  const m = s.match(/^https?:\/\/(?:www\.)?instagram\.com\/([^/?#]+)\/?(?:[?#].*)?$/i);
  if (m) s = m[1];
  s = s.replace(/^@/, "");
  if (!/^[A-Za-z0-9._]{1,30}$/.test(s)) {
    throw new HttpError(400, "bad_instagram", "Enter an Instagram username, like alpine.cards.");
  }
  return s;
}

// A refs link is any https page the person points to as proof of past deals.
export function cleanRefsUrl(v) {
  const s = String(v ?? "").trim();
  if (!s) return "";
  let u;
  try { u = new URL(s); } catch { throw new HttpError(400, "bad_refs", "Enter a full link starting with https://"); }
  if (u.protocol !== "https:" || u.username || u.password || !u.hostname.includes(".") || s.length > 300) {
    throw new HttpError(400, "bad_refs", "Enter a full link starting with https://");
  }
  return u.toString();
}

const BGS = new Set(["BL"]);
for (let g = 1; g <= 10; g += 0.5) BGS.add(String(g));
const PSA = new Set(["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]);

export function cleanGrade(grader, grade) {
  const g = String(grader || "").toLowerCase();
  const v = String(grade ?? "").trim().toUpperCase();
  if (g === "raw") return { grader: "raw", grade: "" };
  if (g === "psa" && PSA.has(v)) return { grader: "psa", grade: v };
  if (g === "bgs" && BGS.has(v)) return { grader: "bgs", grade: v };
  throw new HttpError(400, "bad_grade", "Choose Raw, a PSA grade from 1 to 10, or a BGS grade from 1 to 10 or Black Label.");
}
