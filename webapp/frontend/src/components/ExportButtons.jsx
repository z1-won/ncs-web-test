// F02 검수 확인서 내려받기(xlsx / hwpx). rows: 확인서 행(여러 구성요소 이어 붙임). 서버가 미실행 구성요소를 '미검사'로 채워 54개 항목을 만든다.
import React, { useState } from "react";

import { api } from "../lib/api.js";

// annotate: { upload(토큰), rows(체크리스트 행, 적합 제외) } — 있으면 '수정 메모 원고' 버튼도 보인다(원고가 아직 서버에 있을 때만)
export function ExportButtons({ moduleCode, rows, createdAt, disabled, onError, onNotice, annotate }) {
  const [busy, setBusy] = useState(null);   // 진행 중인 형식
  async function run(format) {
    setBusy(format);
    const { ok, error } = await api.exportSheet({ moduleCode, rows, createdAt, format });
    if (!ok) onError?.(error);
    setBusy(null);
  }
  async function runAnnotate() {
    setBusy("memo");
    const { ok, error, summary } = await api.exportAnnotated({ moduleCode, upload: annotate.upload, rows: annotate.rows });
    if (!ok) onError?.(error);
    else if (summary) onNotice?.(`메모 ${summary.memos}개 — 지적 ${summary.placed}건을 문단에 달았고 ${summary.unplaced}건은 총괄 메모에 적었습니다.`);
    setBusy(null);
  }
  return (
    <span className="export-buttons">
      <span className="meta">확인서 내려받기</span>
      <button type="button" className="krds-btn small secondary" disabled={disabled || busy} onClick={() => run("hwpx")}
              title="원본 F02 양식(hwpx)에 ✓와 비고를 채운 제출본">{busy === "hwpx" ? "만드는 중…" : "hwpx (제출 양식)"}</button>
      <button type="button" className="krds-btn small tertiary" disabled={disabled || busy} onClick={() => run("xlsx")}
              title="열람·편집용 엑셀">{busy === "xlsx" ? "만드는 중…" : "xlsx"}</button>
      {annotate?.upload && (
        <>
          <span className="meta sep">·</span>
          <button type="button" className="krds-btn small tertiary" disabled={disabled || busy || !annotate.rows?.length} onClick={runAnnotate}
                  title="원고 hwpx의 해당 문단에 지적사항을 한글 메모로 단 파일(본문은 바꾸지 않음)">
            {busy === "memo" ? "만드는 중…" : `수정 메모 원고 (${annotate.rows?.length || 0}건)`}
          </button>
        </>
      )}
    </span>
  );
}
