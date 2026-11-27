// Log Pose accounts API.
//
// The site itself is static files; this Worker only answers /api/* (see
// run_worker_first in wrangler.jsonc) and hands everything else to the asset
// server. It needs: a D1 database bound as DB, a Turnstile secret, and client
// credentials for Google and/or Discord sign-in. If any of those are missing
// the matching feature answers "not set up" instead of failing open.

import { HttpError, json, redirect, now, randomToken, sha256, b64url, parseCookies, cookie, readJson,
  cleanUsername, cleanInstagram, cleanRefsUrl, cleanGrade } from "./util.js";
import { ensureSchema } from "./schema.js";

const SESSION_DAYS = 30;
const SESSION_COOKIE = "lp_s";      // HttpOnly session token
const MARKER_COOKIE = "lp_in";      // readable "signed in" hint for the page script, no secret
const SIGNUP_COOKIE = "lp_signup";  // HttpOnly, between first sign-in and finishing sign-up
const OAUTH_COOKIE = "lp_oauth";    // HttpOnly, state + PKCE verifier for one sign-in attempt
const MAX_WISHLIST = 2000;
const MAX_COLLECTION = 2000;
const MAX_MESSAGE = 1000;

const PROVIDERS = {
  google: {
    authUrl: "https://accounts.google.com/o/oauth2/v2/auth",
    tokenUrl: "https://oauth2.googleapis.com/token",
    scope: "openid",
    pkce: true,
  },
  discord: {
    authUrl: "https://discord.com/oauth2/authorize",
    tokenUrl: "https://discord.com/api/oauth2/token",
    userUrl: "https://discord.com/api/users/@me",
    scope: "identify",
    pkce: false,
  },
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);
    try {
      return await api(request, env, url);
    } catch (err) {
      if (err instanceof HttpError) return json({ error: err.code, message: err.message }, err.status);
      console.error("api error", err && err.stack ? err.stack : err);
      return json({ error: "server_error", message: "Something went wrong. Please try again." }, 500);
    }
  },
};

// ---------------------------------------------------------------- routing --

async function api(request, env, url) {
  const method = request.method.toUpperCase();
  const path = url.pathname.replace(/\/+$/, "");
  const seg = path.split("/").slice(2).map(s => { try { return decodeURIComponent(s); } catch { return s; } });

  if (path === "/api/config" && method === "GET") {
    return json({
      ready: !!env.DB,
      providers: { google: hasProvider(env, "google"), discord: hasProvider(env, "discord") },
      turnstileSiteKey: env.TURNSTILE_SITE_KEY || "",
    });
  }
  if (!env.DB) throw new HttpError(503, "not_set_up", "Accounts are not switched on yet.");
  await ensureSchema(env.DB);

  // Anything that changes data must come from our own pages: a custom header
  // (which a cross-site form cannot send) and, when the browser gives one, a
  // matching Origin.
  if (method !== "GET" && method !== "HEAD") {
    const origin = request.headers.get("origin");
    if (origin && origin !== url.origin) throw new HttpError(403, "bad_origin", "That request was not allowed.");
    if (request.headers.get("x-requested-with") !== "logpose") {
      throw new HttpError(403, "bad_request", "That request was not allowed.");
    }
  }

  if (seg[0] === "auth" && method === "GET") {
    if (seg[2] === "start") return authStart(request, env, url, seg[1]);
    if (seg[2] === "callback") return authCallback(request, env, url, seg[1]);
  }

  const me = await currentUser(request, env);

  if (path === "/api/me" && method === "GET") return getMe(request, env, me);
  if (path === "/api/signup" && method === "POST") return signup(request, env);
  if (path === "/api/logout" && method === "POST") return logout(request, env);

  if (!me) throw new HttpError(401, "signed_out", "Sign in to do that.");

  if (path === "/api/me" && method === "PATCH") return patchMe(request, env, me);
  if (path === "/api/me" && method === "DELETE") return deleteMe(request, env, me);

  if (seg[0] === "wishlist") {
    if (seg.length === 1 && method === "GET") return listWishlist(env, me);
    if (seg.length === 2 && method === "PUT") return addWish(env, me, seg[1]);
    if (seg.length === 2 && method === "DELETE") return removeWish(env, me, seg[1]);
  }
  if (seg[0] === "collection") {
    if (seg.length === 1 && method === "GET") return listCollection(env, me);
    if (seg.length === 1 && method === "POST") return addOwned(request, env, me);
    if (seg.length === 2 && method === "PATCH") return editOwned(request, env, me, seg[1]);
    if (seg.length === 2 && method === "DELETE") return removeOwned(env, me, seg[1]);
  }
  if (path === "/api/card-status" && method === "GET") return cardStatus(env, me, url.searchParams.get("card") || "");

  if (seg[0] === "requests") {
    if (seg.length === 1 && method === "GET") return listRequests(env, me);
    if (seg.length === 2 && method === "POST") return answerRequest(request, env, me, seg[1]);
  }
  if (seg[0] === "chats") {
    if (seg.length === 1 && method === "GET") return listChats(env, me);
    if (seg.length === 3 && seg[2] === "messages" && method === "GET") return listMessages(env, me, seg[1], url);
    if (seg.length === 3 && seg[2] === "messages" && method === "POST") return sendMessage(request, env, me, seg[1]);
  }
  if (seg[0] === "users") {
    if (seg[1] === "search" && seg.length === 2 && method === "GET") return searchUsers(env, me, url.searchParams.get("q") || "");
    if (seg.length === 2 && method === "GET") return getProfile(env, me, seg[1]);
  }
  if (seg[0] === "friends") {
    if (seg.length === 1 && method === "GET") return listFriends(env, me);
    if (seg.length === 1 && method === "POST") return requestFriend(request, env, me);
    if (seg.length === 2 && method === "POST") return answerFriend(request, env, me, seg[1]);
  }
  if (seg[0] === "blocks") {
    if (seg.length === 1 && method === "GET") return listBlocks(env, me);
    if (seg.length === 1 && method === "POST") return addBlock(request, env, me);
    if (seg.length === 2 && method === "DELETE") return removeBlock(env, me, seg[1]);
  }
  if (path === "/api/reports" && method === "POST") return addReport(request, env, me);
  if (path === "/api/admin/reports" && method === "GET") return adminReports(env, me);

  throw new HttpError(404, "not_found", "There is nothing at that address.");
}

