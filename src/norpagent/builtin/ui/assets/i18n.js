/* ============================================================
   FarStars shared i18n core（2026-09-12）
   三端共通（主前端 front.html / 星轨控制台 norp-farstars.html / FLOW norp-flow.html）：

     - 统一语言集：zh_CN（简中）/ en（英文）
     - 统一存储键：np_lang（同源三端共享；任一页切换后，其余页重载即生效）
     - 统一接口：FarStarsI18N.get() / set(lang) / onChange(fn) / t(key) / register(dicts)
     - 兼容迁移：读取旧键（farstars_lang / norpflow.lang / np_lang）并统一写入 np_lang
     - 历史遗留：旧值 zh_TW / zh-HK / Hant 一律归一为 zh_CN（繁体已下线）

   页面用法（页面保留自己的词典结构，仅共用「语言状态 + 存储 + 切换事件」）：
     <script src="/assets/i18n.js"></script>
     var LANG = FarStarsI18N.get();
     FarStarsI18N.onChange(function (lang) { LANG = lang; renderAll(); });
     // 切换语言时调用：FarStarsI18N.set('en')  —— 自动持久化并广播
   ============================================================ */
(function () {
  "use strict";
  var LANGS = ["zh_CN", "en"];
  var STORAGE_KEY = "np_lang";

  function LS() {
    try { return window.localStorage; } catch (e) { return null; }
  }

  function norm(v) {
    v = String(v || "");
    /* 繁体 / 港澳（zh_TW / zh-HK / Hant）已下线：一律归一为简中，避免出现
       一个不再受支持的语言码。 */
    if (v === "zh_TW" || v === "zh-TW" || v === "zh_HK" || v === "zh-HK"
        || v === "zh-Hant" || v === "zh-Hant-TW") return "zh_CN";
    if (v === "zh_CN" || v === "zh" || v === "zh-CN" || v === "zh-Hans" || v === "zh_CN.UTF-8") return "zh_CN";
    if (v === "en" || v.indexOf("en-") === 0 || v.indexOf("en_") === 0) return "en";
    return "";
  }

  function detect() {
    var ls = LS();
    var saved = null;
    try { saved = ls && ls.getItem(STORAGE_KEY); } catch (e) { saved = null; }
    var s = norm(saved);
    if (s) return s;
    /* 兼容迁移：旧三端历史键读一次，统一并入 np_lang */
    try {
      var legacy = ls && (ls.getItem("farstars_lang") || ls.getItem("norpflow.lang"));
      var m = legacy === "zh" ? "zh_CN" : norm(legacy);
      if (m) {
        try { ls.setItem(STORAGE_KEY, m); } catch (e) {}
        return m;
      }
    } catch (e) {}
    var nav = String((typeof navigator !== "undefined" && navigator.language) || "").toLowerCase();
    if (nav.indexOf("zh") === 0) {
      return "zh_CN";
    }
    return "en";
  }

  var state = { lang: null, listeners: [], dicts: {} };

  function get() {
    if (!state.lang) state.lang = detect();
    return state.lang;
  }

  function set(lang) {
    var l = norm(lang) || "zh_CN";
    state.lang = l;
    try { var ls = LS(); if (ls) ls.setItem(STORAGE_KEY, l); } catch (e) {}
    try {
      document.documentElement.setAttribute(
        "lang", l === "zh_CN" ? "zh-CN" : "en");
    } catch (e) {}
    for (var i = 0; i < state.listeners.length; i++) {
      try { state.listeners[i](l); } catch (e) {}
    }
    try {
      window.dispatchEvent(new CustomEvent("farstars:lang", { detail: { lang: l } }));
    } catch (e) {}
    return l;
  }

  function onChange(fn) {
    if (typeof fn === "function") state.listeners.push(fn);
  }

  function register(dicts) {
    /* {zh_CN:{...}, en:{...}} 页面词典并入共享查询（后注册者覆盖同键） */
    if (!dicts || typeof dicts !== "object") return;
    for (var k in dicts) {
      if (!Object.prototype.hasOwnProperty.call(dicts, k)) continue;
      if (LANGS.indexOf(k) < 0) continue;
      var src = dicts[k] || {};
      var dst = state.dicts[k] || (state.dicts[k] = {});
      for (var key in src) {
        if (Object.prototype.hasOwnProperty.call(src, key)) dst[key] = src[key];
      }
    }
  }

  function t(key, fallback) {
    var lang = get();
    var d = state.dicts[lang] || {};
    var v = d[key];
    if (v === undefined) return fallback !== undefined ? fallback : key;
    return v;
  }

  window.FarStarsI18N = {
    LANGS: LANGS,
    STORAGE_KEY: STORAGE_KEY,
    get: get,
    set: set,
    onChange: onChange,
    register: register,
    t: t
  };
})();
