import React from "react";

// 검수결과 → KRDS 배지 변형
export const BADGE = { 적합: "bg-light-success", 부적합: "bg-light-danger", 판단불가: "bg-light-warning", 미검사: "bg-light-gray" };

export const MARK = { 적합: "pass", 부적합: "fail", 판단불가: "undecided" };

export function Badge({ value, large }) {
  return <span className={`krds-badge ${large ? "large " : ""}${BADGE[value] || "bg-light-gray"}`}>{value}</span>;
}

export function Spinner({ label }) {
  // KRDS 스피너: role=status + sr-only 글. 글을 눈에 보이게도 둔다(진행 중인 구성요소 이름)
  return <span className="krds-spinner" role="status"><span className="sr-only">{label}</span><span aria-hidden="true">{label}</span></span>;
}
