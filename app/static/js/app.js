/* AdScope — vanilla JS interactions. No framework, no build step.
   Handles: theme toggle (persisted), the query-review editor (add / remove /
   select rows, using the server's field names), the website detail side panel,
   and submit loading states. Server-rendered; forms POST normally. */
(function () {
  "use strict";

  /* ---- Theme ------------------------------------------------------------ */
  var THEME_KEY = "adscope-theme";
  function effectiveTheme() {
    var cur = document.documentElement.getAttribute("data-theme");
    if (cur) return cur;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function applyTheme(t) {
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    document.querySelectorAll("[data-theme-label]").forEach(function (el) {
      el.textContent = effectiveTheme() === "dark" ? "Dark" : "Light";
    });
  }
  try { applyTheme(localStorage.getItem(THEME_KEY)); } catch (e) {}
  function toggleTheme() {
    var next = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, next); } catch (e) {}
  }

  /* ---- Side panel ------------------------------------------------------- */
  function openPanel(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.setAttribute("data-open", "true");
    document.body.style.overflow = "hidden";
    var f = el.querySelector("[data-autofocus], button, a, input");
    if (f) f.focus();
  }
  function closePanel(el) {
    if (typeof el === "string") el = document.getElementById(el);
    if (!el) el = document.querySelector('.scrim[data-open="true"]');
    if (!el) return;
    el.setAttribute("data-open", "false");
    document.body.style.overflow = "";
  }

  /* ---- Query editor ----------------------------------------------------- */
  function autosize(ta) {
    ta.style.height = "auto";
    ta.style.height = ta.scrollHeight + "px";
  }
  function updateCounts() {
    var rows = document.querySelectorAll(".qrow");
    var sel = document.querySelectorAll(".qrow input.checkbox:checked").length;
    var totalEl = document.querySelector("[data-count-total]");
    if (totalEl) totalEl.textContent = rows.length;
    document.querySelectorAll("[data-count-selected]").forEach(function (e) { e.textContent = sel; });
    document.querySelectorAll("[data-submit-selected]").forEach(function (b) {
      b.toggleAttribute("aria-disabled", sel === 0);
    });
  }
  function bindRow(li) {
    var cb = li.querySelector("input.checkbox");
    if (cb) cb.addEventListener("change", function () {
      li.classList.toggle("qrow--sel", cb.checked);
      updateCounts();
    });
    var rm = li.querySelector(".qrow__remove");
    if (rm) rm.addEventListener("click", function () {
      li.style.transition = "opacity .15s, transform .15s";
      li.style.opacity = "0"; li.style.transform = "translateX(8px)";
      setTimeout(function () { li.remove(); updateCounts(); }, 150);
    });
    var ta = li.querySelector(".qrow__input");
    if (ta) { autosize(ta); ta.addEventListener("input", function () { autosize(ta); }); }
  }
  function addRow(list) {
    var i = parseInt(list.getAttribute("data-next-index") || "0", 10);
    list.setAttribute("data-next-index", i + 1);
    var li = document.createElement("li");
    li.className = "qrow qrow--sel";
    li.innerHTML =
      '<label class="qrow__check"><input type="checkbox" class="checkbox" name="selected_' + i + '" checked aria-label="Select query"></label>' +
      '<div class="qrow__main">' +
        '<textarea class="qrow__input" name="text_' + i + '" rows="1" maxlength="500" placeholder="Type a custom query" aria-label="Audience query"></textarea>' +
        '<div class="qrow__meta"><span class="qrow__source qrow__source--custom">Custom</span></div>' +
        '<input type="hidden" name="source_' + i + '" value="">' +
        '<input type="hidden" name="custom_' + i + '" value="1">' +
      '</div>' +
      '<button type="button" class="btn btn--ghost btn--icon qrow__remove" aria-label="Remove query" title="Remove">' +
        '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16"><path d="M4 4l8 8M12 4l-8 8"/></svg>' +
      '</button>';
    list.appendChild(li);
    bindRow(li);
    updateCounts();
    var ta = li.querySelector(".qrow__input");
    if (ta) { autosize(ta); ta.focus(); }
  }

  /* ---- Campaign form: light client-side guard + loading ----------------- */
  function initCampaignForm() {
    var form = document.getElementById("campaign-form");
    if (!form) return;
    form.addEventListener("submit", function (e) {
      var brief = form.querySelector("#briefing");
      if (brief && brief.value.trim().length < 20) {
        e.preventDefault();
        brief.setCustomValidity("Please provide a briefing of at least 20 characters.");
        brief.reportValidity();
        return;
      }
      var btn = form.querySelector('[type="submit"]');
      if (btn) btn.classList.add("btn--is-loading");
    });
    var brief = form.querySelector("#briefing");
    if (brief) brief.addEventListener("input", function () { brief.setCustomValidity(""); });
  }

  /* ---- Init ------------------------------------------------------------- */
  document.addEventListener("DOMContentLoaded", function () {
    applyTheme(document.documentElement.getAttribute("data-theme"));

    document.querySelectorAll("[data-theme-toggle]").forEach(function (b) {
      b.addEventListener("click", toggleTheme);
    });

    document.querySelectorAll("[data-open-panel]").forEach(function (b) {
      b.addEventListener("click", function () { openPanel(b.getAttribute("data-open-panel")); });
    });
    document.querySelectorAll("[data-close-panel]").forEach(function (b) {
      b.addEventListener("click", function () { closePanel(b.closest(".scrim")); });
    });
    document.querySelectorAll(".scrim").forEach(function (s) {
      s.addEventListener("mousedown", function (e) { if (e.target === s) closePanel(s); });
    });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") closePanel(); });

    var list = document.getElementById("query-list");
    if (list) {
      list.querySelectorAll(".qrow").forEach(bindRow);
      updateCounts();
      var addBtn = document.querySelector("[data-add-query]");
      if (addBtn) addBtn.addEventListener("click", function () { addRow(list); });
      var selAll = document.querySelector("[data-select-all]");
      if (selAll) selAll.addEventListener("change", function () {
        list.querySelectorAll(".qrow").forEach(function (li) {
          var cb = li.querySelector("input.checkbox");
          if (cb) { cb.checked = selAll.checked; li.classList.toggle("qrow--sel", selAll.checked); }
        });
        updateCounts();
      });
      // Block submit when nothing is selected; show loading otherwise.
      document.querySelectorAll("[data-submit-selected]").forEach(function (b) {
        b.addEventListener("click", function (e) {
          if (b.getAttribute("aria-disabled") === "true") { e.preventDefault(); return; }
          b.classList.add("btn--is-loading");
        });
      });
    }

    initCampaignForm();
  });

  window.AdScope = { toggleTheme: toggleTheme, openPanel: openPanel, closePanel: closePanel };
})();
