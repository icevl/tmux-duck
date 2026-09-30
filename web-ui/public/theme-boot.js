// Apply the saved theme before first paint (see src/lib/theme.tsx).
(function () {
  var SCI_FI = ["matrix", "cyberpunk", "nostromo"];
  var RETRO = ["web1995"];
  var pref = "system";
  try {
    pref = localStorage.getItem("codi-theme") || "system";
  } catch (e) {}
  var sciFi = SCI_FI.indexOf(pref) !== -1;
  var retro = RETRO.indexOf(pref) !== -1;
  var dark =
    pref === "dark" ||
    sciFi ||
    (pref !== "light" &&
      !retro &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.classList.toggle("dark", dark);
  root.classList.toggle("sci-fi", sciFi);
  var variants = SCI_FI.concat(RETRO);
  for (var i = 0; i < variants.length; i++) {
    root.classList.toggle("theme-" + variants[i], pref === variants[i]);
  }
  root.style.colorScheme = dark ? "dark" : "light";
})();
