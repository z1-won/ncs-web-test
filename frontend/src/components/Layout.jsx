// 페이지 틀 — KRDS 헤더(건너뛰기 링크·로고·메인 메뉴), 맨 위로 버튼, 푸터.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { useAuth, useCanManage } from "../lib/auth.jsx";
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
  { id: "llm-review", label: "LLM 검토", afterResult: true, manager: true },     // manager: 에디터와 직능연 계정에만 보인다
  { id: "figures", label: "그림 검수", afterResult: true },
  { id: "sources", label: "표 출처 검토", afterResult: true },
  { id: "review-history", label: "검수 이력" },
];

/* 페이지 메뉴 — 처음 화면(HomePage)의 기능 묶음 넷(집필, 검수, 이미지, 기타)과 같은 묶음, 같은 순서다.
   메뉴와 처음 화면의 묶음이 다르면(예전: 업스케일링이 처음 화면에서는 이미지 묶음, 메뉴에서는 혼자) 같은 기능을 두 자리에서 찾게 된다.
   묶음은 눌러서 펼치는 2Depth다. 묶음 안 순서는 일하는 순서: 검수는 한 원고 → 여러 원고 → 의견 반영, 이미지는 화질 → 권리 정보 쌓기 → 찾기 → 없으면 만들기 → AI 표기.
   페이지 안 영역(anchors)은 하위 메뉴(.page-subnav)에 */
export const PAGES = [
  { id: "write", label: "집필", children: [
    { path: "/plan", label: "개발계획서 작성" },
    { path: "/suggest", label: "문장 추천" },
  ] },
  { id: "review", label: "검수", children: [
    { path: "/review", label: "원고 검수" },
    { path: "/review/batch", label: "원고 폴더 일괄 검수", manager: true },     // manager: 에디터와 직능연 계정에만 보인다(lib/auth.jsx)
    { path: "/opinion", label: "의견 반영 검토", manager: true },
  ] },
  { id: "image", label: "이미지", children: [
    { path: "/upscale", label: "업스케일링" },
    { path: "/images", label: "이미지 저작권 DB" },
    { path: "/recommend", label: "이미지 추천" },
    { path: "/ai-generate", label: "이미지 AI 생성" },
    { path: "/ai-image", label: "이미지 AI 보완" },
  ] },
  { id: "finish", label: "기타", children: [
    { path: "/rights", label: "권리 증빙 점검" },
    { path: "/volume", label: "원고 분량" },
  ] },
];

/* 2Depth 묶음 — KRDS 메인 메뉴 마크업(.gnb-main-trigger 버튼 + .gnb-toggle-wrap › .gnb-main-list › a.gnb-sub-trigger.is-link).
   KRDS 가이드대로 클릭·Enter·Space로만 펼치고(마우스오버로 펼치지 않음), Esc는 닫고 초점을 1Depth 버튼으로, 바깥 클릭·초점 이탈·항목 선택이면 닫는다.
   펼친 동안 버튼은 .active(밑줄 + 화살표 뒤집힘), 하위 페이지에 있을 때는 .selected(밑줄)로 현재 위치를 알린다. */
