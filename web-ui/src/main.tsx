import React from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { ThemeProvider } from "./lib/theme";
import { MatrixRain } from "./components/MatrixRain";
import "./index.css";

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