// ----------------------------------------------------------------- helpers --

const q = (env, sql, ...args) => env.DB.prepare(sql).bind(...args);
const pair = (a, b) => (a < b ? [a, b] : [b, a]);

function hasProvider(env, name) {
  const P = name.toUpperCase();
  return !!(env[`${P}_CLIENT_ID`] && env[`${P}_CLIENT_SECRET`]);
}

function isAdmin(env, username) {
  return String(env.ADMIN_USERNAMES || "").toLowerCase().split(",").map(s => s.trim()).filter(Boolean)
    .includes(String(username).toLowerCase());
}

async function currentUser(request, env) {
  const token = parseCookies(request)[SESSION_COOKIE];
  if (!token) return null;
  const row = await q(env,
    `SELECT u.id, u.username, u.is_public, u.instagram, u.refs_url, s.expires_at
       FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?`, await sha256(token)).first();
  if (!row || row.expires_at < now()) return null;
  return row;
}

// Fixed-window counter. `key` already names the person and the action.
async function limit(env, key, windowSec, max) {
  const w = Math.floor(now() / windowSec);
  const row = await q(env,
    `INSERT INTO rate (k, w, n) VALUES (?1, ?2, 1)
       ON CONFLICT(k) DO UPDATE SET n = CASE WHEN rate.w = ?2 THEN rate.n + 1 ELSE 1 END, w = ?2
       RETURNING n`, key, w).first();
  if (row && row.n > max) throw new HttpError(429, "slow_down", "You are doing that too quickly. Try again in a little while.");
}

let cardIds = null;
async function knownCard(env, request, id) {
  if (!/^[a-z0-9][a-z0-9-]{1,80}$/.test(String(id))) return false;
  if (!cardIds) {
    const res = await env.ASSETS.fetch(new Request(new URL("/assets/cards-index.json", request ? request.url : "https://logpose.cards/")));
    if (!res.ok) throw new HttpError(503, "not_set_up", "The card list could not be loaded.");
    cardIds = new Set(Object.keys(await res.json()));
  }
  return cardIds.has(id);
}

async function userByName(env, username) {
  if (!/^[A-Za-z0-9_]{3,20}$/.test(String(username || ""))) return null;
  return q(env, `SELECT id, username, is_public, instagram, refs_url FROM users WHERE username = ?`, username).first();
}

async function areFriends(env, a, b) {
  const [lo, hi] = pair(a, b);
  return !!(await q(env, `SELECT 1 x FROM friendships WHERE user_lo = ? AND user_hi = ? AND status = 'accepted'`, lo, hi).first());
}

async function blockedEitherWay(env, a, b) {
  return !!(await q(env,
    `SELECT 1 x FROM blocks WHERE (blocker_id = ?1 AND blocked_id = ?2) OR (blocker_id = ?2 AND blocked_id = ?1)`, a, b).first());
}

const NO_BLOCK = (a, b) =>
  `NOT EXISTS (SELECT 1 FROM blocks b WHERE (b.blocker_id = ${a} AND b.blocked_id = ${b}) OR (b.blocker_id = ${b} AND b.blocked_id = ${a}))`;

// ------------------------------------------------------------------- auth --

function safeNext(v) {
  const s = String(v || "");
  return /^\/(?!\/)[A-Za-z0-9\-._~/?=&%#]*$/.test(s) && s.length < 300 ? s : "/account/";
}

async function authStart(request, env, url, name) {
  const p = PROVIDERS[name];
  if (!p || !hasProvider(env, name)) throw new HttpError(404, "not_set_up", "That sign-in method is not switched on.");
  const state = randomToken(24);
  const verifier = randomToken(48);
  const params = new URLSearchParams({
    client_id: env[`${name.toUpperCase()}_CLIENT_ID`],
    redirect_uri: `${url.origin}/api/auth/${name}/callback`,
    response_type: "code",
    scope: p.scope,
    state,
  });
  if (p.pkce) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    params.set("code_challenge", b64url(new Uint8Array(digest)));
    params.set("code_challenge_method", "S256");
  }
  const authUrl = env[`${name.toUpperCase()}_AUTH_URL`] || p.authUrl;   // override exists for the local test server only
  const value = [state, verifier, encodeURIComponent(safeNext(url.searchParams.get("next")))].join(".");
  return redirect(`${authUrl}?${params}`, [cookie(OAUTH_COOKIE, value, { maxAge: 600, path: "/api/auth" })]);
}

