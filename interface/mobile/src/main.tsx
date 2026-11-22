import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../../src/index.css";
import "./mobile.css";
import App from "./App";
import { estTelephone } from "./garde";
import { RefusOrdinateur } from "./vues/Refus";

const racine = createRoot(document.getElementById("root")!);
if (!estTelephone()) {
  // sur ordinateur (ou tablette) : rien ne démarre, pas même la connexion au compte
  racine.render(<RefusOrdinateur />);
} else {
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/mobile/sw.js", { scope: "/mobile/" }).catch(() => {});
  racine.render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
