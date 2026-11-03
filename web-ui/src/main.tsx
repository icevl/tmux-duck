import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ThemeProvider } from "./lib/theme";
import { MatrixRain } from "./components/MatrixRain";
import "./index.css";
import { applyTextSize, readTextSize } from "./lib/textSize";

// theme-boot.js sets it before paint too, but a cached older copy may not.
applyTextSize(readTextSize());

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root container missing");
}
createRoot(container).render(
  <React.StrictMode>
    <ThemeProvider>
      <MatrixRain />
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