async function authCallback(request, env, url, name) {
  const p = PROVIDERS[name];
  if (!p || !hasProvider(env, name)) throw new HttpError(404, "not_set_up", "That sign-in method is not switched on.");
  const clear = cookie(OAUTH_COOKIE, "", { maxAge: 0, path: "/api/auth" });
  const [state, verifier, nextEnc] = String(parseCookies(request)[OAUTH_COOKIE] || "").split(".");
  const code = url.searchParams.get("code");
  if (!code || !state || url.searchParams.get("state") !== state) {
    return redirect("/account/?signin=failed", [clear]);
  }
  const doFetch = env.FETCH || fetch;
  const P = name.toUpperCase();
  const form = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    client_id: env[`${P}_CLIENT_ID`],
    client_secret: env[`${P}_CLIENT_SECRET`],
    redirect_uri: `${url.origin}/api/auth/${name}/callback`,
  });
  if (p.pkce) form.set("code_verifier", verifier);

  let providerId = "";
  try {
    const tokRes = await doFetch(p.tokenUrl, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded", accept: "application/json" },
      body: form.toString(),
    });
    const tok = await tokRes.json();
    if (!tokRes.ok) throw new Error("token exchange refused");
    if (name === "google") {
      // The ID token came straight from Google over TLS in exchange for our
      // client secret, so its payload can be read without re-checking the signature.
      const payload = JSON.parse(atob(String(tok.id_token).split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
      const issOk = payload.iss === "https://accounts.google.com" || payload.iss === "accounts.google.com";
      if (!issOk || payload.aud !== env.GOOGLE_CLIENT_ID || !payload.sub) throw new Error("unexpected id token");
      providerId = String(payload.sub);
    } else {
      const who = await doFetch(p.userUrl, { headers: { authorization: `Bearer ${tok.access_token}` } });
      const body = await who.json();
      if (!who.ok || !body.id) throw new Error("no discord id");
      providerId = String(body.id);
    }
  } catch (err) {
    console.error("sign-in failed", name, String(err));
    return redirect("/account/?signin=failed", [clear]);
  }

  const known = await q(env, `SELECT user_id FROM identities WHERE provider = ? AND provider_id = ?`, name, providerId).first();
  if (known) {
    const cookies = await startSession(env, known.user_id);
    let next = "/account/";
    try { next = safeNext(decodeURIComponent(nextEnc || "")); } catch { /* keep default */ }
    return redirect(next, [clear, ...cookies]);
  }
  // First time we have seen this identity: nothing is created until the person
  // picks a username, confirms their age and passes the captcha.
  const token = randomToken();
  await env.DB.batch([
    q(env, `DELETE FROM pending_signups WHERE expires_at < ?`, now()),
    q(env, `INSERT INTO pending_signups (token_hash, provider, provider_id, expires_at) VALUES (?, ?, ?, ?)`,
      await sha256(token), name, providerId, now() + 1800),
  ]);
  return redirect("/account/?signup=1", [clear, cookie(SIGNUP_COOKIE, token, { maxAge: 1800 })]);
}

async function startSession(env, userId) {
  const token = randomToken();
  const ttl = SESSION_DAYS * 86400;
  await env.DB.batch([
    q(env, `DELETE FROM sessions WHERE expires_at < ?`, now()),
    q(env, `INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)`,
      await sha256(token), userId, now(), now() + ttl),
  ]);
  return [cookie(SESSION_COOKIE, token, { maxAge: ttl }), cookie(MARKER_COOKIE, "1", { maxAge: ttl, httpOnly: false })];
}

async function pendingSignup(request, env) {
  const token = parseCookies(request)[SIGNUP_COOKIE];
  if (!token) return null;
  const row = await q(env, `SELECT token_hash, provider, provider_id, expires_at FROM pending_signups WHERE token_hash = ?`,
    await sha256(token)).first();
  return row && row.expires_at >= now() ? row : null;
}

async function verifyCaptcha(request, env, token) {
  if (!env.TURNSTILE_SECRET) throw new HttpError(503, "not_set_up", "Sign-up is not switched on yet.");
  if (!token || typeof token !== "string" || token.length > 4000) {
    throw new HttpError(400, "captcha", "Please complete the captcha.");
  }
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token });
  const ip = request.headers.get("cf-connecting-ip");
  if (ip) body.set("remoteip", ip);
  let ok = false;
  try {
    const res = await (env.FETCH || fetch)("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: body.toString(),
    });
    ok = !!(await res.json()).success;
  } catch { ok = false; }
  if (!ok) throw new HttpError(400, "captcha", "The captcha did not pass. Please try it again.");
}

async function signup(request, env) {
  const pending = await pendingSignup(request, env);
  if (!pending) throw new HttpError(400, "signup_expired", "That sign-up has expired. Please sign in again to restart it.");
  const body = await readJson(request);
  const username = cleanUsername(body.username);
  if (body.adult !== true) throw new HttpError(400, "adult", "Accounts are for people aged 18 or over.");
  if (body.terms !== true) throw new HttpError(400, "terms", "Please accept the terms to create an account.");
  await verifyCaptcha(request, env, body.captcha);

  let userId;
  try {
    const r = await q(env, `INSERT INTO users (username, is_public, created_at) VALUES (?, ?, ?)`,
      username, body.isPublic === true ? 1 : 0, now()).run();
    userId = r.meta.last_row_id;
  } catch {
    throw new HttpError(409, "username_taken", "That username is taken. Try another.");
  }
  try {
    await env.DB.batch([
      q(env, `INSERT INTO identities (provider, provider_id, user_id) VALUES (?, ?, ?)`, pending.provider, pending.provider_id, userId),
      q(env, `DELETE FROM pending_signups WHERE token_hash = ?`, pending.token_hash),
    ]);
  } catch {
    await q(env, `DELETE FROM users WHERE id = ?`, userId).run();
    throw new HttpError(409, "already_registered", "That sign-in already has an account. Please sign in.");
  }
  const cookies = await startSession(env, userId);
  return json({ ok: true, username }, 200, { "set-cookie": [...cookies, cookie(SIGNUP_COOKIE, "", { maxAge: 0 })] });
}

async function logout(request, env) {
  const token = parseCookies(request)[SESSION_COOKIE];
  if (token) await q(env, `DELETE FROM sessions WHERE token_hash = ?`, await sha256(token)).run();
  return json({ ok: true }, 200, { "set-cookie": [
    cookie(SESSION_COOKIE, "", { maxAge: 0 }), cookie(MARKER_COOKIE, "", { maxAge: 0, httpOnly: false }),
    cookie(SIGNUP_COOKIE, "", { maxAge: 0 }) ] });
}

