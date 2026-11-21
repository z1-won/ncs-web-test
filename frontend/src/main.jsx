import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import HomePage from "./pages/HomePage.jsx";
import ImageDbPage from "./pages/ImageDbPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OpinionPage from "./pages/OpinionPage.jsx";
import PlanDraftPage from "./pages/PlanDraftPage.jsx";
import PrivacyPage from "./pages/PrivacyPage.jsx";
import ProgressPage from "./pages/ProgressPage.jsx";
import RightsPage from "./pages/RightsPage.jsx";
import RecommendPage from "./pages/RecommendPage.jsx";
import ReviewPage from "./pages/ReviewPage.jsx";
import SuggestPage from "./pages/SuggestPage.jsx";
import UpscalePage from "./pages/UpscalePage.jsx";
import VolumePage from "./pages/VolumePage.jsx";
// KRDS HTML 컴포넌트 키트의 토큰·컴포넌트 CSS (npm: krds-uiux)
// KRDS 기본 서체 Pretendard GOV — npm 패키지(pretendard-gov — GOV 서체는 pretendard와 별도 패키지)에서 번들(외부 CDN 요청 없음)
import "pretendard-gov/dist/web/static/pretendard-gov.css";
import "krds-uiux/resources/cdn/krds.min.css";
import { AuthProvider, useAuth } from "./lib/auth.jsx";
import "./app.css";

// 로그인 문 — 로그인이 필요한 서버에서 로그인하지 않았으면 로그인 화면을 보인다. 주소는 그대로 두어 로그인하면 가려던 화면이 열린다.
// 처음 화면(/)만은 로그인 전에도 보인다(무엇을 하는 곳인지 알 수 있게). 거기서 기능을 누르면 로그인 화면이 나온다.
function AuthGate({ children }) {
  const { status } = useAuth();
  const { pathname } = useLocation();
  if (status === "loading") return null;
  if (status === "out") return pathname === "/" ? <HomePage /> : <LoginPage />;
  if (status === "in" && pathname === "/login") return <Navigate to="/" replace />;
  if (status === "error") return <p className="inner page" role="alert">서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.</p>;
  return children;
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    {/* 페이지: / 처음 화면(최근 원고 미리 보기와 기능 바로 가기), /review 원고 검수, /plan 개발계획서 작성, /upscale 업스케일링, /images 이미지 저작권 DB, /recommend 이미지 추천, /rights 권리 증빙 점검, /volume 원고 분량 산정, /opinion 의견 반영 검토, /suggest 문장 추천, /progress 원고 진행 현황. 서버(ncs_web)는 /api 밖 404를 index.html로 돌려 새로 고침에도 열린다 */}
    <BrowserRouter>
      <AuthProvider>
      <AuthGate>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/review" element={<ReviewPage />} />
        <Route path="/plan" element={<PlanDraftPage />} />
        <Route path="/upscale" element={<UpscalePage />} />
        <Route path="/images" element={<ImageDbPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/rights" element={<RightsPage />} />
        <Route path="/volume" element={<VolumePage />} />
        <Route path="/suggest" element={<SuggestPage />} />
        <Route path="/privacy" element={<PrivacyPage />} />
        <Route path="/opinion" element={<OpinionPage />} />
        <Route path="/progress" element={<ProgressPage />} />
        <Route path="*" element={<HomePage />} />
      </Routes>
      </AuthGate>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
