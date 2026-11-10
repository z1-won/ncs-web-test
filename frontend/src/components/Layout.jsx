// 페이지 틀 — KRDS 헤더(건너뛰기 링크·로고·메인 메뉴), 맨 위로 버튼, 푸터.
import React, { useMemo, useRef } from "react";
import { Link, useLocation } from "react-router-dom";

import { useCssHeightVar, useScrollY } from "../lib/hooks.js";

/* 맨 위로(TOP) 버튼 — KRDS 아이콘 버튼 규격(app.css .krds-btn-top). 화면 높이의 절반 넘게 내려가면 나타나고, 누르면 맨 위로 올린 뒤 포커스를 본문(#container)으로 옮긴다. */
export function TopButton({ target = "#container" }) {
  const y = useScrollY();
  const active = y > (typeof window === "undefined" ? 0 : window.innerHeight / 2);
  function goTop() {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    const el = document.querySelector(target);
    if (el) {
      if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
      el.focus({ preventScroll: true });
    }
  }
  return (
    <button type="button" className={`krds-btn-top${active ? " active" : ""}`} aria-label="맨 위로 이동" onClick={goTop}>
      <i className="svg-icon" aria-hidden="true"></i>
      <span className="sr-only">맨 위로</span>
    </button>
  );
}

/* 헤더 — KRDS 헤더(#krds-header) 최소 구성: 건너뛰기 링크 + 로고(서비스 식별)만. 통합검색·로그인·메인메뉴·유틸리티 메뉴는 이 서비스에 없어 두지 않는다. */
export const NAV_ITEMS = [   // 화면 순서와 같다: 실행 → 결과(주 동선) → 이력(부차)
  { id: "review-run", label: "검수 실행" },
  { id: "review-result", label: "검수 결과" },
  { id: "review-history", label: "검수 이력" },
];

/* 페이지 메뉴 — 라우트 단위. 화면이 둘(원고 검수 / 개발계획서 작성)이라 1Depth 링크형 */
export const PAGES = [
  { path: "/", label: "원고 검수" },
  { path: "/plan", label: "개발계획서 작성" },
];

export function Header({ hasHistory, hasResult, anchors = NAV_ITEMS }) {
  const location = useLocation();
  const items = useMemo(
    () => anchors.filter((item) => (item.id === "review-history" ? hasHistory : item.id === "review-result" ? hasResult : true)),
    [anchors, hasHistory, hasResult],
  );
  const header = useRef(null);
  useCssHeightVar(header, "--header-height");   // app.css의 앵커 scroll-margin-top이 이 값을 읽는다
  // 화면이 하나라 메뉴는 영역 이동(앵커). 스크롤 위치에 따라 현재 영역을 활성 표시한다 — 렌더마다 계산(스크롤 값이 바뀔 때만 다시 그려진다).
  useScrollY();   // 스크롤 값이 바뀔 때마다 다시 그려지도록 구독만 한다 — 아래 현재 영역 계산은 렌더마다(싼 계산) 수행
  const headerHeight = header.current?.offsetHeight || 0;
  let current = items[0]?.id;
  for (const item of items) {
    const el = document.getElementById(item.id);
    // 앵커는 scroll-margin-top(헤더 + gap-7)만큼 띄워 멈추므로 그 여유(약 4rem)까지는 "현재 영역"으로 본다
    if (el && el.getBoundingClientRect().top <= headerHeight + 40) current = item.id;
  }
  function go(e, id) {
    e.preventDefault();
    const el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    el.focus({ preventScroll: true });
  }
  return (
    <>
      <div id="krds-skip-link">
        <a href="#container">본문 바로가기</a>
      </div>
      <header id="krds-header" ref={header}>
        <div className="header-in">
          <div className="header-container">
            <div className="inner">
              <div className="header-branding">
                <h2 className="logo">
                  <Link to="/"><span className="sr-only">NCS 학습모듈 검수 — 동국대학교</span></Link>
                </h2>
              </div>
            </div>
          </div>
          {/* 메인 메뉴 — KRDS .krds-main-menu, 1Depth 링크형(.is-link). 앞은 페이지 이동(라우터), 뒤는 현재 페이지 안 영역 이동(앵커) */}
          <nav className="krds-main-menu" aria-label="주요 영역">
            <div className="inner">
              <ul className="gnb-menu">
                {PAGES.map((page) => (
                  <li key={page.path}>
                    <Link to={page.path} className={`gnb-main-trigger is-link page-link${location.pathname === page.path ? " active" : ""}`}
                          aria-current={location.pathname === page.path ? "page" : undefined}>{page.label}</Link>
                  </li>
                ))}
                {items.map((item) => (
                  <li key={item.id}>
                    <a href={`#${item.id}`} className={`gnb-main-trigger is-link${current === item.id ? " active" : ""}`}
                       aria-current={current === item.id ? "location" : undefined} onClick={(e) => go(e, item.id)}>{item.label}</a>
                  </li>
                ))}
              </ul>
            </div>
          </nav>
        </div>
      </header>
    </>
  );
}

/* 푸터 — KRDS 푸터(#krds-footer) 표준 구조·치수 그대로: 서비스 로고(.f-logo 13.7×4.8rem) → 연락처(.f-info) → 유틸리티 링크(.f-link) → 정책 링크·저작권(.f-btm-text) → 운영기관 식별자(.krds-identifier). 관련 사이트(.foot-quick)·SNS는 두지 않는다. */
export function Footer() {
  return (
    <footer id="krds-footer">
      <div className="inner">
        <div className="f-logo">
          <span className="sr-only">동국대학교</span>
        </div>
        <div className="f-cnt">
          <div className="f-info">
            <p className="info-addr">동국대학교 종합설계1(김동우) · 프로토콜 팀 — 생성형 AI를 활용한 NCS 학습모듈 활용 및 사업운영 지원체계 구축</p>
            <ul className="info-cs">
              <li><span className="key-info"><strong className="strong">이메일</strong><span className="span">dgu2026protocol@gmail.com</span></span></li>
            </ul>
          </div>
          <div className="f-link">
            <div className="link-go">
              <a href="https://ai.dongguk.edu/main" className="krds-btn medium text" target="_blank" rel="noopener noreferrer" title="새 창 열기">동국대학교 첨단융합대학 <i className="svg-icon ico-angle right"></i></a>
              <a href="https://www.krivet.re.kr/kor/index.do" className="krds-btn medium text" target="_blank" rel="noopener noreferrer" title="새 창 열기">한국직업능력연구원 <i className="svg-icon ico-angle right"></i></a>
            </div>
          </div>
        </div>
        <div className="f-btm">
          <div className="f-btm-text">
            <div className="f-menu">
              <Link to="/privacy" className="point">개인정보처리방침</Link>
            </div>
            <p className="f-copy">© 2026 동국대학교 종합설계1 프로토콜 팀. All rights reserved.</p>
          </div>
          <div className="krds-identifier">
            <span className="logo">
              <span className="sr-only">한국직업능력연구원</span>
            </span>
            <span className="ban-txt">검수 기준: 한국직업능력연구원 NCS 학습모듈 검수 확인서</span>
          </div>
        </div>
      </div>
    </footer>
  );
}