// ---------------------------------------------------------------- account --

function publicUser(u) {
  return { username: u.username, isPublic: !!u.is_public, instagram: u.instagram || "", refsUrl: u.refs_url || "" };
}

async function getMe(request, env, me) {
  if (!me) {
    const pending = await pendingSignup(request, env);
    const headers = parseCookies(request)[MARKER_COOKIE]
      ? { "set-cookie": [cookie(MARKER_COOKIE, "", { maxAge: 0, httpOnly: false })] } : {};
    return json({ user: null, signupPending: !!pending }, 200, headers);
  }
  const [reqs, unread, friends] = await env.DB.batch([
    q(env, `SELECT COUNT(*) n FROM matches m JOIN users uo ON uo.id = m.owner_id
             WHERE ((m.wisher_id = ?1 AND m.wisher_status = 'pending' AND m.owner_status <> 'declined')
                 OR (m.owner_id = ?1 AND m.owner_status = 'pending' AND m.wisher_status <> 'declined'))
               AND uo.is_public = 1 AND ${NO_BLOCK("m.wisher_id", "m.owner_id")}`, me.id),
    q(env, `SELECT COUNT(*) n FROM messages mm JOIN chats c ON c.id = mm.chat_id
             WHERE (c.user_lo = ?1 OR c.user_hi = ?1) AND (mm.sender_id IS NULL OR mm.sender_id <> ?1)
               AND mm.id > COALESCE((SELECT last_read_id FROM chat_reads r WHERE r.chat_id = c.id AND r.user_id = ?1), 0)`, me.id),
    q(env, `SELECT COUNT(*) n FROM friendships WHERE (user_lo = ?1 OR user_hi = ?1) AND status = 'pending' AND requested_by <> ?1`, me.id),
  ]);
  return json({
    user: { ...publicUser(me), isAdmin: isAdmin(env, me.username) },
    counts: { requests: reqs.results[0].n, unread: unread.results[0].n, friendRequests: friends.results[0].n },
  });
}

async function patchMe(request, env, me) {
  const body = await readJson(request);
  await limit(env, `profile:${me.id}`, 3600, 60);
  const instagram = "instagram" in body ? cleanInstagram(body.instagram) : me.instagram;
  const refsUrl = "refsUrl" in body ? cleanRefsUrl(body.refsUrl) : me.refs_url;
  const isPublic = "isPublic" in body ? (body.isPublic === true ? 1 : 0) : me.is_public;
  await q(env, `UPDATE users SET instagram = ?, refs_url = ?, is_public = ? WHERE id = ?`, instagram, refsUrl, isPublic, me.id).run();
  if (isPublic && !me.is_public) {
    // Newly public: offer this collection to everyone already wishing for those cards.
    await q(env,
      `INSERT OR IGNORE INTO matches (wisher_id, owner_id, card_id, created_at, updated_at)
       SELECT w.user_id, ?1, w.card_id, ?2, ?2
         FROM wishlist w JOIN (SELECT DISTINCT card_id FROM collection WHERE user_id = ?1) c ON c.card_id = w.card_id
        WHERE w.user_id <> ?1 AND ${NO_BLOCK("w.user_id", "?1")} LIMIT 300`, me.id, now()).run();
  }
  if (!isPublic && me.is_public) {
    // Gone private: withdraw every request that is not already a two-way yes.
    await q(env, `DELETE FROM matches WHERE owner_id = ? AND NOT (wisher_status = 'accepted' AND owner_status = 'accepted')`, me.id).run();
  }
  return json({ ok: true, user: { username: me.username, isPublic: !!isPublic, instagram, refsUrl } });
}

async function deleteMe(request, env, me) {
  const body = await readJson(request);
  if (String(body.confirm || "").toLowerCase() !== me.username.toLowerCase()) {
    throw new HttpError(400, "confirm", "Type your username to confirm.");
  }
  const id = me.id;
  await env.DB.batch([
    q(env, `DELETE FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE user_lo = ?1 OR user_hi = ?1)`, id),
    q(env, `DELETE FROM chat_reads WHERE chat_id IN (SELECT id FROM chats WHERE user_lo = ?1 OR user_hi = ?1)`, id),
    q(env, `DELETE FROM chats WHERE user_lo = ?1 OR user_hi = ?1`, id),
    q(env, `DELETE FROM matches WHERE wisher_id = ?1 OR owner_id = ?1`, id),
    q(env, `DELETE FROM friendships WHERE user_lo = ?1 OR user_hi = ?1`, id),
    q(env, `DELETE FROM blocks WHERE blocker_id = ?1 OR blocked_id = ?1`, id),
    q(env, `DELETE FROM wishlist WHERE user_id = ?`, id),
    q(env, `DELETE FROM collection WHERE user_id = ?`, id),
    q(env, `UPDATE reports SET reporter_id = NULL WHERE reporter_id = ?`, id),
    q(env, `UPDATE reports SET reported_id = NULL WHERE reported_id = ?`, id),
    q(env, `DELETE FROM rate WHERE k LIKE ?`, `%:${id}`),
    q(env, `DELETE FROM sessions WHERE user_id = ?`, id),
    q(env, `DELETE FROM identities WHERE user_id = ?`, id),
    q(env, `DELETE FROM users WHERE id = ?`, id),
  ]);
  return json({ ok: true }, 200, { "set-cookie": [
    cookie(SESSION_COOKIE, "", { maxAge: 0 }), cookie(MARKER_COOKIE, "", { maxAge: 0, httpOnly: false }) ] });
}

// --------------------------------------------------- wishlist + collection --

async function listWishlist(env, me) {
  const r = await q(env, `SELECT card_id, created_at FROM wishlist WHERE user_id = ? ORDER BY created_at DESC, card_id`, me.id).all();
  return json({ items: r.results.map(x => ({ cardId: x.card_id, addedAt: x.created_at })) });
}

