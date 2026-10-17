/* SportIQ front-end behaviours. No framework; progressive enhancement only. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  function csrf() {
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    var input = $('input[name="csrfmiddlewaretoken"]');
    return m ? m[1] : (input ? input.value : "");
  }
  window.siqPost = function (url, data) {
    var body = new URLSearchParams(data || {});
    return fetch(url, { method: "POST", body: body, credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" } });
  };

  // Lesson progress made offline (video position, "Mark complete") is queued on the device and sent when back online.
  var QUEUE = "siq-pending";
  function pending() { try { return JSON.parse(localStorage.getItem(QUEUE) || "[]"); } catch (e) { return []; } }
  function setPending(list) { try { localStorage.setItem(QUEUE, JSON.stringify(list)); } catch (e) {} }
  function enqueue(url, data) {
    setPending(pending().filter(function (x) { return x.url !== url; }).concat([{ url: url, data: data || {} }]));
  }
  window.siqSend = function (url, data) {
    if (!navigator.onLine) { enqueue(url, data); return Promise.resolve(null); }
    return siqPost(url, data).then(function (res) {
      if (!res.ok && res.status >= 500) enqueue(url, data);
      return res;
    }).catch(function () { enqueue(url, data); return null; });
  };
  function flush() {
    var list = pending();
    if (!list.length || !navigator.onLine) return;
    setPending([]);
    list.forEach(function (x) {
      siqPost(x.url, x.data).then(function (res) { if (!res.ok && res.status >= 500) enqueue(x.url, x.data); })
        .catch(function () { enqueue(x.url, x.data); });
    });
  }
  window.addEventListener("online", flush);
  flush();
  $$("form[data-offline-complete]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (navigator.onLine) return;
      e.preventDefault();
      enqueue(f.action, {});
      var note = document.createElement("p");
      note.className = "alert alert-info small mt-1";
      note.textContent = "You're offline. This lesson will be marked complete when you reconnect.";
      f.parentNode.insertBefore(note, f.nextSibling);
      f.querySelector("button").disabled = true;
      if (f.dataset.next) setTimeout(function () { location.href = f.dataset.next; }, 1200);
    });
  });

  // Drawers (public mobile menu, app side drawer)
  document.addEventListener("click", function (e) {
    var open = e.target.closest("[data-open]");
    if (open) { var el = document.getElementById(open.dataset.open); if (el) { el.classList.add("open"); document.body.style.overflow = "hidden"; } }
    var close = e.target.closest("[data-close]");
    if (close) { var c = document.getElementById(close.dataset.close); if (c) { c.classList.remove("open"); document.body.style.overflow = ""; } }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { $$(".drawer.open, .side-drawer.open").forEach(function (d) { d.classList.remove("open"); }); document.body.style.overflow = ""; }
  });
  // Mega-menu keyboard/touch toggle
  $$(".nav-drop > button").forEach(function (b) {
    b.addEventListener("click", function () {
      var p = b.parentElement, isOpen = p.classList.toggle("open");
      b.setAttribute("aria-expanded", isOpen);
      $$(".nav-drop").forEach(function (o) { if (o !== p) o.classList.remove("open"); });
    });
  });
  document.addEventListener("click", function (e) { if (!e.target.closest(".nav-drop")) $$(".nav-drop.open").forEach(function (o) { o.classList.remove("open"); }); });

  // Generic tabs: <div data-tabs><button data-tab="x"> … <div data-panel="x">
  $$("[data-tabs]").forEach(function (root) {
    var buttons = $$("[data-tab]", root);
    function show(name) {
      buttons.forEach(function (b) { b.setAttribute("aria-selected", b.dataset.tab === name ? "true" : "false"); });
      $$("[data-panel]", root).forEach(function (p) { p.classList.toggle("active", p.dataset.panel === name); });
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { show(b.dataset.tab); }); });
    if (buttons.length) show((buttons.filter(function (b) { return b.getAttribute("aria-selected") === "true"; })[0] || buttons[0]).dataset.tab);
  });

  // Theme toggle
  $$("[data-theme-toggle]").forEach(function (b) {
    b.addEventListener("click", function () {
      var root = document.documentElement;
      var dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try { localStorage.setItem("siq-theme", root.dataset.theme); } catch (e) {}
    });
  });

  // Animated counters on the landing page
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target, raw = el.dataset.count, num = parseFloat(raw.replace(/[^0-9.]/g, "")), suffix = raw.replace(/[0-9.,]/g, "");
        if (isNaN(num)) return;
        var start = null;
        function step(ts) { start = start || ts; var p = Math.min(1, (ts - start) / 1200);
          el.textContent = Math.round(num * p).toLocaleString() + suffix; if (p < 1) requestAnimationFrame(step); }
        requestAnimationFrame(step); io.unobserve(el);
      });
    });
    $$("[data-count]").forEach(function (el) { io.observe(el); });
  }

  // Lesson video: HLS, resume position, periodic progress save, speed control
  var video = $("video[data-progress-url]");
  if (video) {
    var hlsSrc = video.dataset.hls;
    if (hlsSrc && window.Hls && Hls.isSupported()) {
      var hls = new Hls({ capLevelToPlayerSize: true, startLevel: video.dataset.lowBandwidth ? 0 : -1 });
      hls.loadSource(hlsSrc); hls.attachMedia(video);
      var q = $("#quality");
      if (q) {
        hls.on(Hls.Events.MANIFEST_PARSED, function () {
          hls.levels.forEach(function (l, i) { var o = document.createElement("option"); o.value = i; o.textContent = l.height + "p"; q.appendChild(o); });
        });
        q.addEventListener("change", function () { hls.currentLevel = parseInt(q.value, 10); });
      }
    } else if (hlsSrc && video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = hlsSrc;
    }
    var resume = parseInt(video.dataset.resume || "0", 10);
    video.addEventListener("loadedmetadata", function () { if (resume > 5 && resume < video.duration - 5) video.currentTime = resume; });
    var last = 0;
    video.addEventListener("timeupdate", function () {
      var t = Math.floor(video.currentTime);
      if (Math.abs(t - last) >= 15) { last = t; siqSend(video.dataset.progressUrl, { position: t }); }
    });
    video.addEventListener("pause", function () { siqSend(video.dataset.progressUrl, { position: Math.floor(video.currentTime) }); });
    var speed = $("#speed");
    if (speed) speed.addEventListener("change", function () { video.playbackRate = parseFloat(speed.value); });
    $$("[data-seek]").forEach(function (a) { a.addEventListener("click", function (e) { e.preventDefault(); video.currentTime = parseInt(a.dataset.seek, 10); video.play(); }); });
    var noteAt = $("#note-at");
    if (noteAt) $("#note-form").addEventListener("submit", function () { noteAt.value = Math.floor(video.currentTime); });
  }

  // Exam: countdown, autosave every 20s, auto-submit at zero, tab-switch integrity flag
  var exam = $("form[data-exam]");
  if (exam) {
    var left = parseInt(exam.dataset.secondsLeft, 10), clock = $("#clock"), dirty = false, submitting = false;
    function fmt(s) { var m = Math.floor(s / 60), r = s % 60; return (m < 10 ? "0" : "") + m + ":" + (r < 10 ? "0" : "") + r; }
    function autosave() { if (!dirty) return; dirty = false; fetch(exam.dataset.autosave, { method: "POST", body: new FormData(exam), credentials: "same-origin", headers: { "X-Requested-With": "fetch" } }); }
    exam.addEventListener("change", function () { dirty = true; });
    exam.addEventListener("input", function () { dirty = true; });
    exam.addEventListener("submit", function () { submitting = true; });
    setInterval(autosave, 20000);
    var tick = setInterval(function () {
      left -= 1; if (clock) clock.textContent = fmt(Math.max(0, left));
      if (left === 60 && clock) clock.parentElement.style.background = "#9a6b00";
      if (left <= 0) { clearInterval(tick); submitting = true; exam.submit(); }
    }, 1000);
    if (clock) clock.textContent = fmt(left);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden && !submitting) siqPost(exam.dataset.flag, { flag: "left exam tab" });
    });
    window.addEventListener("beforeunload", function (e) { if (!submitting) { autosave(); e.preventDefault(); e.returnValue = ""; } });
  }

  // Confirm dangerous actions without native dialogs: two-step buttons
  $$("[data-confirm]").forEach(function (b) {
    b.addEventListener("click", function (e) {
      if (b.dataset.armed) return;
      e.preventDefault(); b.dataset.armed = "1"; var t = b.textContent; b.textContent = b.dataset.confirm;
      setTimeout(function () { delete b.dataset.armed; b.textContent = t; }, 4000);
    });
  });

  // Service worker (PWA shell caching)
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    window.addEventListener("load", function () { navigator.serviceWorker.register("/sw.js").catch(function () {}); });
  }
})();
