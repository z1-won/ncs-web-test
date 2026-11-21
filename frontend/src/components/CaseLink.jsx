// 세분류 건의 권·단계에서 연 도구 화면(의견 반영 검토, 원고 분량, 권리 증빙 점검)에 띄우는 안내.
// 주소의 ?case=&volume=&stage=&label= 을 읽는다. 이 화면에서 돌린 기록은 서버가 그 권과 단계에 붙인다(lib/api.js의 caseLink가 같이 보낸다).
import React from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PageAlert } from "./PageAlert.jsx";

export function CaseLinkNote() {
  const [params] = useSearchParams();
  const caseId = params.get("case");
  const volume = params.get("volume");
  if (!caseId || !volume || !params.get("stage")) return null;
  return (
    <PageAlert kind="info">
        세분류 건에서 열었습니다. 여기서 돌린 결과는 <strong>{params.get("label") || "그 권의 단계"}</strong>에 근거 기록으로 붙습니다.{" "}
        <Link to={`/cases?case=${encodeURIComponent(caseId)}&volume=${encodeURIComponent(volume)}`}>건 화면으로 돌아가기</Link>
    </PageAlert>
  );
}