async function addWish(env, me, cardId) {
  if (!(await knownCard(env, null, cardId))) throw new HttpError(404, "unknown_card", "That card is not in the ledger.");
  await limit(env, `add:${me.id}`, 3600, 600);
  const count = await q(env, `SELECT COUNT(*) n FROM wishlist WHERE user_id = ?`, me.id).first();
  if (count.n >= MAX_WISHLIST) throw new HttpError(400, "full", "Your wishlist is full.");
  await q(env, `INSERT OR IGNORE INTO wishlist (user_id, card_id, created_at) VALUES (?, ?, ?)`, me.id, cardId, now()).run();
  // Offer a chat with public collectors who already own this card.
  await q(env,
    `INSERT OR IGNORE INTO matches (wisher_id, owner_id, card_id, created_at, updated_at)
     SELECT ?1, c.user_id, ?2, ?3, ?3
       FROM (SELECT DISTINCT user_id FROM collection WHERE card_id = ?2 AND user_id <> ?1) c
       JOIN users u ON u.id = c.user_id AND u.is_public = 1
      WHERE ${NO_BLOCK("?1", "c.user_id")} LIMIT 25`, me.id, cardId, now()).run();
  return json({ ok: true });
}

async function removeWish(env, me, cardId) {
  await env.DB.batch([
    q(env, `DELETE FROM wishlist WHERE user_id = ? AND card_id = ?`, me.id, cardId),
    q(env, `DELETE FROM matches WHERE wisher_id = ? AND card_id = ? AND NOT (wisher_status = 'accepted' AND owner_status = 'accepted')`, me.id, cardId),
  ]);
  return json({ ok: true });
}

const ownedOut = x => ({ id: x.id, cardId: x.card_id, grader: x.grader, grade: x.grade, addedAt: x.created_at });

async function listCollection(env, me) {
  const r = await q(env, `SELECT id, card_id, grader, grade, created_at FROM collection WHERE user_id = ? ORDER BY created_at DESC, id DESC`, me.id).all();
  return json({ items: r.results.map(ownedOut) });
}

async function addOwned(request, env, me) {
  const body = await readJson(request);
  const cardId = String(body.cardId || "");
  if (!(await knownCard(env, request, cardId))) throw new HttpError(404, "unknown_card", "That card is not in the ledger.");
  const g = cleanGrade(body.grader, body.grade);
  await limit(env, `add:${me.id}`, 3600, 600);
  const count = await q(env, `SELECT COUNT(*) n FROM collection WHERE user_id = ?`, me.id).first();
  if (count.n >= MAX_COLLECTION) throw new HttpError(400, "full", "Your collection is full.");
  const r = await q(env, `INSERT INTO collection (user_id, card_id, grader, grade, created_at) VALUES (?, ?, ?, ?, ?)`,
    me.id, cardId, g.grader, g.grade, now()).run();
  if (me.is_public) {
    await q(env,
      `INSERT OR IGNORE INTO matches (wisher_id, owner_id, card_id, created_at, updated_at)
       SELECT w.user_id, ?1, ?2, ?3, ?3 FROM wishlist w
        WHERE w.card_id = ?2 AND w.user_id <> ?1 AND ${NO_BLOCK("w.user_id", "?1")} LIMIT 25`, me.id, cardId, now()).run();
  }
  return json({ ok: true, item: { id: r.meta.last_row_id, cardId, grader: g.grader, grade: g.grade } });
}

async function editOwned(request, env, me, idRaw) {
  const body = await readJson(request);
  const g = cleanGrade(body.grader, body.grade);
  const r = await q(env, `UPDATE collection SET grader = ?, grade = ? WHERE id = ? AND user_id = ?`, g.grader, g.grade, Number(idRaw) || 0, me.id).run();
  if (!r.meta.changes) throw new HttpError(404, "not_found", "That entry is not in your collection.");
  return json({ ok: true });
}

async function removeOwned(env, me, idRaw) {
  const row = await q(env, `SELECT card_id FROM collection WHERE id = ? AND user_id = ?`, Number(idRaw) || 0, me.id).first();
  if (!row) throw new HttpError(404, "not_found", "That entry is not in your collection.");
  await q(env, `DELETE FROM collection WHERE id = ? AND user_id = ?`, Number(idRaw) || 0, me.id).run();
  const left = await q(env, `SELECT COUNT(*) n FROM collection WHERE user_id = ? AND card_id = ?`, me.id, row.card_id).first();
  if (!left.n) {
    await q(env, `DELETE FROM matches WHERE owner_id = ? AND card_id = ? AND NOT (wisher_status = 'accepted' AND owner_status = 'accepted')`, me.id, row.card_id).run();
  }
  return json({ ok: true });
}

async function cardStatus(env, me, cardId) {
  const [w, c] = await env.DB.batch([
    q(env, `SELECT 1 x FROM wishlist WHERE user_id = ? AND card_id = ?`, me.id, cardId),
    q(env, `SELECT id, card_id, grader, grade, created_at FROM collection WHERE user_id = ? AND card_id = ? ORDER BY id`, me.id, cardId),
  ]);
  return json({ wished: w.results.length > 0, owned: c.results.map(ownedOut) });
}

// ---------------------------------------------------------- chat requests --

