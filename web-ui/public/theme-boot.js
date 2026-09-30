// Apply the saved theme before first paint (see src/lib/theme.tsx).
(function () {
  var SCI_FI = ["matrix", "cyberpunk", "nostromo"];
  var pref = "system";
  try {
    pref = localStorage.getItem("codi-theme") || "system";
  } catch (e) {}
  var sciFi = SCI_FI.indexOf(pref) !== -1;
  var dark =
    pref === "dark" ||
    sciFi ||
    (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.classList.toggle("sci-fi", sciFi);
  for (var i = 0; i < SCI_FI.length; i++) {
    root.classList.toggle("theme-" + SCI_FI[i], pref === SCI_FI[i]);
  }
  root.style.colorScheme = dark ? "dark" : "light";
})();
