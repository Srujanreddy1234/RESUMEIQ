// Loaded synchronously in <head> to apply the saved theme before first paint (no flash).
(function () {
  var pref = "dark";
  try { pref = localStorage.getItem("riq-theme") || "dark"; } catch (e) { /* storage blocked */ }
  var theme = pref === "system"
    ? (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
    : pref;
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.setAttribute("data-theme-pref", pref);
})();