async function listRequests(env, me) {
  const r = await q(env,
    `SELECT m.id, m.card_id, m.wisher_id, m.owner_id, m.wisher_status, m.owner_status, m.created_at,
            uw.username wname, uw.is_public wpub, uo.username oname, uo.is_public opub,
            (SELECT c.id FROM chats c WHERE c.user_lo = MIN(m.wisher_id, m.owner_id) AND c.user_hi = MAX(m.wisher_id, m.owner_id)) chat_id,
            (SELECT 1 FROM friendships f WHERE f.user_lo = MIN(m.wisher_id, m.owner_id) AND f.user_hi = MAX(m.wisher_id, m.owner_id) AND f.status = 'accepted') friends
       FROM matches m JOIN users uw ON uw.id = m.wisher_id JOIN users uo ON uo.id = m.owner_id
      WHERE (m.wisher_id = ?1 OR m.owner_id = ?1) AND ${NO_BLOCK("m.wisher_id", "m.owner_id")}
      ORDER BY m.updated_at DESC, m.id DESC LIMIT 300`, me.id).all();
  const items = [];
  for (const m of r.results) {
    const iAmWisher = m.wisher_id === me.id;
    const mine = iAmWisher ? m.wisher_status : m.owner_status;
    const theirs = iAmWisher ? m.owner_status : m.wisher_status;
    const connected = mine === "accepted" && theirs === "accepted";
    if (mine === "declined" || theirs === "declined") continue;   // a "no" from either side closes it quietly
    if (!connected && !m.opub) continue;                           // the owner has since gone private
    const otherPublic = iAmWisher ? !!m.opub : !!m.wpub;
    const showName = otherPublic || connected || !!m.friends;
    items.push({
      id: m.id, cardId: m.card_id, role: iAmWisher ? "wisher" : "owner",
      other: showName ? (iAmWisher ? m.oname : m.wname) : null,
      mine, theirs, connected, chatId: connected ? m.chat_id : null, createdAt: m.created_at,
    });
  }
  return json({ items });
}

async function answerRequest(request, env, me, idRaw) {
  const body = await readJson(request);
  const action = body.action;
  if (action !== "accept" && action !== "decline") throw new HttpError(400, "bad_action", "Choose accept or decline.");
  const m = await q(env, `SELECT m.*, uo.is_public opub FROM matches m JOIN users uo ON uo.id = m.owner_id WHERE m.id = ?`, Number(idRaw) || 0).first();
  if (!m || (m.wisher_id !== me.id && m.owner_id !== me.id)) throw new HttpError(404, "not_found", "That chat request no longer exists.");
  const iAmWisher = m.wisher_id === me.id;
  const otherId = iAmWisher ? m.owner_id : m.wisher_id;
  const theirs = iAmWisher ? m.owner_status : m.wisher_status;
  if (theirs === "declined" || await blockedEitherWay(env, me.id, otherId)) {
    throw new HttpError(404, "not_found", "That chat request no longer exists.");
  }
  const column = iAmWisher ? "wisher_status" : "owner_status";
  const status = action === "accept" ? "accepted" : "declined";
  await q(env, `UPDATE matches SET ${column} = ?, updated_at = ? WHERE id = ?`, status, now(), m.id).run();
  if (status !== "accepted" || theirs !== "accepted") return json({ ok: true, connected: false });

  // Both said yes: open (or reuse) the one chat between these two people.
  const [lo, hi] = pair(me.id, otherId);
  await q(env, `INSERT OR IGNORE INTO chats (user_lo, user_hi, created_at) VALUES (?, ?, ?)`, lo, hi, now()).run();
  const chat = await q(env, `SELECT id FROM chats WHERE user_lo = ? AND user_hi = ?`, lo, hi).first();
  await q(env, `INSERT INTO messages (chat_id, sender_id, kind, body, created_at) VALUES (?, NULL, 'connected', ?, ?)`, chat.id, m.card_id, now()).run();
  return json({ ok: true, connected: true, chatId: chat.id });
}

// ------------------------------------------------------------------- chat --

async function myChat(env, me, idRaw) {
  const c = await q(env, `SELECT id, user_lo, user_hi FROM chats WHERE id = ?`, Number(idRaw) || 0).first();
  if (!c || (c.user_lo !== me.id && c.user_hi !== me.id)) throw new HttpError(404, "not_found", "That chat does not exist.");
  c.otherId = c.user_lo === me.id ? c.user_hi : c.user_lo;
  return c;
}

async function listChats(env, me) {
  const r = await q(env,
    `SELECT c.id, u.username other,
            (SELECT body FROM messages x WHERE x.chat_id = c.id ORDER BY x.id DESC LIMIT 1) last_body,
            (SELECT kind FROM messages x WHERE x.chat_id = c.id ORDER BY x.id DESC LIMIT 1) last_kind,
            (SELECT created_at FROM messages x WHERE x.chat_id = c.id ORDER BY x.id DESC LIMIT 1) last_at,
            (SELECT COUNT(*) FROM messages mm WHERE mm.chat_id = c.id AND (mm.sender_id IS NULL OR mm.sender_id <> ?1)
                AND mm.id > COALESCE((SELECT last_read_id FROM chat_reads r WHERE r.chat_id = c.id AND r.user_id = ?1), 0)) unread,
            EXISTS (SELECT 1 FROM blocks b WHERE (b.blocker_id = c.user_lo AND b.blocked_id = c.user_hi)
                                              OR (b.blocker_id = c.user_hi AND b.blocked_id = c.user_lo)) blocked
       FROM chats c JOIN users u ON u.id = CASE WHEN c.user_lo = ?1 THEN c.user_hi ELSE c.user_lo END
      WHERE c.user_lo = ?1 OR c.user_hi = ?1
      ORDER BY last_at DESC, c.id DESC`, me.id).all();
  return json({ items: r.results.map(c => ({
    id: c.id, other: c.other, unread: c.unread, blocked: !!c.blocked,
    last: c.last_at ? { kind: c.last_kind, body: c.last_body, at: c.last_at } : null })) });
}

