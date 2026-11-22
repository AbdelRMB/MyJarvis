import "./lib/ancienNom"; // en premier : reprend les préférences enregistrées sous l'ancien nom (Jarvis)
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