function MenuGroup({ group, pathname }) {
  const [open, setOpen] = useState(false);
  const item = useRef(null);
  const trigger = useRef(null);
  const canManage = useCanManage();
  const children = group.children.filter((child) => canManage || !child.manager);
  const here = children.some((child) => child.path === pathname);
  const panelId = `gnb-${group.id}`;

  useEffect(() => {
    if (!open) return undefined;
    function onDown(event) { if (!item.current?.contains(event.target)) setOpen(false); }
    function onKey(event) {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <li ref={item} onBlur={(event) => { if (!item.current?.contains(event.relatedTarget)) setOpen(false); }}>
      <button ref={trigger} type="button" className={`gnb-main-trigger${open ? " active" : ""}${here ? " selected" : ""}`}
              aria-haspopup="true" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen((o) => !o)}>
        {group.label}{here && <span className="sr-only"> (현재 메뉴)</span>}
      </button>
      <div className={`gnb-toggle-wrap${open ? " is-open" : ""}`} id={panelId}>
        <div className="gnb-main-list" data-has-submenu="false">
          <ul>
            {children.map((child) => (
              <li key={child.path}>
                <Link to={child.path} className={`gnb-sub-trigger is-link${pathname === child.path ? " active" : ""}`}
                      aria-current={pathname === child.path ? "page" : undefined} onClick={() => setOpen(false)}>{child.label}</Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </li>
  );
}

export function Header({ hasHistory, hasResult, anchors = NAV_ITEMS }) {
  const location = useLocation();
  const { status, account, logOut } = useAuth();
  const signedOut = status === "out";     // 로그인 전: 메뉴를 숨긴다. 처음 화면에는 [로그인]만, 로그인 화면에는 로고만 보인다
  const canManage = useCanManage();
  const items = useMemo(
    () => anchors.filter((item) => (canManage || !item.manager)
      && (item.id === "review-history" ? hasHistory : item.id === "review-result" || item.afterResult ? hasResult : true)),
    [anchors, hasHistory, hasResult, canManage],
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
                  <Link to="/"><span className="sr-only">NCS 학습모듈 검수, 한국직업능력연구원</span></Link>
                </h2>
              </div>
              {/* 진행 현황은 작업 도구가 아니라 가끔 확인하는 화면이라 작업 메뉴 밖(머리글 오른쪽)에 둔다. 로그인이 생기면 이 자리가 '내 원고'가 된다 */}
              {signedOut ? (location.pathname === "/" && (
              <div className="header-actions">
                <Link to="/login" className="krds-btn small secondary">로그인</Link>
              </div>
              )) : (
              <div className="header-actions">
                {account && <span className="header-account"><strong>{account.name}</strong> {account.role_name}</span>}
                <Link to="/cases" className={`krds-btn small ${location.pathname === "/cases" ? "secondary" : "tertiary"}`}
                      aria-current={location.pathname === "/cases" ? "page" : undefined}>세분류 건</Link>
                <Link to="/progress" className={`krds-btn small ${location.pathname === "/progress" ? "secondary" : "tertiary"}`}
                      aria-current={location.pathname === "/progress" ? "page" : undefined}>진행 현황</Link>
                {account && <button type="button" className="krds-btn small tertiary" onClick={logOut}>로그아웃</button>}
              </div>
              )}
            </div>
          </div>
          {/* 메인 메뉴 — KRDS .krds-main-menu, 1Depth 링크형(.is-link). 페이지 이동만 두어 어느 화면에서도 같은 항목이 보이게 한다(#10) */}
          {!signedOut && <nav className="krds-main-menu" aria-label="주요 영역">
            <div className="inner">
              <ul className="gnb-menu">
                {PAGES.map((page) => page.children ? <MenuGroup key={page.id} group={page} pathname={location.pathname} /> : (
                  <li key={page.path}>
                    <Link to={page.path} className={`gnb-main-trigger is-link page-link${location.pathname === page.path ? " active" : ""}`}
                          aria-current={location.pathname === page.path ? "page" : undefined}>{page.label}</Link>
                  </li>
                ))}
              </ul>
            </div>
          </nav>}
          {/* 하위 메뉴 — 현재 페이지 안 영역 이동(앵커). 페이지마다 항목이 다르므로 메인 메뉴와 분리해 한 단 아래 둔다. 영역이 없는 페이지(개인정보처리방침)는 생략 */}
          {items.length > 0 && (
            <nav className="page-subnav" aria-label="현재 페이지 영역">
              <div className="inner">
                <ul className="subnav-menu">
                  {items.map((item) => (
                    <li key={item.id}>
                      <a href={`#${item.id}`} className={`subnav-trigger${current === item.id ? " active" : ""}`}
                         aria-current={current === item.id ? "location" : undefined} onClick={(e) => go(e, item.id)}>{item.label}</a>
                    </li>
                  ))}
                </ul>
              </div>
            </nav>
          )}
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
            <p className="info-addr">동국대학교 종합설계1(김동우) 프로토콜 팀</p>
            <p className="info-addr">생성형 AI를 활용한 NCS 학습모듈 활용 및 사업운영 지원체계 구축</p>
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
