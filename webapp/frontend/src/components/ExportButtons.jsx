// F02 검수 확인서 내려받기(xlsx / hwpx). rows: 확인서 행(여러 구성요소 이어 붙임). 서버가 미실행 구성요소를 '미검사'로 채워 54개 항목을 만든다.
import React, { useState } from "react";

import { api } from "../lib/api.js";

export function ExportButtons({ moduleCode, rows, createdAt, disabled, onError }) {
  const [busy, setBusy] = useState(null);   // 진행 중인 형식
  async function run(format) {
    setBusy(format);
    const { ok, error } = await api.exportSheet({ moduleCode, rows, createdAt, format });
    if (!ok) onError?.(error);
    setBusy(null);
  }
  return (
    <span className="export-buttons">
      <span className="meta">확인서 내려받기</span>
      <button type="button" className="krds-btn small secondary" disabled={disabled || busy} onClick={() => run("hwpx")}
              title="원본 F02 양식(hwpx)에 ✓와 비고를 채운 제출본">{busy === "hwpx" ? "만드는 중…" : "hwpx (제출 양식)"}</button>
      <button type="button" className="krds-btn small tertiary" disabled={disabled || busy} onClick={() => run("xlsx")}
              title="열람·편집용 엑셀">{busy === "xlsx" ? "만드는 중…" : "xlsx"}</button>
    </span>
  );
}
