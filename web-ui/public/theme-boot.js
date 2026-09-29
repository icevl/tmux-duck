// Apply the saved theme before first paint (see src/lib/theme.tsx).
(function () {
  var pref = "system";
  try {
    pref = localStorage.getItem("codi-theme") || "system";
  } catch (e) {}
  var dark =
    pref === "dark" ||
    (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
})();
