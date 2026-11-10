// 페이지 수준 알림 — 폼 칸에 속하지 않는 오류·안내(목록 로딩 실패, 실행 실패, 성공 안내).
// KRDS form-hint-invalid는 form-group 안의 입력 도움말용이라 바깥에서는 쓰지 않는다. 색·여백은 KRDS 토큰(surface/border/text의 danger·success·information).
import React from "react";

const ROLE = { danger: "alert", success: "status", info: "status" };

export function PageAlert({ kind = "danger", children, className = "" }) {
  if (!children) return null;
  return (
    <div className={`page-alert ${kind} ${className}`.trim()} role={ROLE[kind] || "status"}>
      <i className="svg-icon" aria-hidden="true"></i>
      <div className="page-alert-body">{children}</div>
    </div>
  );
}
