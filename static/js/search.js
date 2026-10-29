/* Keeper Knowledge Base - search box with typo-tolerant suggestions.
   Used on the home page. Talks to /search and /suggest. */
(function () {
  const input = document.getElementById("query");
  const btn = document.getElementById("btn");
  const resultsEl = document.getElementById("results");
  const suggestEl = document.getElementById("suggestions");
  if (!input) return;

  let suggestItems = [];
  let activeIndex = -1;
  let debounceTimer = null;

  input.addEventListener("input", () => {
    const q = input.value.trim();
    activeIndex = -1;
    clearTimeout(debounceTimer);
    if (q.length < 2) { closeSuggestions(); return; }
    debounceTimer = setTimeout(() => fetchSuggestions(q), 150);
  });

  input.addEventListener("keydown", (e) => {
    const open = suggestEl.classList.contains("open");
    if (open && e.key === "ArrowDown") {
      e.preventDefault();
      activeIndex = Math.min(activeIndex + 1, suggestItems.length - 1);
      renderSuggestions();
    } else if (open && e.key === "ArrowUp") {
      e.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      renderSuggestions();
    } else if (e.key === "Enter") {
      if (open && activeIndex >= 0) chooseSuggestion(activeIndex);
      else { closeSuggestions(); runSearch(); }
    } else if (e.key === "Escape") {
      closeSuggestions();
    }
  });

  btn.addEventListener("click", runSearch);
  document.addEventListener("click", (e) => {
    if (!suggestEl.contains(e.target) && e.target !== input) closeSuggestions();
  });

  async function fetchSuggestions(q) {
    try {
      const res = await fetch(`/suggest?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      suggestItems = data.suggestions || [];
      renderSuggestions();
    } catch (_) { closeSuggestions(); }
  }

  function renderSuggestions() {
    if (!suggestItems.length) { closeSuggestions(); return; }
    suggestEl.innerHTML = suggestItems.map((s, i) =>
      `<div class="suggestion${i === activeIndex ? " active" : ""}" data-i="${i}">${escapeHtml(s)}</div>`
    ).join("");
    suggestEl.classList.add("open");
    suggestEl.querySelectorAll(".suggestion").forEach(el => {
      el.addEventListener("mousedown", (e) => {
        e.preventDefault();
        chooseSuggestion(Number(el.dataset.i));
      });
    });
  }

  function chooseSuggestion(i) {
    if (i < 0 || i >= suggestItems.length) return;
    input.value = suggestItems[i];
    closeSuggestions();
    runSearch();
  }

  function closeSuggestions() {
    suggestEl.classList.remove("open");
    suggestEl.innerHTML = "";
    activeIndex = -1;
  }

  async function runSearch() {
    const query = input.value.trim();
    resultsEl.innerHTML = "";
    if (!query) {
      resultsEl.innerHTML = '<p class="msg error">Please enter a search query.</p>';
      return;
    }
    btn.disabled = true;
    btn.textContent = "Searching...";
    try {
      const res = await fetch("/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });
      const data = await res.json();
      if (!res.ok) {
        resultsEl.innerHTML = `<p class="msg error">${data.error || "Search failed."}</p>`;
        return;
      }
      if (!data.results || data.results.length === 0) {
        resultsEl.innerHTML =
          `<p class="msg">No sufficiently relevant articles were found.<br>` +
          `Try rewording, or <a href="/categories">browse all categories</a>.</p>`;
        return;
      }
      resultsEl.innerHTML = data.results.map(renderResult).join("");
    } catch (err) {
      resultsEl.innerHTML = `<p class="msg error">Could not reach the server.</p>`;
    } finally {
      btn.disabled = false;
      btn.textContent = "Search";
    }
  }

  function renderResult(r) {
    const pct = Math.round(r.score * 100);
    const link = r.article_url
      ? `<a class="read-link" href="${r.article_url}">Read detailed instructions &rarr;</a>`
      : "";
    return `
      <div class="result">
        <div class="meta">
          <span class="tag">${escapeHtml(r.category)}</span>
          <span class="score">relevance: ${pct}%</span>
        </div>
        <h3>${escapeHtml(r.title)}</h3>
        <div class="bar"><span style="width:${pct}%"></span></div>
        <p class="summary">${escapeHtml(shorten(r.content, 220))}</p>
        ${link}
      </div>`;
  }

  function shorten(s, n) {
    s = String(s);
    return s.length > n ? s.slice(0, n).trim() + "..." : s;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
})();
