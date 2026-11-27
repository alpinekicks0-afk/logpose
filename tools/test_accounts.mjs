// End-to-end checks for the accounts API, run against the local test server.
//
//   node tools/test_accounts.mjs
//
// Covers sign-up rules (captcha, age, terms, usernames), privacy (private
// accounts, friends, blocks), the wishlist/collection match → chat request →
// chat flow, and the request checks that keep other sites from acting for you.

import assert from "node:assert/strict";
import { startServer } from "./dev_server.mjs";

const PORT = 8911;
const { server, env, origin } = await startServer(PORT);
let passed = 0;
const ok = (cond, label) => { assert.ok(cond, label); passed++; };
const eq = (a, b, label) => { assert.deepEqual(a, b, label); passed++; };

// A tiny browser: keeps cookies, follows redirects by hand.
class Client {
  constructor(name) { this.name = name; this.jar = new Map([["mock_user", name]]); }
  cookieHeader() { return [...this.jar].map(([k, v]) => `${k}=${v}`).join("; "); }
  absorb(res) {
    for (const c of res.headers.getSetCookie()) {
      const [kv, ...attrs] = c.split(";");
      const i = kv.indexOf("=");
      const k = kv.slice(0, i).trim(), v = kv.slice(i + 1).trim();
      if (attrs.some(a => /max-age=0/i.test(a)) || v === "") this.jar.delete(k); else this.jar.set(k, v);
    }
  }
  async raw(path, { method = "GET", body, headers = {} } = {}) {
    const h = { cookie: this.cookieHeader(), ...headers };
    if (body !== undefined) h["content-type"] = h["content-type"] || "application/json";
    const res = await fetch(path.startsWith("http") ? path : origin + path, {
      method, headers: h, body: body === undefined ? undefined : typeof body === "string" ? body : JSON.stringify(body), redirect: "manual" });
    this.absorb(res);
    return res;
  }
  async call(path, method = "GET", body) {
    const res = await this.raw(path, { method, body, headers: { "x-requested-with": "logpose" } });
    let data = {};
    try { data = await res.json(); } catch { /* empty */ }
    return { status: res.status, ...data };
  }
  async signIn(provider = "google") {
    let res = await this.raw(`/api/auth/${provider}/start`);
    for (let i = 0; i < 5 && res.status === 302; i++) res = await this.raw(res.headers.get("location"));
    return res;
  }
  async signUp(extra = {}) {
    await this.signIn(extra.provider);
    return this.call("/api/signup", "POST", { username: this.name, isPublic: true, adult: true, terms: true, captcha: "ok", ...extra, provider: undefined });
  }
}

const CARD_A = "luffy-st01-001-serial-2023", CARD_B = "borsalino-op02-114-2023", CARD_C = "kuzan-op02-096-2023";

