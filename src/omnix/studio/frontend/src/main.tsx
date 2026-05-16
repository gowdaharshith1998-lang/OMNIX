import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { loader } from "@monaco-editor/react";
import App from "./App";
import { registerOmnixMonacoTheme } from "./styles/monaco-theme";
import "./index.css";

void loader.init().then((monaco) => {
  registerOmnixMonacoTheme(monaco);
});

const el = document.getElementById("root");
if (!el) throw new Error("root");
createRoot(el).render(
  <StrictMode>
    <App />
  </StrictMode>
);
