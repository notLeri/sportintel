import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";
import { App, initTelemetry } from "./app";
import { syncFavicon } from "@/shared/lib/theme";

// До рендера: ошибки первого рендера тоже должны попасть в Sentry.
initTelemetry();
void syncFavicon();

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
