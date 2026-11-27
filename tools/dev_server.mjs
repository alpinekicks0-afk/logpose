// Local test server for the accounts Worker.
//
//   node tools/dev_server.mjs [port]
//
// Runs worker/index.js unmodified under Node: D1 is emulated with node:sqlite
// (in memory), the asset server reads ./public, and the three outside services
// (Google, Discord, Turnstile) are replaced by stand-ins. Nothing here ships:
// wrangler only bundles worker/.
//
// Stand-in sign-in: set a cookie `mock_user=<name>` before opening
// /api/auth/google/start; the fake provider signs you in as that identity.
// Stand-in captcha: the page sends the token "ok" when the site key is "test-mode".

import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DatabaseSync } from "node:sqlite";
import worker from "../worker/index.js";
import { resetSchemaCache } from "../worker/schema.js";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "public");
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json",
  ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".xml": "application/xml", ".txt": "text/plain" };

// ---- D1 on node:sqlite ------------------------------------------------------
class Statement {
  constructor(db, sql, args = []) { this.db = db; this.sql = sql; this.args = args; }
  bind(...args) { return new Statement(this.db, this.sql, args.map(a => (a === undefined ? null : typeof a === "boolean" ? Number(a) : a))); }
  _rows() { return this.db.prepare(this.sql).all(...this.args).map(r => ({ ...r })); }
  _returnsRows() { return /^\s*(SELECT|WITH)\b/i.test(this.sql) || /\bRETURNING\b/i.test(this.sql); }
  async first(col) { const r = this._rows()[0]; return r === undefined ? null : col ? r[col] : r; }
  async all() { return { results: this._rows(), success: true, meta: {} }; }
  async run() {
    if (this._returnsRows()) return this.all();
    const r = this.db.prepare(this.sql).run(...this.args);
    return { success: true, results: [], meta: { changes: Number(r.changes), last_row_id: Number(r.lastInsertRowid) } };
  }
}
export function makeD1() {
  const db = new DatabaseSync(":memory:");
  return {
    prepare: sql => new Statement(db, sql),
    async batch(stmts) {
      db.exec("BEGIN");
      try {
        const out = [];
        for (const s of stmts) out.push(await s.run());
        db.exec("COMMIT");
        return out;
      } catch (e) { db.exec("ROLLBACK"); throw e; }
    },
    _raw: db,
  };
}

// ---- static assets ----------------------------------------------------------
function assetResponse(request) {
  const url = new URL(request.url);
  let p = decodeURIComponent(url.pathname);
  if (p.endsWith("/")) p += "index.html";
  let file = path.join(ROOT, p);
  if (!file.startsWith(ROOT)) return new Response("bad path", { status: 400 });
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
  if (!fs.existsSync(file)) {
    return new Response(fs.readFileSync(path.join(ROOT, "404.html")), { status: 404, headers: { "content-type": TYPES[".html"] } });
  }
  return new Response(fs.readFileSync(file), { headers: { "content-type": TYPES[path.extname(file)] || "application/octet-stream" } });
}

// ---- stand-ins for Google, Discord and Turnstile ------------------------------
const b64 = o => Buffer.from(JSON.stringify(o)).toString("base64url");
async function fakeFetch(input, init = {}) {
  const url = String(input);
  const body = new URLSearchParams(init.body || "");
  if (url === "https://oauth2.googleapis.com/token") {
    const code = body.get("code") || "";
    if (!code.startsWith("mock-") || body.get("client_secret") !== "test-google-secret" || !body.get("code_verifier")) {
      return Response.json({ error: "invalid_grant" }, { status: 400 });
    }
    return Response.json({ id_token: `x.${b64({ iss: "https://accounts.google.com", aud: "test-google-id", sub: "g-" + code.slice(5) })}.x` });
  }
  if (url === "https://discord.com/api/oauth2/token") {
    const code = body.get("code") || "";
    if (!code.startsWith("mock-")) return Response.json({ error: "invalid_grant" }, { status: 400 });
    return Response.json({ access_token: "tok-" + code.slice(5) });
  }
  if (url === "https://discord.com/api/users/@me") {
    const auth = (init.headers && (init.headers.authorization || init.headers.Authorization)) || "";
    return Response.json({ id: "d-" + auth.replace("Bearer tok-", "") });
  }
  if (url === "https://challenges.cloudflare.com/turnstile/v0/siteverify") {
    return Response.json({ success: body.get("secret") === "test-turnstile-secret" && body.get("response") === "ok" });
  }
  return new Response("unexpected outbound request: " + url, { status: 500 });
}

export function makeEnv(origin, overrides = {}) {
  resetSchemaCache();
  return {
    DB: makeD1(),
    ASSETS: { fetch: async req => assetResponse(req) },
    FETCH: fakeFetch,
    GOOGLE_CLIENT_ID: "test-google-id", GOOGLE_CLIENT_SECRET: "test-google-secret",
    DISCORD_CLIENT_ID: "test-discord-id", DISCORD_CLIENT_SECRET: "test-discord-secret",
    GOOGLE_AUTH_URL: origin + "/__mock/authorize", DISCORD_AUTH_URL: origin + "/__mock/authorize",
    TURNSTILE_SITE_KEY: "test-mode", TURNSTILE_SECRET: "test-turnstile-secret",
    ADMIN_USERNAMES: "alpine",
    ...overrides,
  };
}

// ---- http front ---------------------------------------------------------------
export function startServer(port, overrides = {}) {
  const origin = `http://localhost:${port}`;
  const env = makeEnv(origin, overrides);
  const server = http.createServer(async (req, res) => {
    try {
      const chunks = [];
      for await (const c of req) chunks.push(c);
      const url = new URL(req.url, origin);
      let response;
      if (url.pathname === "/__mock/authorize") {
        // The fake provider: sign in as whoever the mock_user cookie names.
        const who = (/(?:^|;\s*)mock_user=([^;]+)/.exec(req.headers.cookie || "") || [])[1];
        const back = new URL(url.searchParams.get("redirect_uri"));
        if (who) back.searchParams.set("code", "mock-" + who);
        back.searchParams.set("state", url.searchParams.get("state") || "");
        response = new Response(null, { status: 302, headers: { location: back.toString() } });
      } else {
        const headers = new Headers();
        for (const [k, v] of Object.entries(req.headers)) headers.set(k, Array.isArray(v) ? v.join(", ") : v);
        const init = { method: req.method, headers, redirect: "manual" };
        if (!["GET", "HEAD"].includes(req.method)) init.body = Buffer.concat(chunks);
        const request = new Request(url, init);
        // Same split as production: the Worker only sees /api/* and requests that match no file.
        response = url.pathname.startsWith("/api/") ? await worker.fetch(request, env) : assetResponse(request);
      }
      const out = {};
      response.headers.forEach((v, k) => { if (k !== "set-cookie") out[k] = v; });
      const cookies = response.headers.getSetCookie();
      if (cookies.length) out["set-cookie"] = cookies;
      res.writeHead(response.status, out);
      res.end(Buffer.from(await response.arrayBuffer()));
    } catch (e) {
      console.error(e);
      res.writeHead(500); res.end(String(e));
    }
  });
  return new Promise(resolve => server.listen(port, () => resolve({ server, env, origin })));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2]) || 8787;
  startServer(port).then(({ origin }) => console.log("Log Pose test server on " + origin));
}