async function listMessages(env, me, idRaw, url) {
  const c = await myChat(env, me, idRaw);
  const after = Number(url.searchParams.get("after")) || 0;
  const [msgs, other, blocked] = await env.DB.batch([
    q(env, `SELECT id, sender_id, kind, body, created_at FROM messages WHERE chat_id = ? AND id > ? ORDER BY id LIMIT 500`, c.id, after),
    q(env, `SELECT username FROM users WHERE id = ?`, c.otherId),
    q(env, `SELECT blocker_id FROM blocks WHERE (blocker_id = ?1 AND blocked_id = ?2) OR (blocker_id = ?2 AND blocked_id = ?1)`, me.id, c.otherId),
  ]);
  const list = msgs.results;
  if (list.length) {
    await q(env,
      `INSERT INTO chat_reads (chat_id, user_id, last_read_id) VALUES (?1, ?2, ?3)
         ON CONFLICT(chat_id, user_id) DO UPDATE SET last_read_id = MAX(last_read_id, ?3)`, c.id, me.id, list[list.length - 1].id).run();
  }
  return json({
    other: other.results[0] ? other.results[0].username : null,
    blocked: blocked.results.length > 0,
    blockedByMe: blocked.results.some(b => b.blocker_id === me.id),
    messages: list.map(m => ({ id: m.id, kind: m.kind, mine: m.sender_id === me.id, body: m.body, at: m.created_at })),
  });
}

async function sendMessage(request, env, me, idRaw) {
  const c = await myChat(env, me, idRaw);
  const body = await readJson(request);
  const text = String(body.body ?? "").replace(/\r\n?/g, "\n").trim();
  if (!text) throw new HttpError(400, "empty", "Write a message first.");
  if (text.length > MAX_MESSAGE) throw new HttpError(400, "too_long", `Messages can be up to ${MAX_MESSAGE} characters.`);
  if (await blockedEitherWay(env, me.id, c.otherId)) throw new HttpError(403, "blocked", "You can no longer message each other.");
  await limit(env, `msg:${me.id}`, 60, 20);
  const r = await q(env, `INSERT INTO messages (chat_id, sender_id, kind, body, created_at) VALUES (?, ?, 'text', ?, ?)`, c.id, me.id, text, now()).run();
  await q(env,
    `INSERT INTO chat_reads (chat_id, user_id, last_read_id) VALUES (?1, ?2, ?3)
       ON CONFLICT(chat_id, user_id) DO UPDATE SET last_read_id = MAX(last_read_id, ?3)`, c.id, me.id, r.meta.last_row_id).run();
  return json({ ok: true, id: r.meta.last_row_id });
}

// ------------------------------------------------------ profiles + friends --

async function searchUsers(env, me, term) {
  const s = String(term).trim();
  if (!/^[A-Za-z0-9_]{2,20}$/.test(s)) return json({ items: [] });
  await limit(env, `search:${me.id}`, 60, 40);
  // Underscore is a LIKE wildcard, so escape it; usernames have no % or backslash.
  const r = await q(env,
    `SELECT u.username FROM users u
      WHERE u.is_public = 1 AND u.id <> ?1 AND u.username LIKE ?2 ESCAPE '\\' AND ${NO_BLOCK("u.id", "?1")}
      ORDER BY LENGTH(u.username), u.username LIMIT 20`, me.id, s.replace(/_/g, "\\_") + "%").all();
  return json({ items: r.results.map(u => ({ username: u.username })) });
}

async function getProfile(env, me, username) {
  const u = await userByName(env, username);
  const hidden = new HttpError(404, "not_found", "No public profile by that name.");
  if (!u) throw hidden;
  const self = u.id === me.id;
  if (!self && await blockedEitherWay(env, me.id, u.id)) throw hidden;
  const [lo, hi] = pair(me.id, u.id);
  const f = self ? null : await q(env, `SELECT requested_by, status FROM friendships WHERE user_lo = ? AND user_hi = ?`, lo, hi).first();
  const friends = !!f && f.status === "accepted";
  // A private account is visible only to its owner, its friends, and someone it has sent a friend request to.
  const invitedMe = !!f && f.status === "pending" && f.requested_by === u.id;
  if (!self && !u.is_public && !friends && !invitedMe) throw hidden;
  const relation = self ? "self" : friends ? "friends" : !f ? "none" : f.requested_by === me.id ? "requested" : "invited";
  const out = { ...publicUser(u), relation, wishlist: null, collection: null };
  if (self || u.is_public || friends) {
    const [w, c] = await env.DB.batch([
      q(env, `SELECT card_id FROM wishlist WHERE user_id = ? ORDER BY created_at DESC, card_id`, u.id),
      q(env, `SELECT card_id, grader, grade FROM collection WHERE user_id = ? ORDER BY created_at DESC, id DESC`, u.id),
    ]);
    out.wishlist = w.results.map(x => x.card_id);
    out.collection = c.results.map(x => ({ cardId: x.card_id, grader: x.grader, grade: x.grade }));
  } else {
    out.instagram = ""; out.refsUrl = "";
  }
  return json(out);
}

async function listFriends(env, me) {
  const r = await q(env,
    `SELECT u.username, f.status, f.requested_by FROM friendships f
       JOIN users u ON u.id = CASE WHEN f.user_lo = ?1 THEN f.user_hi ELSE f.user_lo END
      WHERE (f.user_lo = ?1 OR f.user_hi = ?1) AND ${NO_BLOCK("f.user_lo", "f.user_hi")}
      ORDER BY u.username`, me.id).all();
  const out = { friends: [], incoming: [], outgoing: [] };
  for (const f of r.results) {
    if (f.status === "accepted") out.friends.push({ username: f.username });
    else if (f.requested_by === me.id) out.outgoing.push({ username: f.username });
    else out.incoming.push({ username: f.username });
  }
  return json(out);
}