try {
  // ---- signed out -------------------------------------------------------------
  const anon = new Client("nobody"); anon.jar.clear();
  eq((await anon.call("/api/config")).ready, true, "config says ready");
  eq((await anon.call("/api/me")).user, null, "signed-out /api/me has no user");
  eq((await anon.call("/api/wishlist")).status, 401, "wishlist needs sign-in");
  eq((await anon.call("/api/users/search?q=al")).status, 401, "search needs sign-in");
  eq((await anon.call("/api/users/alpine")).status, 401, "profiles need sign-in");

  // ---- sign-up rules -----------------------------------------------------------
  const alice = new Client("alice");
  await alice.signIn();
  eq((await alice.call("/api/me")).signupPending, true, "first sign-in waits for sign-up");
  ok(!alice.jar.has("lp_s"), "no session before sign-up is finished");
  const base = { username: "alice", isPublic: true, adult: true, terms: true, captcha: "ok" };
  eq((await alice.call("/api/signup", "POST", { ...base, captcha: "" })).error, "captcha", "captcha is required");
  eq((await alice.call("/api/signup", "POST", { ...base, captcha: "wrong" })).error, "captcha", "a failed captcha is refused");
  eq((await alice.call("/api/signup", "POST", { ...base, adult: false })).error, "adult", "must confirm 18+");
  eq((await alice.call("/api/signup", "POST", { ...base, terms: false })).error, "terms", "must accept terms");
  eq((await alice.call("/api/signup", "POST", { ...base, username: "a b" })).error, "bad_username", "bad username refused");
  eq((await alice.call("/api/signup", "POST", { ...base, username: "admin" })).error, "bad_username", "reserved username refused");
  eq((await alice.call("/api/me")).user, null, "failed attempts created no account");
  eq((await alice.call("/api/signup", "POST", base)).ok, true, "sign-up succeeds");
  ok(alice.jar.has("lp_s") && alice.jar.get("lp_in") === "1", "session + marker cookies set");
  const me = await alice.call("/api/me");
  eq([me.user.username, me.user.isPublic, me.user.isAdmin], ["alice", true, false], "profile after sign-up");

  // The same Google identity signs straight in next time; a different one cannot take the name.
  const alice2 = new Client("alice");
  await alice2.signIn();
  eq((await alice2.call("/api/me")).user.username, "alice", "returning sign-in needs no second sign-up");
  const thief = new Client("mallory");
  await thief.signIn();
  eq((await thief.call("/api/signup", "POST", { ...base, username: "ALICE" })).error, "username_taken", "usernames are unique, ignoring case");
  // Same person name on Discord is a different identity.
  const dAlice = new Client("alice");
  await dAlice.signIn("discord");
  eq((await dAlice.call("/api/me")).signupPending, true, "discord identity is separate from google");

  // ---- request forgery checks ----------------------------------------------------
  let res = await alice.raw("/api/wishlist/" + CARD_A, { method: "PUT" });
  eq(res.status, 403, "write without the custom header is refused");
  res = await alice.raw("/api/wishlist/" + CARD_A, { method: "PUT", headers: { "x-requested-with": "logpose", origin: "https://evil.example" } });
  eq(res.status, 403, "write from another origin is refused");
  res = await alice.raw("/api/logout", { method: "POST", body: "{}", headers: { "content-type": "text/plain", origin: "https://evil.example" } });
  eq(res.status, 403, "cross-site form post cannot sign you out");
  eq((await alice.call("/api/wishlist")).items.length, 0, "nothing was written by refused requests");
  // A sign-in callback with a made-up state does nothing.
  const forged = new Client("eve");
  res = await forged.raw("/api/auth/google/callback?code=mock-alice&state=guess");
  ok(res.headers.get("location").includes("signin=failed") && !forged.jar.has("lp_s") && !forged.jar.has("lp_signup"), "forged sign-in callback is rejected");
  // The return address after sign-in cannot point off-site.
  res = await new Client("x").raw("/api/auth/google/start?next=https://evil.example/");
  ok(!decodeURIComponent(res.headers.getSetCookie().join("")).includes("evil.example"), "off-site return address is dropped");

  // ---- profile fields --------------------------------------------------------------
  let r = await alice.call("/api/me", "PATCH", { instagram: "https://www.instagram.com/alpine.cards/", refsUrl: "https://example.com/refs?id=1" });
  eq([r.user.instagram, r.user.refsUrl], ["alpine.cards", "https://example.com/refs?id=1"], "instagram + refs saved");
  eq((await alice.call("/api/me", "PATCH", { refsUrl: "javascript:alert(1)" })).error, "bad_refs", "script links refused");
  eq((await alice.call("/api/me", "PATCH", { refsUrl: "http://example.com/" })).error, "bad_refs", "non-https links refused");
  eq((await alice.call("/api/me", "PATCH", { instagram: "<b>x</b>" })).error, "bad_instagram", "bad instagram refused");
  eq((await alice.call("/api/me")).user.instagram, "alpine.cards", "bad edits changed nothing");

  // ---- wishlist + collection ------------------------------------------------------------
  eq((await alice.call("/api/wishlist/not-a-card", "PUT")).error, "unknown_card", "unknown card refused");
  eq((await alice.call("/api/collection", "POST", { cardId: CARD_A, grader: "psa", grade: "11" })).error, "bad_grade", "PSA 11 refused");
  eq((await alice.call("/api/collection", "POST", { cardId: CARD_A, grader: "psa", grade: "9.5" })).error, "bad_grade", "PSA half grade refused");
  eq((await alice.call("/api/collection", "POST", { cardId: CARD_A, grader: "cgc", grade: "10" })).error, "bad_grade", "other graders refused");
  for (const [grader, grade] of [["raw", ""], ["psa", "10"], ["psa", "1"], ["bgs", "BL"], ["bgs", "9.5"], ["bgs", "10"], ["bgs", "1"]]) {
    eq((await alice.call("/api/collection", "POST", { cardId: CARD_A, grader, grade })).ok, true, `grade ${grader} ${grade} accepted`);
  }
  let col = (await alice.call("/api/collection")).items;
  eq(col.length, 7, "seven copies listed");
  eq((await alice.call("/api/collection/" + col[0].id, "PATCH", { grader: "psa", grade: "8" })).ok, true, "grade can be changed");
  eq((await alice.call("/api/card-status?card=" + CARD_A)).owned.length, 7, "card status shows owned copies");

  // ---- matching: wishlist meets a public collection -----------------------------------
  const bob = new Client("bob");
  eq((await bob.signUp({ isPublic: false })).ok, true, "bob signs up (private)");
  eq((await bob.call("/api/collection/" + col[0].id, "PATCH", { grader: "raw", grade: "" })).status, 404, "cannot edit someone else's collection entry");
  eq((await bob.call("/api/collection/" + col[0].id, "DELETE")).status, 404, "cannot delete someone else's collection entry");
  eq((await bob.call("/api/wishlist/" + CARD_A, "PUT")).ok, true, "bob wishes for a card alice owns");
  let aReq = (await alice.call("/api/requests")).items, bReq = (await bob.call("/api/requests")).items;
  eq([aReq.length, bReq.length], [1, 1], "both get exactly one chat request (7 copies, one request)");
  eq([aReq[0].cardId, aReq[0].role, aReq[0].other], [CARD_A, "owner", null], "owner sees the card; private wisher's name is hidden");
  eq([bReq[0].cardId, bReq[0].role, bReq[0].other], [CARD_A, "wisher", "alice"], "wisher sees the card and the public owner");
  eq([(await alice.call("/api/me")).counts.requests, (await bob.call("/api/me")).counts.requests], [1, 1], "both are notified");
  eq((await alice.call("/api/chats")).items.length, 0, "no chat before both accept");

  // A private owner produces no request at all.
  eq((await bob.call("/api/collection", "POST", { cardId: CARD_B, grader: "raw" })).ok, true, "private bob owns card B");
  eq((await alice.call("/api/wishlist/" + CARD_B, "PUT")).ok, true, "alice wishes for card B");
  eq((await alice.call("/api/requests")).items.length, 1, "no request for a private owner's card");
  eq((await bob.call("/api/requests")).items.length, 1, "private owner is not notified either");

  // A stranger cannot answer or see someone else's request.
  const carol = new Client("carol");
  await carol.signUp();
  eq((await carol.call("/api/requests/" + aReq[0].id, "POST", { action: "accept" })).status, 404, "outsider cannot answer a request");
  eq((await carol.call("/api/requests")).items.length, 0, "outsider sees no requests");

  // One accept is not enough.
  r = await bob.call("/api/requests/" + bReq[0].id, "POST", { action: "accept" });
  eq(r.connected, false, "one accept does not open a chat");
  eq((await bob.call("/api/chats")).items.length, 0, "still no chat");
  eq((await bob.call("/api/me")).counts.requests, 0, "bob's count clears after answering");
  r = await alice.call("/api/requests/" + aReq[0].id, "POST", { action: "accept" });
  ok(r.connected === true && r.chatId > 0, "second accept opens the chat");
  const chatId = r.chatId;
  eq((await alice.call("/api/requests")).items[0].other, "bob", "names are shown once connected");

  // ---- chat -------------------------------------------------------------------------------
  let msgs = await bob.call(`/api/chats/${chatId}/messages`);
  eq([msgs.other, msgs.messages.length, msgs.messages[0].kind, msgs.messages[0].body], ["alice", 1, "connected", CARD_A], "chat opens with the card it is about");
  eq((await bob.call(`/api/chats/${chatId}/messages`, "POST", { body: "  Hi, is the PSA 10 available?  " })).ok, true, "bob sends a message");
  eq((await alice.call("/api/me")).counts.unread, 2, "alice has two unread: the 'connected' notice and bob's message");
  msgs = await alice.call(`/api/chats/${chatId}/messages?after=${msgs.messages[0].id}`);
  eq([msgs.messages.length, msgs.messages[0].body, msgs.messages[0].mine], [1, "Hi, is the PSA 10 available?", false], "alice reads it (trimmed)");
  eq((await alice.call("/api/me")).counts.unread, 0, "reading clears unread");
  eq((await bob.call(`/api/chats/${chatId}/messages`, "POST", { body: "" })).error, "empty", "empty message refused");
  eq((await bob.call(`/api/chats/${chatId}/messages`, "POST", { body: "x".repeat(1001) })).error, "too_long", "overlong message refused");
  eq((await carol.call(`/api/chats/${chatId}/messages`)).status, 404, "outsider cannot read the chat");
  eq((await carol.call(`/api/chats/${chatId}/messages`, "POST", { body: "hello" })).status, 404, "outsider cannot post in the chat");
  eq((await anon.call(`/api/chats/${chatId}/messages`)).status, 401, "signed-out cannot read the chat");
  // HTML in a message is stored and returned as plain text (the page shows it with textContent).
  await alice.call(`/api/chats/${chatId}/messages`, "POST", { body: "<img src=x onerror=alert(1)>" });
  msgs = await bob.call(`/api/chats/${chatId}/messages`);
  eq(msgs.messages.at(-1).body, "<img src=x onerror=alert(1)>", "message text is returned verbatim as JSON");

  // A second card between the same two people reuses the one chat.
  await alice.call("/api/collection", "POST", { cardId: CARD_C, grader: "bgs", grade: "BL" });
  await bob.call("/api/wishlist/" + CARD_C, "PUT");
  const second = (await bob.call("/api/requests")).items.find(x => x.cardId === CARD_C);
  await bob.call("/api/requests/" + second.id, "POST", { action: "accept" });
  r = await alice.call("/api/requests/" + second.id, "POST", { action: "accept" });
  eq(r.chatId, chatId, "same pair, same chat");
  eq((await alice.call("/api/chats")).items.length, 1, "still one chat between them");
  msgs = await alice.call(`/api/chats/${chatId}/messages`);
  eq(msgs.messages.at(-1).body, CARD_C, "the chat notes the second card");

  // ---- declining -------------------------------------------------------------------------------
  const dave = new Client("dave");
  await dave.signUp();
  await dave.call("/api/wishlist/" + CARD_A, "PUT");
  const dReq = (await dave.call("/api/requests")).items[0];
  eq(dReq.other, "alice", "dave has a request about alice's card");
  eq((await alice.call("/api/requests/" + dReq.id, "POST", { action: "decline" })).connected, false, "alice declines");
  eq((await dave.call("/api/requests")).items.length, 0, "a declined request disappears for the other side");
  eq((await dave.call("/api/requests/" + dReq.id, "POST", { action: "accept" })).status, 404, "a declined request cannot be accepted");
  eq((await dave.call("/api/chats")).items.length, 0, "no chat after a decline");

  // ---- profiles, privacy and search ----------------------------------------------------------------
  eq((await carol.call("/api/users/search?q=al")).items.map(u => u.username), ["alice"], "public profile is found");
  eq((await carol.call("/api/users/search?q=bo")).items.length, 0, "private profile is not found");
  eq((await carol.call("/api/users/search?q=%25")).items.length, 0, "wildcards do not list everyone");
  eq((await carol.call("/api/users/search?q=__")).items.length, 0, "underscore is not a wildcard");
  let prof = await carol.call("/api/users/alice");
  eq([prof.username, prof.collection.length, prof.instagram, prof.relation], ["alice", 8, "alpine.cards", "none"], "public profile shows lists and links");
  eq((await carol.call("/api/users/bob")).status, 404, "private profile is hidden from strangers");
  eq((await carol.call("/api/friends", "POST", { username: "bob" })).status, 404, "cannot friend a private account from outside");
  // Friends see a private account.
  eq((await bob.call("/api/friends", "POST", { username: "carol" })).relation, "requested", "private bob asks carol");
  prof = await carol.call("/api/users/bob");
  eq([prof.relation, prof.wishlist, prof.collection], ["invited", null, null], "invited person sees the name but not the lists");
  eq((await carol.call("/api/me")).counts.friendRequests, 1, "carol is notified of the friend request");
  eq((await carol.call("/api/friends/bob", "POST", { action: "accept" })).relation, "friends", "carol accepts");
  prof = await carol.call("/api/users/bob");
  eq([prof.relation, prof.wishlist.length, prof.collection.length], ["friends", 2, 1], "friends see a private account's lists");
  eq((await bob.call("/api/friends/bob", "POST", { action: "accept" })).status, 404, "cannot friend yourself");
  eq((await alice.call("/api/friends", "POST", { username: "carol" })).relation, "requested", "alice asks carol");
  eq((await alice.call("/api/friends/carol", "POST", { action: "accept" })).error, "bad_action", "cannot accept your own request");
  eq((await carol.call("/api/friends", "POST", { username: "alice" })).relation, "friends", "asking back accepts");
  r = await carol.call("/api/friends");
  eq(r.friends.map(f => f.username), ["alice", "bob"], "friends list");
  eq((await carol.call("/api/friends/alice", "POST", { action: "remove" })).relation, "none", "unfriend");
  eq((await carol.call("/api/friends")).friends.map(f => f.username), ["bob"], "friend removed");

  // Going private withdraws open requests and hides the profile.
  const erin = new Client("erin");
  await erin.signUp();
  await erin.call("/api/collection", "POST", { cardId: CARD_B, grader: "psa", grade: "10" });
  eq((await alice.call("/api/requests")).items.filter(x => x.cardId === CARD_B).length, 1, "new public owner triggers a request for an existing wish");
  await erin.call("/api/me", "PATCH", { isPublic: false });
  eq((await alice.call("/api/requests")).items.filter(x => x.cardId === CARD_B).length, 0, "going private withdraws the request");
  eq((await alice.call("/api/users/erin")).status, 404, "and hides the profile");
  await erin.call("/api/me", "PATCH", { isPublic: true });
  eq((await alice.call("/api/requests")).items.filter(x => x.cardId === CARD_B).length, 1, "going public offers it again");

  // ---- blocks ---------------------------------------------------------------------------------------
  eq((await bob.call("/api/blocks", "POST", { username: "alice" })).ok, true, "bob blocks alice");
  eq((await alice.call(`/api/chats/${chatId}/messages`, "POST", { body: "hello?" })).error, "blocked", "blocked: alice cannot message");
  eq((await bob.call(`/api/chats/${chatId}/messages`, "POST", { body: "hello?" })).error, "blocked", "blocked: bob cannot message either");
  eq((await bob.call("/api/users/alice")).status, 404, "blocked profiles are hidden both ways");
  eq((await alice.call("/api/users/search?q=bo")).items.length, 0, "blocked accounts are not found");
  eq((await alice.call("/api/friends", "POST", { username: "bob" })).status, 404, "blocked accounts cannot be friended");
  await alice.call("/api/collection", "POST", { cardId: CARD_B, grader: "raw" });
  await bob.call("/api/wishlist/" + CARD_B, "PUT");
  const between = env.DB._raw.prepare(
    `SELECT COUNT(*) n FROM matches m JOIN users w ON w.id = m.wisher_id JOIN users o ON o.id = m.owner_id
      WHERE w.username = 'bob' AND o.username = 'alice' AND m.card_id = ?`).get(CARD_B);
  eq(Number(between.n), 0, "no new requests are created between blocked accounts");
  eq((await bob.call("/api/requests")).items.filter(x => x.cardId === CARD_B).map(x => x.other), ["erin"], "requests with other public owners still arrive");
  eq((await bob.call("/api/blocks")).items.map(u => u.username), ["alice"], "block list");
  eq((await bob.call("/api/blocks/alice", "DELETE")).ok, true, "unblock");
  eq((await alice.call(`/api/chats/${chatId}/messages`, "POST", { body: "back" })).ok, true, "messages work again after unblock");

  // ---- reports ---------------------------------------------------------------------------------------
  eq((await bob.call("/api/reports", "POST", { username: "alice", reason: "no" })).error, "reason", "a report needs a reason");
  eq((await carol.call("/api/reports", "POST", { username: "alice", reason: "spam messages", chatId })).status, 404, "cannot attach a chat you are not in");
  eq((await bob.call("/api/reports", "POST", { username: "alice", reason: "Asked me to pay outside.", chatId })).ok, true, "report with chat");
  eq((await bob.call("/api/admin/reports")).status, 404, "ordinary members cannot read reports");
  const admin = new Client("alpine");
  await admin.signUp();
  eq((await admin.call("/api/me")).user.isAdmin, true, "site keeper is recognised");
  r = await admin.call("/api/admin/reports");
  eq([r.items.length, r.items[0].reporter, r.items[0].reported, r.items[0].messages.length > 0], [1, "bob", "alice", true], "keeper reads the report and its chat");

  // ---- sign out + delete ---------------------------------------------------------------------------------
  const tokenBefore = alice2.jar.get("lp_s");
  eq((await alice2.call("/api/logout", "POST", {})).ok, true, "sign out");
  ok(!alice2.jar.has("lp_s") && !alice2.jar.has("lp_in"), "cookies cleared on sign out");
  const stale = new Client("alice"); stale.jar.set("lp_s", tokenBefore);
  eq((await stale.call("/api/me")).user, null, "a signed-out session token no longer works");
  eq((await alice.call("/api/me")).user.username, "alice", "other sessions stay signed in");

  eq((await bob.call("/api/me", "DELETE", { confirm: "nope" })).error, "confirm", "delete needs the username typed");
  eq((await bob.call("/api/me", "DELETE", { confirm: "bob" })).ok, true, "bob deletes his account");
  eq((await bob.call("/api/me")).user, null, "deleted account is signed out");
  eq((await alice.call("/api/chats")).items.length, 0, "the chat is gone for the other person too");
  eq((await carol.call("/api/friends")).friends.length, 0, "friendship removed");
  eq((await alice.call("/api/requests")).items.filter(x => x.other === "bob").length, 0, "requests removed");
  const left = env.DB._raw.prepare(
    `SELECT (SELECT COUNT(*) FROM users WHERE username='bob') + (SELECT COUNT(*) FROM identities WHERE provider_id='g-bob')
          + (SELECT COUNT(*) FROM messages WHERE body LIKE '%PSA 10 available%') n`).get();
  eq(Number(left.n), 0, "no rows about the deleted account remain");
  eq((await admin.call("/api/admin/reports")).items[0].reporter, null, "the report is kept without the deleted account's name");
  // The name is free again and the same Google identity starts from scratch.
  const bob2 = new Client("bob");
  eq((await bob2.signUp()).ok, true, "a deleted identity can sign up again");
  eq((await bob2.call("/api/wishlist")).items.length, 0, "and starts empty");

  // ---- rate limits ------------------------------------------------------------------------------------------
  const fast = new Client("speedy");
  await fast.signUp();
  await fast.call("/api/wishlist/" + CARD_A, "PUT");
  const fr = (await fast.call("/api/requests")).items[0];
  await fast.call("/api/requests/" + fr.id, "POST", { action: "accept" });
  r = await alice.call("/api/requests/" + fr.id, "POST", { action: "accept" });
  let last;
  for (let i = 0; i < 22; i++) last = await fast.call(`/api/chats/${r.chatId}/messages`, "POST", { body: "msg " + i });
  eq(last.status, 429, "message flood is slowed down");

  // ---- nothing personal is stored -------------------------------------------------------------------------------
  const cols = env.DB._raw.prepare(`SELECT name FROM pragma_table_info('users')`).all().map(x => x.name).sort();
  eq(cols, ["created_at", "id", "instagram", "is_public", "refs_url", "username"], "users table holds no email, name or IP");
  const sess = env.DB._raw.prepare(`SELECT token_hash FROM sessions`).all().map(x => x.token_hash);
  ok(!sess.includes(alice.jar.get("lp_s")), "session tokens are stored hashed, not as issued");

  // ---- switched off --------------------------------------------------------------------------------------------------
  const off = await startServer(PORT + 1, { DB: undefined });
  const cfg = await (await fetch(off.origin + "/api/config")).json();
  eq(cfg.ready, false, "without a database, config says not ready");
  const offMe = await fetch(off.origin + "/api/me");
  eq(offMe.status, 503, "and the API answers 'not switched on'");
  eq((await fetch(off.origin + "/")).status, 200, "while the site itself still loads");
  off.server.close();

  console.log(`\nAll ${passed} checks passed.`);
} catch (err) {
  console.error(`\nFAILED after ${passed} checks:\n`, err);
  process.exitCode = 1;
} finally {
  server.close();
}
