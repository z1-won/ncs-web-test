// KRDS 페이지네이션(.krds-pagination) — 이전/다음 + 번호(현재 주변 ±2, 양끝은 … 으로 줄임). 링크 대신 버튼: 라우트가 바뀌지 않는 화면 안 페이지 넘김.
import React from "react";

function pageList(page, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const set = new Set([1, total, page - 1, page, page + 1]);
  if (page <= 3) [2, 3, 4].forEach((n) => set.add(n));
  if (page >= total - 2) [total - 3, total - 2, total - 1].forEach((n) => set.add(n));
  const nums = [...set].filter((n) => n >= 1 && n <= total).sort((a, b) => a - b);
  const out = [];
  nums.forEach((n, i) => { if (i && n - nums[i - 1] > 1) out.push("dot"); out.push(n); });
  return out;
}

export function Pagination({ page, total, onChange, label = "페이지" }) {
  if (total <= 1) return null;
  return (
    <nav className="krds-pagination" aria-label={label}>
      <button type="button" className={`page-navi prev${page <= 1 ? " disabled" : ""}`} disabled={page <= 1} onClick={() => onChange(page - 1)}>이전</button>
      <div className="page-links">
        {pageList(page, total).map((n, i) => n === "dot"
          ? <span key={`dot-${i}`} className="page-link link-dot" aria-hidden="true"></span>
          : <button key={n} type="button" className={`page-link${n === page ? " active" : ""}`} aria-current={n === page ? "page" : undefined} onClick={() => onChange(n)}>
              {n === page && <span className="sr-only">현재페이지 </span>}{n}
            </button>)}
      </div>
      <button type="button" className={`page-navi next${page >= total ? " disabled" : ""}`} disabled={page >= total} onClick={() => onChange(page + 1)}>다음</button>
    </nav>
  );
}
