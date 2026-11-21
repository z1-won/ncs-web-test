// 페이지 수준 알림 — 폼 칸에 속하지 않는 오류·안내(목록 로딩 실패, 실행 실패, 성공 안내).
// KRDS form-hint-invalid는 form-group 안의 입력 도움말용이라 바깥에서는 쓰지 않는다. 색·여백은 KRDS 토큰(surface/border/text의 danger·warning·success·information).
// warning: 결과는 나왔지만 그대로 믿거나 쓰기 전에 확인할 것(추정치, 상한 초과 등). 화면을 막는 오류가 아니라 role은 status.
import React from "react";

const ROLE = { danger: "alert", warning: "status", success: "status", info: "status" };

export function PageAlert({ kind = "danger", children, className = "" }) {
  if (!children) return null;
  return (
    <div className={`page-alert ${kind} ${className}`.trim()} role={ROLE[kind] || "status"}>
      <i className="svg-icon" aria-hidden="true"></i>
      <div className="page-alert-body">{children}</div>
    </div>
  );
}
