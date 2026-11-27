/* Log Pose account section (/account/).
   Everything a person types or another person wrote is put on the page with
   textContent, never as HTML. */
(function () {
  "use strict";
  var root = document.getElementById("lp-account");
  if (!root) return;

  var S = { config: null, me: null, counts: {}, signupPending: false, index: null, timer: null };
  var qs = new URLSearchParams(location.search);

  // ---- tiny helpers --------------------------------------------------------
  function h(tag, props) {
    var el = document.createElement(tag), i, k;
    props = props || {};
    for (k in props) {
      if (k === "class") el.className = props[k];
      else if (k === "text") el.textContent = props[k];
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), props[k]);
      else if (props[k] === true) el.setAttribute(k, "");
      else if (props[k] !== false && props[k] != null) el.setAttribute(k, props[k]);
    }
    for (i = 2; i < arguments.length; i++) {
      var c = arguments[i];
      if (c == null || c === false) continue;
      if (Array.isArray(c)) c.forEach(function (x) { if (x != null && x !== false) el.appendChild(typeof x === "string" ? document.createTextNode(x) : x); });
      else el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    }
    return el;
  }
  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", credentials: "same-origin", headers: { "X-Requested-With": "logpose" } };
    if (opts.body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(opts.body); }
    return fetch(path, init).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) { var e = new Error(data.message || "Something went wrong."); e.code = data.error; e.status = res.status; throw e; }
        return data;
      });
    });
  }
  function when(ts) {
    var d = new Date(ts * 1000), n = new Date();
    var sameDay = d.toDateString() === n.toDateString();
    return sameDay ? d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
      : d.toLocaleDateString([], { month: "short", day: "numeric" }) + ", " + d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }
  function gradeLabel(grader, grade) {
    if (grader === "raw") return "Raw (ungraded)";
    if (grader === "psa") return "PSA " + grade;
    return grade === "BL" ? "BGS 10 Black Label" : "BGS " + grade;
  }
  function gradeSelect(current) {
    var sel = h("select", { "aria-label": "Grade" }), g;
    function opt(v, label) { var o = h("option", { value: v, text: label }); if (v === current) o.selected = true; sel.appendChild(o); }
    opt("raw:", "Raw (ungraded)");
    for (g = 10; g >= 1; g--) opt("psa:" + g, "PSA " + g);
    opt("bgs:BL", "BGS 10 Black Label");
    for (g = 10; g >= 1; g -= 0.5) opt("bgs:" + g, "BGS " + g);
    return sel;
  }
  function splitGrade(v) { var i = v.indexOf(":"); return { grader: v.slice(0, i), grade: v.slice(i + 1) }; }
  function card(id) { return (S.index && S.index[id]) || { n: "Unknown card", no: id, p: "", i: "", s: "" }; }
  function cardImg(c) {
    return c.i ? h("img", { src: "/" + c.i, alt: c.n + " " + c.no, loading: "lazy" }) : h("div", { class: "noimg", text: "No image" });
  }
  function cardLink(c, cls) {
    return c.s ? h("a", { class: cls || "t", href: "/card/" + c.s + "/", text: c.n }) : h("span", { class: cls || "t", text: c.n });
  }
  function tile(id, extra) {
    var c = card(id);
    return h("div", { class: "lpa-card", "data-card": id }, cardImg(c), cardLink(c), h("div", { class: "m", text: c.no + (c.p ? " · " + c.p : "") }), extra);
  }
  function mini(id, lines) {
    var c = card(id);
    return h("div", { class: "lpa-mini" }, cardImg(c), h("div", { class: "tx" }, h("b", null, cardLink(c, "t")),
      h("span", { class: "muted", text: c.no + (c.p ? " · " + c.p : "") }), lines));
  }
  function flash(el, msg, cls) {
    var n = h("div", { class: cls || "error", role: "alert", text: msg });
    el.insertBefore(n, el.firstChild);
    setTimeout(function () { if (n.parentNode) n.parentNode.removeChild(n); }, 6000);
  }
  function busy(btn, promise) {
    btn.disabled = true;
    return promise.then(function (v) { btn.disabled = false; return v; }, function (e) { btn.disabled = false; throw e; });
  }
  function profileHref(name) { return "/account/?u=" + encodeURIComponent(name); }
  function stopTimer() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }

  // ---- start ---------------------------------------------------------------
  function start() {
    Promise.all([
      api("/api/config").catch(function () { return { ready: false, providers: {} }; }),
      fetch("/assets/cards-index.json").then(function (r) { return r.json(); }).catch(function () { return {}; }),
    ]).then(function (r) {
      S.config = r[0]; S.index = r[1];
      if (!S.config.ready) return renderOff();
      return refreshMe().then(route);
    }).catch(function () { renderOff(); });
    window.addEventListener("hashchange", route);
  }
  function refreshMe() {
    return api("/api/me").then(function (d) {
      S.me = d.user; S.counts = d.counts || {}; S.signupPending = !!d.signupPending;
    });
  }
  function renderOff() {
    clear(root).appendChild(h("div", null, h("h1", { text: "Accounts" }),
      h("p", { class: "note", text: "Accounts are not switched on yet. The rest of Log Pose works as usual." })));
  }

  function route() {
    stopTimer();
    if (!S.me) return S.signupPending ? renderSignup() : renderSignedOut();
    var viewing = qs.get("u");
    if (viewing && !location.hash) return renderProfile(viewing);
    var hash = (location.hash || "#wishlist").slice(1);
    var chat = /^chat\/(\d+)$/.exec(hash);
    var frame = shell(chat ? "chats" : hash);
    if (chat) return viewChat(frame, Number(chat[1]));
    var views = { wishlist: viewWishlist, collection: viewCollection, requests: viewRequests, chats: viewChats,
      friends: viewFriends, profile: viewSettings, reports: viewReports };
    (views[hash] || viewWishlist)(frame);
    refreshCounts();   // moving between tabs does not reload the page, so re-check what is waiting
  }

  function shell(active) {
    var tabs = [["wishlist", "Wishlist"], ["collection", "Collection"], ["requests", "Chat requests", S.counts.requests],
      ["chats", "Chats", S.counts.unread], ["friends", "Friends", S.counts.friendRequests], ["profile", "Profile"]];
    if (S.me.isAdmin) tabs.push(["reports", "Reports"]);
    var nav = h("nav", { class: "lpa-tabs", "aria-label": "Account sections" }, tabs.map(function (t) {
      return h("a", { href: "/account/#" + t[0], class: t[0] === active ? "on" : "", "data-tab": t[0] }, t[1],
        t[2] ? h("span", { class: "lpa-badge", text: String(t[2]) }) : null);
    }));
    var frame = h("div", { class: "lpa-view" });
    clear(root).appendChild(h("div", null,
      h("h1", { text: "Your account" }),
      h("p", { class: "muted" }, "Signed in as ", h("b", { text: S.me.username }), " · ",
        S.me.isPublic ? "public profile" : "private profile"),
      nav, frame));
    return frame;
  }

  // ---- signed out / sign up ------------------------------------------------
  function renderSignedOut() {
    // Came from a card's Wishlist / Collection button: go back to that page after signing in.
    var from = qs.get("next") || "";
    var next = /^\/(?!\/)[A-Za-z0-9\-._~\/]*$/.test(from) && from.length < 200 ? from : "/account/" + location.hash;
    var p = S.config.providers || {};
    var box = h("div", null, h("h1", { text: "Your account" }),
      h("p", null, "Sign in to keep a wishlist and a collection, and to be connected with collectors who own the cards you are looking for."));
    if (qs.get("signin") === "failed") box.appendChild(h("div", { class: "error", text: "That sign-in did not go through. Please try again." }));
    if (!p.google && !p.discord) {
      box.appendChild(h("p", { class: "note", text: "Sign-in is not switched on yet." }));
    } else {
      var row = h("div", { class: "lpa-row" });
      if (p.google) row.appendChild(h("a", { class: "lpa-btn", href: "/api/auth/google/start?next=" + encodeURIComponent(next), text: "Continue with Google" }));
      if (p.discord) row.appendChild(h("a", { class: "lpa-btn", href: "/api/auth/discord/start?next=" + encodeURIComponent(next), text: "Continue with Discord" }));
      box.appendChild(row);
      box.appendChild(h("p", { class: "muted" }, "Log Pose keeps only an anonymous ID from Google or Discord. It never sees your password and does not ask for your email. Accounts are for people aged 18 or over. See the ",
        h("a", { href: "/privacy/", text: "privacy page" }), "."));
    }
    clear(root).appendChild(box);
  }

  function renderSignup() {
    var captchaToken = S.config.turnstileSiteKey === "test-mode" ? "ok" : "";
    var name = h("input", { type: "text", id: "lpa-username", maxlength: "20", autocomplete: "off", autocapitalize: "off", spellcheck: "false" });
    var pub = h("input", { type: "radio", name: "vis", value: "public", id: "lpa-vis-public" });
    var priv = h("input", { type: "radio", name: "vis", value: "private", id: "lpa-vis-private", checked: true });
    var adult = h("input", { type: "checkbox", id: "lpa-adult" });
    var terms = h("input", { type: "checkbox", id: "lpa-terms" });
    var captcha = h("div", { id: "lpa-captcha" });
    var submit = h("button", { class: "lpa-btn", type: "submit", text: "Create account" });
    var form = h("form", { class: "lpa-form", novalidate: true },
      h("label", { for: "lpa-username", text: "Choose a username" }), name,
      h("p", { class: "hint", text: "3–20 letters, numbers or underscores. This is the name other collectors see." }),
      h("label", { text: "Who can see your account?" }),
      h("label", { class: "check", for: "lpa-vis-private" }, priv, h("span", null, h("b", { text: "Private. " }), "Only friends you accept can see your wishlist and collection. You cannot be found in search.")),
      h("label", { class: "check", for: "lpa-vis-public" }, pub, h("span", null, h("b", { text: "Public. " }), "Anyone signed in can find you and see your wishlist and collection, and collectors who want a card you own can send you a chat request.")),
      h("label", { class: "check", for: "lpa-adult" }, adult, h("span", { text: "I am 18 or older." })),
      h("label", { class: "check", for: "lpa-terms" }, terms, h("span", null, "I agree to the ", h("a", { href: "/terms/", target: "_blank", rel: "noopener", text: "terms" }), " and have read the ", h("a", { href: "/privacy/", target: "_blank", rel: "noopener", text: "privacy page" }), ".")),
      h("label", { text: "Confirm you are a real person" }), captcha,
      h("div", { class: "lpa-row", style: "margin-top:16px" }, submit));
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!captchaToken) return flash(form, "Please complete the captcha first.");
      busy(submit, api("/api/signup", { method: "POST", body: {
        username: name.value.trim(), isPublic: pub.checked, adult: adult.checked, terms: terms.checked, captcha: captchaToken } }))
        .then(function () { history.replaceState(null, "", "/account/"); qs = new URLSearchParams(""); return refreshMe(); })
        .then(route)
        .catch(function (e) {
          flash(form, e.message);
          if (e.code === "captcha" && window.turnstile) { try { window.turnstile.reset(); } catch (x) {} captchaToken = ""; }
          if (e.code === "signup_expired") { S.signupPending = false; }
        });
    });
    clear(root).appendChild(h("div", null, h("h1", { text: "Finish creating your account" }),
      h("p", { class: "muted", text: "One more step. Nothing is saved until you press Create account." }), form));

    if (S.config.turnstileSiteKey === "test-mode") {
      captcha.appendChild(h("p", { class: "muted", text: "Captcha (test mode)." }));
    } else if (!S.config.turnstileSiteKey) {
      captcha.appendChild(h("p", { class: "error", text: "The captcha is not switched on yet, so new accounts cannot be created." }));
      submit.disabled = true;
    } else {
      window.lpTurnstileReady = function () {
        window.turnstile.render(captcha, { sitekey: S.config.turnstileSiteKey,
          callback: function (t) { captchaToken = t; }, "expired-callback": function () { captchaToken = ""; } });
      };
      var sc = document.createElement("script");
      sc.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit&onload=lpTurnstileReady";
      sc.async = true;
      document.head.appendChild(sc);
    }
  }

  // ---- add-a-card search ---------------------------------------------------
  function cardSearch(placeholder, renderAction) {
    var input = h("input", { class: "lpa-input", type: "text", placeholder: placeholder, "aria-label": placeholder, autocomplete: "off" });
    var results = h("div", { class: "lpa-results", hidden: true });
    input.addEventListener("input", function () {
      var term = input.value.trim().toLowerCase();
      clear(results);
      if (term.length < 2) { results.hidden = true; return; }
      var found = [], id;
      for (id in S.index) {
        var c = S.index[id];
        if ((c.n + " " + c.no + " " + c.p).toLowerCase().indexOf(term) >= 0) { found.push(id); if (found.length >= 30) break; }
      }
      results.hidden = false;
      if (!found.length) { results.appendChild(h("div", { class: "r muted", text: "No card matches that." })); return; }
      found.forEach(function (cid) { results.appendChild(h("div", { class: "r", "data-card": cid }, mini(cid), renderAction(cid))); });
    });
    return h("div", { class: "lpa-search" }, input, results);
  }

  // ---- wishlist ------------------------------------------------------------
  function viewWishlist(frame) {
    var grid = h("div", { class: "lpa-grid" }), empty = h("p", { class: "muted" });
    function load() {
      return api("/api/wishlist").then(function (d) {
        clear(grid);
        empty.textContent = d.items.length ? "" : "Nothing on your wishlist yet. Search above, or use the Wishlist button on any card page.";
        d.items.forEach(function (it) {
          var rm = h("button", { class: "lpa-btn ghost small", type: "button", text: "Remove" });
          rm.addEventListener("click", function () {
            busy(rm, api("/api/wishlist/" + encodeURIComponent(it.cardId), { method: "DELETE" })).then(load).catch(function (e) { flash(frame, e.message); });
          });
          grid.appendChild(tile(it.cardId, rm));
        });
      });
    }
    var search = cardSearch("Add a card: search by name or number", function (cid) {
      var b = h("button", { class: "lpa-btn small", type: "button", text: "Add to wishlist" });
      b.addEventListener("click", function () {
        busy(b, api("/api/wishlist/" + encodeURIComponent(cid), { method: "PUT" })).then(function () { b.textContent = "Added"; b.disabled = true; return load(); })
          .then(refreshCounts).catch(function (e) { flash(frame, e.message); });
      });
      return b;
    });
    frame.appendChild(h("h2", { text: "Wishlist" }));
    frame.appendChild(h("p", { class: "muted", text: "Cards you are looking for. If a public collector owns one, you will both get a chat request." }));
    frame.appendChild(search); frame.appendChild(empty); frame.appendChild(grid);
    load().catch(function (e) { flash(frame, e.message); });
  }

  // ---- collection ----------------------------------------------------------
  function viewCollection(frame) {
    var grid = h("div", { class: "lpa-grid" }), empty = h("p", { class: "muted" });
    function load() {
      return api("/api/collection").then(function (d) {
        clear(grid);
        empty.textContent = d.items.length ? "" : "Nothing in your collection yet. Search above, or use the Collection button on any card page.";
        d.items.forEach(function (it) {
          var sel = gradeSelect(it.grader + ":" + it.grade);
          sel.addEventListener("change", function () {
            api("/api/collection/" + it.id, { method: "PATCH", body: splitGrade(sel.value) }).catch(function (e) { flash(frame, e.message); });
          });
          var rm = h("button", { class: "lpa-btn ghost small", type: "button", text: "Remove" });
          rm.addEventListener("click", function () {
            busy(rm, api("/api/collection/" + it.id, { method: "DELETE" })).then(load).catch(function (e) { flash(frame, e.message); });
          });
          grid.appendChild(tile(it.cardId, [sel, rm]));
        });
      });
    }
    var search = cardSearch("Add a card you own: search by name or number", function (cid) {
      var sel = gradeSelect("raw:");
      var b = h("button", { class: "lpa-btn small", type: "button", text: "Add" });
      b.addEventListener("click", function () {
        var g = splitGrade(sel.value);
        busy(b, api("/api/collection", { method: "POST", body: { cardId: cid, grader: g.grader, grade: g.grade } }))
          .then(function () { b.textContent = "Added"; return load(); }).then(refreshCounts).catch(function (e) { flash(frame, e.message); });
      });
      return h("div", { class: "lpa-row" }, sel, b);
    });
    frame.appendChild(h("h2", { text: "Collection" }));
    frame.appendChild(h("p", { class: "muted", text: S.me.isPublic
      ? "Cards you own, with their grade. Your profile is public, so collectors who want one of these can send you a chat request."
      : "Cards you own, with their grade. Your profile is private, so only your friends can see this." }));
    frame.appendChild(search); frame.appendChild(empty); frame.appendChild(grid);
    load().catch(function (e) { flash(frame, e.message); });
  }

  function refreshCounts() {
    return refreshMe().then(function () {
      var map = { requests: S.counts.requests, chats: S.counts.unread, friends: S.counts.friendRequests };
      Array.prototype.forEach.call(root.querySelectorAll(".lpa-tabs a"), function (a) {
        var n = map[a.getAttribute("data-tab")], badge = a.querySelector(".lpa-badge");
        if (badge) a.removeChild(badge);
        if (n) a.appendChild(h("span", { class: "lpa-badge", text: String(n) }));
      });
    }).catch(function () {});
  }

  // ---- chat requests -------------------------------------------------------
  function viewRequests(frame) {
    frame.appendChild(h("h2", { text: "Chat requests" }));
    frame.appendChild(h("p", { class: "muted", text: "When a card on someone's wishlist is in a public collector's collection, both get a request here. A chat opens only if both of you accept." }));
    var body = h("div"); frame.appendChild(body);
    function load() {
      return api("/api/requests").then(function (d) {
        clear(body);
        var groups = { todo: [], waiting: [], connected: [] };
        d.items.forEach(function (r) { (r.connected ? groups.connected : r.mine === "pending" ? groups.todo : groups.waiting).push(r); });
        if (!d.items.length) body.appendChild(h("p", { class: "muted", text: "No chat requests yet." }));
        section("Needs your answer", groups.todo, function (r) {
          var yes = h("button", { class: "lpa-btn small", type: "button", text: "Accept" });
          var no = h("button", { class: "lpa-btn ghost small", type: "button", text: "Decline" });
          function answer(btn, action) {
            busy(btn, api("/api/requests/" + r.id, { method: "POST", body: { action: action } })).then(function (res) {
              if (res.connected) { location.hash = "#chat/" + res.chatId; return; }
              return load().then(refreshCounts);
            }).catch(function (e) { flash(frame, e.message); });
          }
          yes.addEventListener("click", function () { answer(yes, "accept"); });
          no.addEventListener("click", function () { answer(no, "decline"); });
          return h("div", { class: "lpa-row" }, yes, no);
        });
        section("Waiting for them", groups.waiting, function () { return h("span", { class: "muted", text: "You accepted. Waiting for their answer." }); });
        section("Connected", groups.connected, function (r) { return h("a", { class: "lpa-btn small", href: "/account/#chat/" + r.chatId, text: "Open chat" }); });
      });
    }
    function section(title, items, action) {
      if (!items.length) return;
      body.appendChild(h("h3", { text: title }));
      body.appendChild(h("ul", { class: "lpa-list" }, items.map(function (r) {
        var who = r.other ? h("a", { href: profileHref(r.other), text: r.other }) : "A private collector";
        var line = r.role === "wisher"
          ? h("span", { class: "muted" }, who, " has this card in their collection. It is on your wishlist.")
          : h("span", { class: "muted" }, who, " has this card on their wishlist. It is in your collection.");
        return h("li", { "data-request": String(r.id) }, mini(r.cardId, h("div", null, line)), action(r));
      })));
    }
    load().catch(function (e) { flash(frame, e.message); });
  }

  // ---- chats ---------------------------------------------------------------
  function preview(last) {
    if (!last) return "";
    return last.kind === "connected" ? "Connected about " + card(last.body).n : last.body;
  }
  function viewChats(frame) {
    frame.appendChild(h("h2", { text: "Chats" }));
    api("/api/chats").then(function (d) {
      if (!d.items.length) { frame.appendChild(h("p", { class: "muted", text: "No chats yet. A chat opens when you and another collector both accept a chat request." })); return; }
      frame.appendChild(h("ul", { class: "lpa-list" }, d.items.map(function (c) {
        return h("li", null,
          h("div", null, h("a", { class: "who", href: "/account/#chat/" + c.id, text: c.other }),
            c.unread ? h("span", { class: "lpa-badge", text: String(c.unread) }) : null,
            h("div", { class: "muted", text: preview(c.last).slice(0, 90) })),
          h("span", { class: "muted", text: c.last ? when(c.last.at) : "" }));
      })));
    }).catch(function (e) { flash(frame, e.message); });
  }

  function viewChat(frame, id) {
    var log = h("div", { class: "lpa-chat", "aria-live": "polite" });
    var box = h("textarea", { maxlength: "1000", placeholder: "Write a message", "aria-label": "Message" });
    var send = h("button", { class: "lpa-btn", type: "submit", text: "Send" });
    var form = h("form", { class: "lpa-compose" }, box, send);
    var head = h("div", { class: "lpa-row", style: "justify-content:space-between" });
    var note = h("div");
    var lastId = 0, other = null;
    frame.appendChild(h("p", null, h("a", { href: "/account/#chats", text: "← All chats" })));
    frame.appendChild(head); frame.appendChild(note); frame.appendChild(log); frame.appendChild(form);
    frame.appendChild(h("p", { class: "muted", text: "Be careful with deals: Log Pose does not verify anyone, hold payments or guarantee trades. Check references before sending money or cards." }));

    function draw(d) {
      if (other === null) {
        other = d.other;
        head.appendChild(h("h2", { style: "margin:0;border:0" }, "Chat with ", h("a", { href: profileHref(other), text: other })));
        var block = h("button", { class: "lpa-btn ghost small", type: "button", text: d.blockedByMe ? "Unblock" : "Block" });
        block.addEventListener("click", function () {
          var p = block.textContent === "Block" ? api("/api/blocks", { method: "POST", body: { username: other } })
            : api("/api/blocks/" + encodeURIComponent(other), { method: "DELETE" });
          busy(block, p).then(route).catch(function (e) { flash(frame, e.message); });
        });
        var report = h("button", { class: "lpa-btn danger small", type: "button", text: "Report" });
        report.addEventListener("click", function () { reportForm(note, other, id); });
        head.appendChild(h("div", { class: "lpa-row" }, block, report));
      }
      if (d.blocked) { box.disabled = true; send.disabled = true; box.placeholder = "You can no longer message each other."; }
      d.messages.forEach(function (m) {
        lastId = Math.max(lastId, m.id);
        if (m.kind === "connected") {
          log.appendChild(h("div", { class: "lpa-msg sys" }, "You connected about ", cardLink(card(m.body), "t"), " (" + card(m.body).no + ")"));
        } else {
          log.appendChild(h("div", { class: "lpa-msg" + (m.mine ? " mine" : "") }, m.body, h("time", { text: when(m.at) })));
        }
      });
      if (d.messages.length) log.scrollTop = log.scrollHeight;
    }
    function poll() {
      return api("/api/chats/" + id + "/messages?after=" + lastId).then(draw);
    }
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var text = box.value.trim();
      if (!text) return;
      busy(send, api("/api/chats/" + id + "/messages", { method: "POST", body: { body: text } }))
        .then(function () { box.value = ""; return poll(); }).catch(function (e) { flash(frame, e.message); });
    });
    box.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
    });
    poll().then(function () { refreshCounts(); S.timer = setInterval(function () { if (!document.hidden) poll().catch(function () {}); }, 6000); })
      .catch(function (e) { clear(frame).appendChild(h("p", { class: "error", text: e.message })); });
  }

  function reportForm(where, username, chatId) {
    var reason = h("textarea", { maxlength: "1000", placeholder: "What happened?", "aria-label": "What happened?" });
    var send = h("button", { class: "lpa-btn danger small", type: "submit", text: "Send report" });
    var cancel = h("button", { class: "lpa-btn ghost small", type: "button", text: "Cancel" });
    var form = h("form", { class: "lpa-form note" },
      h("b", { text: "Report " + username }),
      h("p", { class: "hint", text: chatId ? "The people who keep Log Pose will be able to read this chat in order to look into your report." : "The people who keep Log Pose will review this." }),
      reason, h("div", { class: "lpa-row", style: "margin-top:8px" }, send, cancel));
    cancel.addEventListener("click", function () { clear(where); });
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var body = { username: username, reason: reason.value };
      if (chatId) body.chatId = chatId;
      busy(send, api("/api/reports", { method: "POST", body: body }))
        .then(function () { clear(where).appendChild(h("p", { class: "ok", text: "Report sent. Thank you." })); })
        .catch(function (e) { flash(form, e.message); });
    });
    clear(where).appendChild(form);
  }

  // ---- friends -------------------------------------------------------------
  function viewFriends(frame) {
    frame.appendChild(h("h2", { text: "Friends" }));
    frame.appendChild(h("p", { class: "muted", text: "Friends can see each other's wishlist and collection, even when a profile is private." }));
    var input = h("input", { class: "lpa-input", type: "text", placeholder: "Find a public profile by username", "aria-label": "Find a public profile by username", autocomplete: "off" });
    var results = h("div", { class: "lpa-results", hidden: true }), t = null;
    input.addEventListener("input", function () {
      clearTimeout(t);
      var term = input.value.trim();
      if (term.length < 2) { results.hidden = true; return; }
      t = setTimeout(function () {
        api("/api/users/search?q=" + encodeURIComponent(term)).then(function (d) {
          clear(results); results.hidden = false;
          if (!d.items.length) { results.appendChild(h("div", { class: "r muted", text: "No public profile starts with that." })); return; }
          d.items.forEach(function (u) {
            results.appendChild(h("div", { class: "r" }, h("a", { class: "who", href: profileHref(u.username), text: u.username }),
              h("a", { class: "lpa-btn ghost small", href: profileHref(u.username), text: "View profile" })));
          });
        }).catch(function (e) { flash(frame, e.message); });
      }, 250);
    });
    frame.appendChild(h("div", { class: "lpa-search" }, input, results));
    var body = h("div"); frame.appendChild(body);
    function act(btn, username, action) {
      busy(btn, api("/api/friends/" + encodeURIComponent(username), { method: "POST", body: { action: action } }))
        .then(load).then(refreshCounts).catch(function (e) { flash(frame, e.message); });
    }
    function list(title, items, buttons) {
      if (!items.length) return;
      body.appendChild(h("h3", { text: title }));
      body.appendChild(h("ul", { class: "lpa-list" }, items.map(function (u) {
        return h("li", null, h("a", { class: "who", href: profileHref(u.username), text: u.username }), h("div", { class: "lpa-row" }, buttons(u)));
      })));
    }
    function btn(label, cls, username, action) {
      var b = h("button", { class: "lpa-btn small " + cls, type: "button", text: label });
      b.addEventListener("click", function () { act(b, username, action); });
      return b;
    }
    function load() {
      return api("/api/friends").then(function (d) {
        clear(body);
        list("Friend requests", d.incoming, function (u) { return [btn("Accept", "", u.username, "accept"), btn("Decline", "ghost", u.username, "decline")]; });
        list("Your friends", d.friends, function (u) { return [h("a", { class: "lpa-btn ghost small", href: profileHref(u.username), text: "View" }), btn("Remove", "ghost", u.username, "remove")]; });
        list("Requests you sent", d.outgoing, function (u) { return [btn("Cancel", "ghost", u.username, "remove")]; });
        if (!d.incoming.length && !d.friends.length && !d.outgoing.length) body.appendChild(h("p", { class: "muted", text: "No friends yet. Search for a public profile above to send a request." }));
      });
    }
    load().catch(function (e) { flash(frame, e.message); });
  }

  // ---- another person's profile ---------------------------------------------
  function renderProfile(username) {
    var frame = h("div");
    clear(root).appendChild(h("div", null, h("p", null, h("a", { href: "/account/#friends", text: "← Your account" })), frame));
    api("/api/users/" + encodeURIComponent(username)).then(function (p) {
      var note = h("div");
      frame.appendChild(h("h1", { text: p.username }));
      frame.appendChild(h("p", { class: "muted", text: (p.isPublic ? "Public profile" : "Private profile") +
        (p.relation === "friends" ? " · your friend" : p.relation === "self" ? " · this is you" : "") }));
      var links = h("p", { class: "lpa-profile-links" });
      if (p.instagram) links.appendChild(h("a", { href: "https://www.instagram.com/" + encodeURIComponent(p.instagram) + "/", target: "_blank", rel: "noopener nofollow ugc", text: "Instagram: @" + p.instagram }));
      if (/^https:\/\//i.test(p.refsUrl || "")) links.appendChild(h("a", { href: p.refsUrl, target: "_blank", rel: "noopener nofollow ugc", text: "Refs (opens " + hostOf(p.refsUrl) + ")" }));
      if (links.firstChild) frame.appendChild(links);

      if (p.relation !== "self") {
        var row = h("div", { class: "lpa-row" });
        var label = { none: "Add friend", requested: "Request sent", invited: "Accept friend request", friends: "Remove friend" }[p.relation];
        var fb = h("button", { class: "lpa-btn small" + (p.relation === "friends" ? " ghost" : ""), type: "button", text: label });
        if (p.relation === "requested") fb.disabled = true;
        fb.addEventListener("click", function () {
          var call = p.relation === "friends" ? api("/api/friends/" + encodeURIComponent(p.username), { method: "POST", body: { action: "remove" } })
            : p.relation === "invited" ? api("/api/friends/" + encodeURIComponent(p.username), { method: "POST", body: { action: "accept" } })
            : api("/api/friends", { method: "POST", body: { username: p.username } });
          busy(fb, call).then(function () { renderProfile(p.username); }).catch(function (e) { flash(frame, e.message); });
        });
        var block = h("button", { class: "lpa-btn ghost small", type: "button", text: "Block" });
        block.addEventListener("click", function () {
          busy(block, api("/api/blocks", { method: "POST", body: { username: p.username } }))
            .then(function () { location.href = "/account/#friends"; }).catch(function (e) { flash(frame, e.message); });
        });
        var report = h("button", { class: "lpa-btn danger small", type: "button", text: "Report" });
        report.addEventListener("click", function () { reportForm(note, p.username, null); });
        row.appendChild(fb); row.appendChild(block); row.appendChild(report);
        frame.appendChild(row); frame.appendChild(note);
      }
      if (p.wishlist === null) {
        frame.appendChild(h("p", { class: "note", text: "This profile is private. Its wishlist and collection are visible to friends only." }));
        return;
      }
      frame.appendChild(h("h2", { text: "Collection (" + p.collection.length + ")" }));
      frame.appendChild(p.collection.length ? h("div", { class: "lpa-grid", id: "lpa-their-collection" }, p.collection.map(function (it) {
        return tile(it.cardId, h("div", { class: "g", text: gradeLabel(it.grader, it.grade) }));
      })) : h("p", { class: "muted", text: "Nothing listed." }));
      frame.appendChild(h("h2", { text: "Wishlist (" + p.wishlist.length + ")" }));
      frame.appendChild(p.wishlist.length ? h("div", { class: "lpa-grid", id: "lpa-their-wishlist" }, p.wishlist.map(function (cid) { return tile(cid); }))
        : h("p", { class: "muted", text: "Nothing listed." }));
    }).catch(function (e) {
      frame.appendChild(h("h1", { text: "Profile not found" }));
      frame.appendChild(h("p", { class: "note", text: e.message }));
    });
  }
  function hostOf(url) { try { return new URL(url).hostname.replace(/^www\./, ""); } catch (e) { return "link"; } }

  // ---- profile + settings ----------------------------------------------------
  function viewSettings(frame) {
    var ig = h("input", { type: "text", id: "lpa-ig", value: S.me.instagram, maxlength: "60", autocapitalize: "off", spellcheck: "false", placeholder: "alpine.cards" });
    var refs = h("input", { type: "url", id: "lpa-refs", value: S.me.refsUrl, maxlength: "300", placeholder: "https://…" });
    var pub = h("input", { type: "radio", name: "vis", id: "lpa-set-public", checked: S.me.isPublic });
    var priv = h("input", { type: "radio", name: "vis", id: "lpa-set-private", checked: !S.me.isPublic });
    var save = h("button", { class: "lpa-btn", type: "submit", text: "Save profile" });
    var saved = h("span", { class: "ok" });
    var form = h("form", { class: "lpa-form" },
      h("label", { text: "Username" }), h("p", { style: "margin:0" }, h("b", { text: S.me.username }), " ",
        h("a", { href: profileHref(S.me.username), text: "View your profile" })),
      h("label", { text: "Who can see your account?" }),
      h("label", { class: "check", for: "lpa-set-private" }, priv, h("span", null, h("b", { text: "Private. " }), "Only friends can see your wishlist and collection. You cannot be found in search, and nobody is sent a chat request about cards you own.")),
      h("label", { class: "check", for: "lpa-set-public" }, pub, h("span", null, h("b", { text: "Public. " }), "Anyone signed in can find you and see your wishlist, collection and links. Collectors who want a card you own get a chat request.")),
      h("label", { for: "lpa-ig", text: "Instagram" }), ig, h("p", { class: "hint", text: "Your username or profile link. Shown on your profile." }),
      h("label", { for: "lpa-refs", text: "Refs link" }), refs, h("p", { class: "hint", text: "A link to your references from past deals, starting with https://. Shown on your profile." }),
      h("div", { class: "lpa-row", style: "margin-top:16px" }, save, saved));
    form.addEventListener("submit", function (ev) {
      ev.preventDefault(); saved.textContent = "";
      busy(save, api("/api/me", { method: "PATCH", body: { instagram: ig.value, refsUrl: refs.value, isPublic: pub.checked } }))
        .then(function (d) { ig.value = d.user.instagram; refs.value = d.user.refsUrl; saved.textContent = "Saved."; return refreshMe(); })
        .then(function () { var p = root.querySelector("h1 + .muted"); if (p) { clear(p); p.appendChild(document.createTextNode("Signed in as ")); p.appendChild(h("b", { text: S.me.username })); p.appendChild(document.createTextNode(" · " + (S.me.isPublic ? "public profile" : "private profile"))); } refreshCounts(); })
        .catch(function (e) { flash(form, e.message); });
    });
    frame.appendChild(h("h2", { text: "Profile" })); frame.appendChild(form);

    var blocked = h("div"); frame.appendChild(blocked);
    api("/api/blocks").then(function (d) {
      if (!d.items.length) return;
      blocked.appendChild(h("h2", { text: "Blocked accounts" }));
      blocked.appendChild(h("ul", { class: "lpa-list" }, d.items.map(function (u) {
        var b = h("button", { class: "lpa-btn ghost small", type: "button", text: "Unblock" });
        b.addEventListener("click", function () { busy(b, api("/api/blocks/" + encodeURIComponent(u.username), { method: "DELETE" })).then(route).catch(function (e) { flash(frame, e.message); }); });
        return h("li", null, h("span", { class: "who", text: u.username }), b);
      })));
    }).catch(function () {});

    var out = h("button", { class: "lpa-btn ghost", type: "button", text: "Sign out" });
    out.addEventListener("click", function () { busy(out, api("/api/logout", { method: "POST", body: {} })).then(function () { location.href = "/account/"; }); });
    var confirmBox = h("input", { class: "lpa-input", type: "text", placeholder: "Type your username to confirm", "aria-label": "Type your username to confirm", autocomplete: "off" });
    var del = h("button", { class: "lpa-btn danger", type: "button", text: "Delete my account" });
    del.addEventListener("click", function () {
      busy(del, api("/api/me", { method: "DELETE", body: { confirm: confirmBox.value.trim() } }))
        .then(function () { location.href = "/account/"; }).catch(function (e) { flash(frame, e.message); });
    });
    frame.appendChild(h("h2", { text: "Sign out" })); frame.appendChild(out);
    frame.appendChild(h("h2", { text: "Delete account" }));
    frame.appendChild(h("p", { class: "muted", text: "This permanently deletes your profile, wishlist, collection, friends and chats. It cannot be undone." }));
    frame.appendChild(h("div", { class: "lpa-row" }, confirmBox, del));
  }

  // ---- reports (site keepers only) -------------------------------------------
  function viewReports(frame) {
    frame.appendChild(h("h2", { text: "Reports" }));
    api("/api/admin/reports").then(function (d) {
      if (!d.items.length) { frame.appendChild(h("p", { class: "muted", text: "No open reports." })); return; }
      d.items.forEach(function (r) {
        var box = h("div", { class: "note" },
          h("p", null, h("b", { text: (r.reporter || "deleted account") + " reported " + r.reported }), " · " + when(r.at)),
          h("p", { text: r.reason }));
        if (r.messages.length) {
          box.appendChild(h("div", { class: "lpa-chat" }, r.messages.map(function (m) {
            return m.kind === "connected" ? h("div", { class: "lpa-msg sys", text: "Connected about " + card(m.body).n })
              : h("div", { class: "lpa-msg" }, h("b", { text: (m.sender || "deleted") + ": " }), m.body, h("time", { text: when(m.at) }));
          })));
        }
        frame.appendChild(box);
      });
    }).catch(function (e) { flash(frame, e.message); });
  }

  start();
})();
