// 결과 머리글 — 단독 결과(App)와 전체 실행(AllResults)이 같은 틀을 쓴다. 어떤 검수든 내려받기·펼치기 버튼이 같은 자리에 오도록
// 두 줄로 고정한다: 1줄 판정 배지 + 설명(메타) + 상태 배지, 2줄 액션 바(왼쪽 내려받기 묶음, 오른쪽 보기 도구).
// 액션이 아직 없을 때(검사 진행 중)도 2줄의 자리는 비워 둬 결과가 채워질 때 아래 내용이 밀리지 않는다.
import React from "react";

export function ResultHead({ status, meta, badges, downloads, tools }) {
  return (
    <div className="result-head">
      <div className="summary">
        {status}
        {meta && <span className="meta">{meta}</span>}
        {badges}
      </div>
      <div className="actions">
        <div className="downloads">{downloads}</div>
        {tools && <div className="toolbar">{tools}</div>}
      </div>
    </div>
  );
}
