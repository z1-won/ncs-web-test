// 개인정보처리방침 — KRDS 푸터의 필수 정책 링크. 이 서비스가 실제로 다루는 데이터(올린 문서·생성 결과·입력한 담당자 이름)에 대해서만 적는다.
import React from "react";
import { Link } from "react-router-dom";

import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { usePageTitle } from "../lib/hooks.js";

export default function PrivacyPage() {
  usePageTitle("개인정보처리방침");
  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page policy">
      <h1 className="page-title">개인정보처리방침</h1>
      <p className="page-desc">
        이 누리집은 동국대학교 종합설계1 프로토콜 팀이 운영하는 NCS 학습모듈 검수·개발계획서 작성 지원 도구(로컬 테스트용)입니다.
        회원가입·로그인·쿠키 추적이 없으며, 아래의 자료만 처리합니다.
      </p>

      <h2 className="section-title">1. 처리하는 자료</h2>
      <ul className="krds-info-list dash">
        <li><strong>올린 문서</strong> — 원고·개발계획서(.hwp/.hwpx)·출력본 PDF. 검수를 위해 내용(본문·표·그림)을 읽습니다.</li>
        <li><strong>검수 결과</strong> — 확인서 행·지적사항·체크리스트와 모듈 코드, 실행 시각. 원고 파일명이 결과에 함께 남습니다.</li>
        <li><strong>개발계획서 작성에서 입력한 값</strong> — 개발기관명, 영문 세분류명, 능력단위별 담당 집필진·검토진 이름. 생성되는 초안 hwpx에만 쓰이고 서버에 저장하지 않습니다.</li>
      </ul>

      <h2 className="section-title">2. 보관과 삭제</h2>
      <ul className="krds-info-list dash">
        <li>올린 문서는 서버 임시 폴더에 두고 검수가 끝나면 지웁니다. 전체 실행용 업로드 토큰은 10분 뒤 자동으로 만료·삭제됩니다.</li>
        <li>검수 결과는 운영자가 정한 저장소(저장소 루트의 <code>결과/</code> 폴더 또는 데이터베이스)에 남으며, 화면의 검수 이력에서 <strong>삭제</strong> 버튼으로 언제든 지울 수 있습니다. 삭제한 이력은 되돌릴 수 없습니다.</li>
        <li>개발계획서 초안은 만든 즉시 내려받기로 전달되고 서버 사본은 남기지 않습니다.</li>
      </ul>

      <h2 className="section-title">3. 제3자 제공·외부 전송</h2>
      <ul className="krds-info-list dash">
        <li>올린 문서와 결과를 외부에 제공하지 않습니다. 서비스는 운영자의 컴퓨터(또는 지정한 서버)에서 실행되며 외부 서비스로 문서를 보내지 않습니다.</li>
        <li>수행 내용 ②(상품명 판별) 한 항목은 운영자가 API 키와 전송 승인(<code>LLM_ALLOW_UPLOAD=1</code>)을 <strong>둘 다</strong> 설정했을 때만 생성형 AI 모델(OpenAI 호환 API)을 호출합니다. 이때도 해당 블록의 재료·기기 줄만 보내고 원고 전체는 보내지 않으며, 둘 중 하나라도 없으면 외부 전송은 일어나지 않습니다.</li>
      </ul>

      <h2 className="section-title">4. 문의</h2>
      <p>자료 삭제 요청이나 문의는 <a href="mailto:dgu2026protocol@gmail.com">dgu2026protocol@gmail.com</a>으로 보내 주세요.</p>
      <p className="meta">시행일 2026년 11월 10일 · <Link to="/">원고 검수로 돌아가기</Link></p>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
