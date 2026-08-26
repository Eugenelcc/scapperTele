/* Deal Hunter — Telegram Mini App frontend */
(function () {
  "use strict";

  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  if (tg) {
    tg.ready();
    tg.expand();
  }

  const initData = tg ? tg.initData : "";

  async function api(path, options) {
    options = options || {};
    const headers = Object.assign(
      { "Content-Type": "application/json", "X-Telegram-Init-Data": initData },
      options.headers || {}
    );
    const resp = await fetch(path, Object.assign({}, options, { headers }));
    let data = null;
    try { data = await resp.json(); } catch (e) { /* ignore */ }
    if (!resp.ok) {
      const msg = (data && (data.detail || data.error)) || ("HTTP " + resp.status);
      throw new Error(msg);
    }
    return data;
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function openListing(url) {
    if (tg && tg.openLink) tg.openLink(url);
    else window.open(url, "_blank");
  }

  function haptic(kind) {
    try { if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred(kind || "light"); }
    catch (e) { /* ignore */ }
  }

  function listingCard(l) {
    const card = document.createElement("div");
    card.className = "card";
    const img = l.image_url
      ? '<img src="' + esc(l.image_url) + '" loading="lazy" alt="" />'
      : "";
    const meta = [l.condition, l.location].filter(Boolean).map(esc).join(" · ");
    card.innerHTML =
      img +
      '<div class="body">' +
      '<div class="price">' + esc(l.price_str) + "</div>" +
      '<div class="title">' + esc(l.title) + "</div>" +
      (meta ? '<div class="meta">' + meta + "</div>" : "") +
      "</div>";
    card.addEventListener("click", function () { haptic(); openListing(l.url); });
    return card;
  }

  function renderCards(container, listings, emptyMsg) {
    container.innerHTML = "";
    if (!listings || !listings.length) {
      container.innerHTML = '<p class="empty">' + esc(emptyMsg || "Nothing found.") + "</p>";
      return;
    }
    listings.forEach(function (l) { container.appendChild(listingCard(l)); });
  }

  /* ---- Tabs ---- */
  document.querySelectorAll(".tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const name = btn.dataset.tab;
      document.querySelectorAll(".tab").forEach(function (b) { b.classList.toggle("active", b === btn); });
      document.querySelectorAll(".panel").forEach(function (p) {
        p.classList.toggle("active", p.id === name);
      });
      if (name === "watches") loadWatches();
    });
  });

  /* ---- Search ---- */
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");
  const dealsStatus = document.getElementById("deals-status");
  const dealsList = document.getElementById("deals-list");

  searchForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = searchInput.value.trim();
    if (!query) return;
    dealsStatus.textContent = "Searching…";
    dealsList.innerHTML = "";
    try {
      const data = await api("/api/search", {
        method: "POST",
        body: JSON.stringify({ query: query }),
      });
      dealsStatus.textContent = data.results.length + " result(s) for “" + query + "”";
      renderCards(dealsList, data.results, "No results right now.");
    } catch (err) {
      dealsStatus.textContent = "Error: " + err.message;
    }
  });

  /* ---- Watches ---- */
  const watchForm = document.getElementById("watch-form");
  const watchesStatus = document.getElementById("watches-status");
  const watchesList = document.getElementById("watches-list");
  const scanResults = document.getElementById("scan-results");

  async function loadWatches() {
    watchesStatus.textContent = "Loading…";
    try {
      const data = await api("/api/watches");
      watchesStatus.textContent = "";
      watchesList.innerHTML = "";

      if (data.builtin.length) {
        watchesList.appendChild(sectionLabel("Built-in"));
        data.builtin.forEach(function (w) { watchesList.appendChild(watchRow(w, false)); });
      }
      watchesList.appendChild(sectionLabel("Your watches"));
      if (data.user.length) {
        data.user.forEach(function (w) { watchesList.appendChild(watchRow(w, true)); });
      } else {
        const p = document.createElement("p");
        p.className = "empty";
        p.textContent = "None yet — add one above.";
        watchesList.appendChild(p);
      }
    } catch (err) {
      watchesStatus.textContent = "Error: " + err.message;
    }
  }

  function sectionLabel(text) {
    const d = document.createElement("div");
    d.className = "section-label";
    d.textContent = text;
    return d;
  }

  function watchRow(w, removable) {
    const row = document.createElement("div");
    row.className = "watch-item";
    row.innerHTML =
      '<div class="desc">' +
      (removable ? "" : '<div class="badge">built-in</div>') +
      esc(w.describe) +
      "</div>";
    if (removable) {
      const del = document.createElement("button");
      del.className = "del";
      del.textContent = "🗑️";
      del.title = "Remove";
      del.addEventListener("click", async function () {
        del.disabled = true;
        try {
          await api("/api/watches/" + w.id, { method: "DELETE" });
          haptic("medium");
          loadWatches();
        } catch (err) {
          watchesStatus.textContent = "Error: " + err.message;
          del.disabled = false;
        }
      });
      row.appendChild(del);
    }
    return row;
  }

  watchForm.addEventListener("submit", async function (e) {
    e.preventDefault();
    const query = document.getElementById("w-query").value.trim();
    if (!query) return;
    const priceRaw = document.getElementById("w-price").value.trim();
    const keywords = document.getElementById("w-keywords").value.trim();
    watchesStatus.textContent = "Saving…";
    try {
      await api("/api/watches", {
        method: "POST",
        body: JSON.stringify({
          query: query,
          max_price: priceRaw === "" ? null : Number(priceRaw),
          keywords: keywords,
        }),
      });
      haptic("medium");
      watchForm.reset();
      loadWatches();
    } catch (err) {
      watchesStatus.textContent = "Error: " + err.message;
    }
  });

  document.getElementById("scan-now").addEventListener("click", async function () {
    const btn = this;
    btn.disabled = true;
    watchesStatus.textContent = "Scanning all watches… (this can take a moment)";
    scanResults.innerHTML = "";
    try {
      const data = await api("/api/scan", { method: "POST" });
      if (!data.hits.length) {
        watchesStatus.textContent = "No new deals since the last scan. ✅";
      } else {
        let total = 0;
        data.hits.forEach(function (h) {
          scanResults.appendChild(sectionLabel("New for " + h.watch));
          const wrap = document.createElement("div");
          wrap.className = "cards";
          renderCards(wrap, h.results, "");
          scanResults.appendChild(wrap);
          total += h.results.length;
        });
        watchesStatus.textContent = total + " new deal(s) found 🎉";
      }
    } catch (err) {
      watchesStatus.textContent = "Error: " + err.message;
    } finally {
      btn.disabled = false;
    }
  });

  // Kick off on first load.
  searchInput.focus();
})();
