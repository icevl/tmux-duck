// Apply the saved theme before first paint (see src/lib/theme.tsx).
(function () {
  var pref = "system";
  try {
    pref = localStorage.getItem("codi-theme") || "system";
  } catch (e) {}
  var dark =
    pref === "dark" ||
    pref === "matrix" ||
    (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.classList.toggle("theme-matrix", pref === "matrix");
  root.style.colorScheme = dark ? "dark" : "light";
})();
