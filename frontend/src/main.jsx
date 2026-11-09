import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import App from "./App.jsx";
import PlanDraftPage from "./pages/PlanDraftPage.jsx";
// KRDS HTML 컴포넌트 키트의 토큰·컴포넌트 CSS (npm: krds-uiux)
// KRDS 기본 서체 Pretendard GOV — npm 패키지(pretendard-gov — GOV 서체는 pretendard와 별도 패키지)에서 번들(외부 CDN 요청 없음)
import "pretendard-gov/dist/web/static/pretendard-gov.css";
import "krds-uiux/resources/cdn/krds.min.css";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* 페이지: / 원고 검수(기존 App), /plan 개발계획서 작성. 서버(ncs_web)는 /api 밖 404를 index.html로 돌려 새로 고침에도 열린다 */}
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />} />
        <Route path="/plan" element={<PlanDraftPage />} />
        <Route path="*" element={<App />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
