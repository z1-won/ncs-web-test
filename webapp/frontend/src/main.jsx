import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
// KRDS HTML 컴포넌트 키트의 토큰·컴포넌트 CSS (npm: krds-uiux)
// KRDS 기본 서체 Pretendard GOV — npm 패키지에서 번들(외부 CDN 요청 없음)
import "pretendard/dist/web/static/pretendard-gov.css";
import "krds-uiux/resources/cdn/krds.min.css";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
