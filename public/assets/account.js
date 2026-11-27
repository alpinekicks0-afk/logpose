/* Log Pose accounts: the small part that runs on every page.
   - Puts Wishlist / Collection buttons on card pages and on the card view in the app.
   - Shows a count on the Account link when something is waiting for you.
   Visitors who are not signed in never cause a request to the accounts API:
   the "lp_in" cookie is only a hint that a session exists (the session itself
   is in an HttpOnly cookie this script cannot read).
   Everything is wrapped so that a failure here can never break the page. */
(function () {
  "use strict";
  try {
    var signedIn = /(?:^|;\s*)lp_in=1(?:;|$)/.test(document.cookie);

    var css = ".lp-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:12px 0 4px;font:600 13px/1.2 system-ui,-apple-system,sans-serif}" +
      ".lp-actions:empty{display:none}" +
      ".lp-actions .lp-b{font:inherit;padding:7px 12px;border-radius:999px;border:1px solid #0b1f33;background:#0b1f33;color:#efe3c6;cursor:pointer;text-decoration:none;display:inline-block}" +
      ".lp-actions .lp-b.on{background:#d9a33a;border-color:#d9a33a;color:#1c1408}" +
      ".lp-actions .lp-b.ghost{background:transparent;color:#0b1f33}" +
      ".lp-actions .lp-b[disabled]{opacity:.55;cursor:default}" +
      ".lp-actions select{font:inherit;font-weight:400;padding:6px 8px;border-radius:8px;border:1px solid rgba(36,26,16,.4);background:#fffaf0;color:#241a10}" +
      ".lp-actions .lp-note{font-weight:400;color:#6b5a42;flex-basis:100%}" +
      ".lp-actions .lp-note a{color:inherit}" +
      ".lp-count{display:inline-block;min-width:17px;margin-left:6px;padding:1px 5px;border-radius:999px;background:#a5342b;color:#fff;font:700 11px/1.4 system-ui,sans-serif;text-align:center;vertical-align:1px}";
    var st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);

    function el(tag, cls, text) {
      var e = document.createElement(tag);
      if (cls) e.className = cls;
      if (text != null) e.textContent = text;
      return e;
    }
    function api(path, method, body) {
      var init = { method: method || "GET", credentials: "same-origin", headers: { "X-Requested-With": "logpose" } };
      if (body !== undefined) { init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body); }
      return fetch(path, init).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) { var e = new Error(data.message || "Something went wrong."); e.status = res.status; throw e; }
          return data;
        });
      });
    }
    function gradeLabel(g) {
      if (g.grader === "raw") return "Raw";
      if (g.grader === "psa") return "PSA " + g.grade;
      return g.grade === "BL" ? "BGS 10 Black Label" : "BGS " + g.grade;
    }
    function gradeSelect() {
      var sel = el("select"), g;
      sel.setAttribute("aria-label", "Grade");
      function opt(v, label) { var o = el("option", null, label); o.value = v; sel.appendChild(o); }
      opt("raw:", "Raw (ungraded)");
      for (g = 10; g >= 1; g--) opt("psa:" + g, "PSA " + g);
      opt("bgs:BL", "BGS 10 Black Label");
      for (g = 10; g >= 1; g -= 0.5) opt("bgs:" + g, "BGS " + g);
      return sel;
    }

    // ---- the buttons ---------------------------------------------------------
    function signedOutButtons(slot) {
      slot.textContent = "";
      var next = "/account/?next=" + encodeURIComponent(location.pathname);
      var w = el("a", "lp-b ghost", "♡ Wishlist"); w.href = next; w.title = "Sign in to add this card to your wishlist";
      var c = el("a", "lp-b ghost", "＋ Collection"); c.href = next; c.title = "Sign in to add this card to your collection";
      slot.appendChild(w); slot.appendChild(c);
    }

    function fill(slot, cardId) {
      if (!cardId || slot.getAttribute("data-done") === cardId) return;
      slot.setAttribute("data-done", cardId);
      if (!signedIn) return signedOutButtons(slot);
      api("/api/card-status?card=" + encodeURIComponent(cardId)).then(function (s) { draw(slot, cardId, s); })
        .catch(function (e) { if (e.status === 401) { signedIn = false; } signedOutButtons(slot); });
    }

    function draw(slot, cardId, s) {
      slot.textContent = "";
      var note = el("span", "lp-note");
      function fail(e) { note.textContent = e.message; }
      function reload() { return api("/api/card-status?card=" + encodeURIComponent(cardId)).then(function (n) { draw(slot, cardId, n); }); }

      var wish = el("button", "lp-b" + (s.wished ? " on" : ""), s.wished ? "♥ On your wishlist" : "♡ Add to wishlist");
      wish.type = "button";
      wish.title = s.wished ? "Remove from your wishlist" : "Add to your wishlist";
      wish.addEventListener("click", function () {
        wish.disabled = true;
        api("/api/wishlist/" + encodeURIComponent(cardId), s.wished ? "DELETE" : "PUT").then(reload).catch(function (e) { wish.disabled = false; fail(e); });
      });
      slot.appendChild(wish);

      var add = el("button", "lp-b" + (s.owned.length ? " on" : ""), s.owned.length ? "✓ In your collection" : "＋ Add to collection");
      add.type = "button";
      add.addEventListener("click", function () {
        add.hidden = true;
        var sel = gradeSelect();
        var ok = el("button", "lp-b", "Add"); ok.type = "button";
        var cancel = el("button", "lp-b ghost", "Cancel"); cancel.type = "button";
        cancel.addEventListener("click", function () { draw(slot, cardId, s); });
        ok.addEventListener("click", function () {
          var i = sel.value.indexOf(":");
          ok.disabled = true;
          api("/api/collection", "POST", { cardId: cardId, grader: sel.value.slice(0, i), grade: sel.value.slice(i + 1) })
            .then(reload).catch(function (e) { ok.disabled = false; fail(e); });
        });
        slot.insertBefore(cancel, note); slot.insertBefore(ok, cancel); slot.insertBefore(sel, ok);
      });
      slot.appendChild(add);
      slot.appendChild(note);
      if (s.owned.length) {
        note.appendChild(document.createTextNode("You own: " + s.owned.map(gradeLabel).join(", ") + ". Tap the button to add another copy, or "));
        var manage = el("a", null, "manage your collection"); manage.href = "/account/#collection";
        note.appendChild(manage);
        note.appendChild(document.createTextNode("."));
      }
    }

    // Static card pages carry an empty slot with the card id.
    Array.prototype.forEach.call(document.querySelectorAll(".lp-actions[data-card]"), function (slot) {
      fill(slot, slot.getAttribute("data-card"));
    });

    // The app draws a card into #ledger; add the slot each time it does.
    var ledger = document.getElementById("ledger");
    if (ledger && window.MutationObserver) {
      var currentCard = function () {
        try { if (typeof onCard !== "undefined" && onCard) return String(onCard); } catch (e) {}
        var h = history.state;
        return h && h.kind === "card" && h.id ? String(h.id) : "";
      };
      var check = function () {
        try {
          var detail = ledger.querySelector(".detail");
          if (!detail || detail.querySelector(".lp-actions")) return;
          var id = currentCard();
          if (!id) return;
          var slot = el("div", "lp-actions");
          var hero = detail.querySelector(".hero");
          if (hero && hero.parentNode === detail) detail.insertBefore(slot, hero); else detail.appendChild(slot);
          fill(slot, id);
        } catch (e) {}
      };
      new MutationObserver(check).observe(ledger, { childList: true });
      check();
    }

    // ---- "something is waiting" count on the Account link ----------------------
    if (signedIn) {
      var links = document.querySelectorAll("a.lp-acct");
      if (links.length) {
        var show = function (n) {
          if (!n) return;
          Array.prototype.forEach.call(links, function (a) { a.appendChild(el("span", "lp-count", String(n))); });
        };
        var cached = null;
        try { cached = JSON.parse(sessionStorage.getItem("lp-count") || "null"); } catch (e) {}
        if (cached && Date.now() - cached.t < 60000) show(cached.n);
        else api("/api/me").then(function (d) {
          var c = d.counts || {}, n = (c.requests || 0) + (c.unread || 0) + (c.friendRequests || 0);
          try { sessionStorage.setItem("lp-count", JSON.stringify({ t: Date.now(), n: n })); } catch (e) {}
          show(n);
        }).catch(function () {});
      }
    }
  } catch (e) { /* never let the account extras break a page */ }
})();
