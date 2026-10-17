/* SportIQ Phase 2: offline lesson packs, offline-safe exam answers, webcam invigilation, shared-device privacy. */
(function () {
  "use strict";
  var OFFLINE_CACHE = "sportiq-offline-lessons";
  function csrf() { var m = document.cookie.match(/csrftoken=([^;]+)/); return m ? m[1] : ""; }

  // ---- Offline lesson packs: cache the lesson page + its audio/attachment/transcript -------------------
  function savedList() { try { return JSON.parse(localStorage.getItem("siq-offline") || "[]"); } catch (e) { return []; } }
  function setSaved(list) { try { localStorage.setItem("siq-offline", JSON.stringify(list)); } catch (e) {} }

  document.querySelectorAll("[data-offline-save]").forEach(function (btn) {
    var url = btn.dataset.offlineSave, title = btn.dataset.title, assets = (btn.dataset.assets || "").split("|").filter(Boolean);
    var isSaved = savedList().some(function (x) { return x.url === url; });
    if (isSaved) { btn.textContent = "Saved for offline ✓"; }
    if (!("caches" in window)) { btn.hidden = true; return; }
    btn.addEventListener("click", function () {
      btn.disabled = true; btn.textContent = "Saving…";
      caches.open(OFFLINE_CACHE).then(function (cache) {
        return cache.addAll([url].concat(assets));
      }).then(function () {
        var list = savedList().filter(function (x) { return x.url !== url; });
        list.push({ url: url, title: title, saved: new Date().toISOString().slice(0, 10) });
        setSaved(list); btn.textContent = "Saved for offline ✓";
      }).catch(function () { btn.disabled = false; btn.textContent = "Couldn't save. Try again"; });
    });
  });

  var listEl = document.getElementById("offline-list");
  if (listEl) {
    var items = savedList();
    listEl.innerHTML = items.length ? items.map(function (x) {
      return '<li><a class="grow" href="' + x.url + '">' + x.title.replace(/</g, "&lt;") + '</a><small class="muted">saved ' + x.saved + "</small></li>";
    }).join("") : '<li class="muted small">No lessons saved on this device.</li>';
  }

  // Shared-device privacy: wipe offline copies when logging out.
  document.querySelectorAll('form[action$="/account/logout/"]').forEach(function (f) {
    f.addEventListener("submit", function () {
      try { localStorage.removeItem("siq-offline"); localStorage.removeItem("siq-pending"); Object.keys(localStorage).forEach(function (k) { if (k.indexOf("siq-exam-") === 0) localStorage.removeItem(k); }); } catch (e) {}
      if ("caches" in window) caches.delete(OFFLINE_CACHE);
    });
  });

  // ---- Exam: keep answers locally if the connection drops; sync when it returns -------------------------
  var exam = document.querySelector("form[data-exam]");
  if (exam) {
    var key = "siq-exam-" + exam.dataset.autosave;
    function snapshotAnswers() {
      var fd = new FormData(exam), obj = {};
      fd.forEach(function (v, k) { if (k === "csrfmiddlewaretoken") return; (obj[k] = obj[k] || []).push(v); });
      return obj;
    }
    function restore() {
      var saved; try { saved = JSON.parse(localStorage.getItem(key) || "null"); } catch (e) { saved = null; }
      if (!saved) return;
      Object.keys(saved).forEach(function (name) {
        saved[name].forEach(function (val) {
          exam.querySelectorAll('[name="' + name + '"]').forEach(function (el) {
            if (el.type === "radio" || el.type === "checkbox") { if (el.value === val) el.checked = true; }
            else if (!el.value) el.value = val;
          });
        });
      });
    }
    function sync() {
      var saved; try { saved = localStorage.getItem(key); } catch (e) { return; }
      if (!saved || !navigator.onLine) return;
      var body = new URLSearchParams(); var obj = JSON.parse(saved);
      Object.keys(obj).forEach(function (k) { obj[k].forEach(function (v) { body.append(k, v); }); });
      body.append("_offline_sync", "1");
      fetch(exam.dataset.autosave, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": csrf() } })
        .then(function (r) { if (r.ok) { try { localStorage.removeItem(key); } catch (e) {} var b = document.getElementById("offline-banner"); if (b) b.hidden = true; } });
    }
    restore();
    exam.addEventListener("change", function () { try { localStorage.setItem(key, JSON.stringify(snapshotAnswers())); } catch (e) {} });
    exam.addEventListener("submit", function () { try { localStorage.removeItem(key); } catch (e) {} });
    window.addEventListener("offline", function () {
      var b = document.getElementById("offline-banner");
      if (!b) { b = document.createElement("div"); b.id = "offline-banner"; b.className = "alert alert-warning"; exam.prepend(b); }
      b.hidden = false; b.textContent = "You're offline. Keep going: your answers are saved on this device and will sync when you reconnect.";
    });
    window.addEventListener("online", sync);
    setInterval(sync, 30000);

    // ---- Webcam invigilation (only when the exam enables it and the learner did not choose an alternative) --
    if (exam.dataset.snapshot && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      var video = document.getElementById("cam");
      navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 }, audio: false }).then(function (stream) {
        video.srcObject = stream;
        function shoot() {
          var c = document.createElement("canvas"); c.width = 320; c.height = 240;
          c.getContext("2d").drawImage(video, 0, 0, 320, 240);
          var body = new URLSearchParams({ image: c.toDataURL("image/jpeg", 0.6) });
          fetch(exam.dataset.snapshot, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": csrf() } });
        }
        setTimeout(shoot, 5000); setInterval(shoot, 60000);
      }).catch(function () {
        fetch(exam.dataset.flag, { method: "POST", body: new URLSearchParams({ flag: "camera unavailable" }), credentials: "same-origin", headers: { "X-CSRFToken": csrf() } });
      });
    }
  }
})();
