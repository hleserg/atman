(function () {
  try {
    var q = new URLSearchParams(globalThis.location.search);
    var u = q.get("lang");
    var s = globalThis.localStorage.getItem("atman-lang");
    var L;
    if (u === "en" || u === "ru") {
      L = u;
    } else if (s === "en" || s === "ru") {
      L = s;
    } else if ((globalThis.navigator.language || "").toLowerCase().startsWith("ru")) {
      L = "ru";
    } else {
      L = "en";
    }
    globalThis.document.documentElement.lang = L;
  } catch (e) {
    void e;
  }
})();