async function requestFriend(request, env, me) {
  const body = await readJson(request);
  const u = await userByName(env, body.username);
  const hidden = new HttpError(404, "not_found", "No public profile by that name.");
  if (!u || u.id === me.id || await blockedEitherWay(env, me.id, u.id)) throw hidden;
  const [lo, hi] = pair(me.id, u.id);
  const f = await q(env, `SELECT requested_by, status FROM friendships WHERE user_lo = ? AND user_hi = ?`, lo, hi).first();
  if (f) {
    if (f.status === "pending" && f.requested_by === u.id) {   // they already asked: this is a yes
      await q(env, `UPDATE friendships SET status = 'accepted' WHERE user_lo = ? AND user_hi = ?`, lo, hi).run();
      return json({ ok: true, relation: "friends" });
    }
    return json({ ok: true, relation: f.status === "accepted" ? "friends" : "requested" });
  }
  if (!u.is_public) throw hidden;   // private accounts can only be befriended when they ask first
  await limit(env, `friend:${me.id}`, 86400, 40);
  await q(env, `INSERT INTO friendships (user_lo, user_hi, requested_by, status, created_at) VALUES (?, ?, ?, 'pending', ?)`, lo, hi, me.id, now()).run();
  return json({ ok: true, relation: "requested" });
}

async function answerFriend(request, env, me, username) {
  const body = await readJson(request);
  const u = await userByName(env, username);
  if (!u || u.id === me.id) throw new HttpError(404, "not_found", "No friend request from that name.");
  const [lo, hi] = pair(me.id, u.id);
  const f = await q(env, `SELECT requested_by, status FROM friendships WHERE user_lo = ? AND user_hi = ?`, lo, hi).first();
  if (!f) throw new HttpError(404, "not_found", "No friend request from that name.");
  if (body.action === "accept") {
    if (f.status !== "pending" || f.requested_by === me.id) throw new HttpError(400, "bad_action", "There is no request from them to accept.");
    await q(env, `UPDATE friendships SET status = 'accepted' WHERE user_lo = ? AND user_hi = ?`, lo, hi).run();
    return json({ ok: true, relation: "friends" });
  }
  if (body.action === "decline" || body.action === "remove") {
    await q(env, `DELETE FROM friendships WHERE user_lo = ? AND user_hi = ?`, lo, hi).run();
    return json({ ok: true, relation: "none" });
  }
  throw new HttpError(400, "bad_action", "Choose accept, decline or remove.");
}

// -------------------------------------------------------- blocks + reports --

async function listBlocks(env, me) {
  const r = await q(env, `SELECT u.username FROM blocks b JOIN users u ON u.id = b.blocked_id WHERE b.blocker_id = ? ORDER BY u.username`, me.id).all();
  return json({ items: r.results.map(u => ({ username: u.username })) });
}

async function addBlock(request, env, me) {
  const body = await readJson(request);
  const u = await userByName(env, body.username);
  if (!u || u.id === me.id) throw new HttpError(404, "not_found", "No account by that name.");
  const [lo, hi] = pair(me.id, u.id);
  await env.DB.batch([
    q(env, `INSERT OR IGNORE INTO blocks (blocker_id, blocked_id, created_at) VALUES (?, ?, ?)`, me.id, u.id, now()),
    q(env, `DELETE FROM friendships WHERE user_lo = ? AND user_hi = ?`, lo, hi),
    q(env, `DELETE FROM matches WHERE ((wisher_id = ?1 AND owner_id = ?2) OR (wisher_id = ?2 AND owner_id = ?1))
              AND NOT (wisher_status = 'accepted' AND owner_status = 'accepted')`, me.id, u.id),
  ]);
  return json({ ok: true });
}

async function removeBlock(env, me, username) {
  const u = await userByName(env, username);
  if (u) await q(env, `DELETE FROM blocks WHERE blocker_id = ? AND blocked_id = ?`, me.id, u.id).run();
  return json({ ok: true });
}

async function addReport(request, env, me) {
  const body = await readJson(request);
  const u = await userByName(env, body.username);
  if (!u || u.id === me.id) throw new HttpError(404, "not_found", "No account by that name.");
  const reason = String(body.reason ?? "").trim().slice(0, 1000);
  if (reason.length < 5) throw new HttpError(400, "reason", "Say briefly what happened.");
  let chatId = null;
  if (body.chatId) {
    const c = await myChat(env, me, body.chatId);
    if (c.otherId !== u.id) throw new HttpError(400, "bad_chat", "That chat is not with this person.");
    chatId = c.id;
  }
  await limit(env, `report:${me.id}`, 86400, 20);
  await q(env, `INSERT INTO reports (reporter_id, reported_id, reported_name, chat_id, reason, created_at) VALUES (?, ?, ?, ?, ?, ?)`,
    me.id, u.id, u.username, chatId, reason, now()).run();
  return json({ ok: true });
}

// Reports are read by the site's keepers (usernames listed in ADMIN_USERNAMES).
// A report that names a chat includes that conversation, as the privacy page says.
async function adminReports(env, me) {
  if (!isAdmin(env, me.username)) throw new HttpError(404, "not_found", "There is nothing at that address.");
  const r = await q(env,
    `SELECT r.id, r.reason, r.created_at, r.chat_id, r.reported_name, ur.username reporter
       FROM reports r LEFT JOIN users ur ON ur.id = r.reporter_id
      WHERE r.resolved = 0 ORDER BY r.id DESC LIMIT 100`).all();
  const items = [];
  for (const rep of r.results) {
    let messages = [];
    if (rep.chat_id) {
      const m = await q(env,
        `SELECT m.kind, m.body, m.created_at, u.username sender FROM messages m LEFT JOIN users u ON u.id = m.sender_id
          WHERE m.chat_id = ? ORDER BY m.id DESC LIMIT 60`, rep.chat_id).all();
      messages = m.results.reverse().map(x => ({ kind: x.kind, sender: x.sender, body: x.body, at: x.created_at }));
    }
    items.push({ id: rep.id, reporter: rep.reporter, reported: rep.reported_name, reason: rep.reason, at: rep.created_at, messages });
  }
  return json({ items });
}
