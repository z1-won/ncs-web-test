import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
// KRDS HTML 컴포넌트 키트의 토큰·컴포넌트 CSS (npm: krds-uiux)
import "krds-uiux/resources/cdn/krds.min.css";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
