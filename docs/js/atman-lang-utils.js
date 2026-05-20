(function (global) {
  function detectLanguage(translations) {
    const urlLang = new URLSearchParams(global.location.search).get("lang");
    if (urlLang === "en" || urlLang === "ru") {
      return urlLang;
    }

    const savedLang = global.localStorage.getItem("atman-lang");
    if (savedLang && translations[savedLang]) {
      return savedLang;
    }

    const browserLang = global.navigator.language || global.navigator.userLanguage;
    if (browserLang.startsWith("ru")) {
      return "ru";
    }
    return "en";
  }

  function applyTranslations(lang, translations, options) {
    const opts = options || {};
    const t = translations[lang];
    if (!t) {
      return undefined;
    }

    document.documentElement.lang = lang;

    if (opts.meta) {
      document.querySelectorAll("[data-i18n-meta]").forEach((el) => {
        const key = el.dataset.i18nMeta;
        if (t.meta && t.meta[key]) {
          if (el.tagName === "TITLE") {
            el.textContent = t.meta[key];
          } else {
            el.setAttribute("content", t.meta[key]);
          }
        }
      });
    }

    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const key = el.dataset.i18n;
      const keys = key.split(".");
      let value = t;
      for (const k of keys) {
        value = value?.[k];
      }
      if (value) {
        el.textContent = value;
      }
    });

    if (opts.html) {
      document.querySelectorAll("[data-i18n-html]").forEach((el) => {
        const key = el.dataset.i18nHtml;
        const keys = key.split(".");
        let value = t;
        for (const k of keys) {
          value = value?.[k];
        }
        if (value) {
          el.innerHTML = value;
        }
      });
    }

    document.querySelectorAll(".lang-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.lang === lang);
    });

    global.localStorage.setItem("atman-lang", lang);
    syncAtmanLangInLinks(lang);
    return t;
  }

  function syncAtmanLangInLinks(lang) {
    document.querySelectorAll("a[href]").forEach((a) => {
      const raw = a.getAttribute("href");
      if (
        !raw ||
        raw.startsWith("http://") ||
        raw.startsWith("https://") ||
        raw.startsWith("mailto:") ||
        raw.startsWith("#")
      ) {
        return;
      }
      const hashIdx = raw.indexOf("#");
      const pathAndQuery = hashIdx >= 0 ? raw.slice(0, hashIdx) : raw;
      const hash = hashIdx >= 0 ? raw.slice(hashIdx) : "";
      if (
        !pathAndQuery.startsWith("document.html") &&
        !pathAndQuery.startsWith("demo.html") &&
        pathAndQuery !== "index.html" &&
        !pathAndQuery.startsWith("index.html?")
      ) {
        return;
      }
      const base = pathAndQuery || "index.html";
      const u = new URL(base, global.location.href);
      const file = u.pathname.split("/").pop() || "";
      if (file !== "document.html" && file !== "demo.html" && file !== "index.html") {
        return;
      }
      u.searchParams.set("lang", lang);
      a.setAttribute("href", file + u.search + hash);
    });
  }

  global.AtmanLang = {
    detectLanguage,
    applyTranslations,
    syncAtmanLangInLinks,
  };
})(globalThis);
