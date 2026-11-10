// 화면 공통 훅.
import { useEffect, useState } from "react";

// 세로 스크롤 위치(px). rAF로 묶어 스크롤마다 한 번만 갱신한다. 헤더의 현재 영역 표시와 TOP 버튼이 함께 쓴다.
export function useScrollY() {
  const [y, setY] = useState(() => (typeof window === "undefined" ? 0 : window.scrollY));
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { setY(window.scrollY); ticking = false; });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
    return () => { window.removeEventListener("scroll", onScroll); window.removeEventListener("resize", onScroll); };
  }, []);
  return y;
}

// 요소의 높이를 CSS 변수(--header-height 등)로 :root에 써 둔다. 앵커의 scroll-margin-top이 헤더 높이를 하드코딩하지 않게.
export function useCssHeightVar(ref, name) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const write = () => document.documentElement.style.setProperty(name, `${el.offsetHeight}px`);
    write();
    const observer = new ResizeObserver(write);
    observer.observe(el);
    return () => { observer.disconnect(); document.documentElement.style.removeProperty(name); };
  }, [ref, name]);
}

// 라우트별 탭 제목. index.html의 <title>은 하나라 화면마다 여기서 바꾼다. 서비스명은 뒤에 붙인다.
export const SERVICE_NAME = "NCS 학습모듈 검수";
export function usePageTitle(title) {
  useEffect(() => {
    const prev = document.title;
    document.title = title ? `${title} — ${SERVICE_NAME}` : SERVICE_NAME;
    return () => { document.title = prev; };
  }, [title]);
}
