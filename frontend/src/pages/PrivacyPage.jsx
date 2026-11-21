// 개인정보처리방침 — KRDS 푸터의 필수 정책 링크. 이 서비스가 실제로 다루는 것만 적는다: 기능별 처리 자료, 보관과 삭제, 외부로 보내는 내용, 브라우저에 남는 것.
// 기능이 자료를 새로 저장하거나 외부로 보내게 되면 이 페이지를 함께 고친다. 근거 코드:
//   보관 — ncs_web/uploads.py(임시 보관 10분), ncs_service/migrations.py(review_files 원고 보관, volume_runs, image_*), ncs_core/llm.py(응답 캐시 30일)
//   외부 전송 — ncs_core/llm.py ALLOWED_TASKS(생성형 AI로 보내는 작업 목록), ncs_core/ncs_fetch.py(NCS), ncs_core/law_lookup.py(법제처), ncs_core/lexicon.py(표준국어대사전)
//   브라우저 — lib/imageTerms.js(변경한 사람 이름)
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
        이 누리집은 동국대학교 종합설계1 프로토콜 팀이 운영하는 NCS 학습모듈 검수와 개발계획서 작성 지원 도구(로컬 테스트용)입니다.
        회원가입과 로그인이 없고 쿠키를 쓰지 않습니다. 이 누리집이 다루는 자료와 보관 기간, 외부로 보내는 내용을 아래에 적었습니다.
      </p>

      <h2 className="section-title">1. 처리하는 자료</h2>
      <p className="section-desc">올린 문서에는 집필진, 검토진, 제작자의 이름이나 사진 속 인물처럼 개인을 알아볼 수 있는 내용이 들어 있을 수 있습니다.</p>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>기능별로 처리하는 자료</caption>
          <thead><tr><th scope="col">기능</th><th scope="col">처리하는 자료</th></tr></thead>
          <tbody>
            <tr><th scope="row">원고 검수</th><td>원고, 개발계획서(hwp, hwpx), 출력본 PDF의 본문, 표, 그림. 검수 결과(확인서, 지적사항, 모듈 코드, 실행 시각, 원고 파일 이름)</td></tr>
            <tr><th scope="row">개발계획서 작성</th><td>입력한 개발기관명, 영문 세분류명, 능력단위별 담당 집필진과 검토진 이름. 점검을 위해 올린 개발계획서</td></tr>
            <tr><th scope="row">의견 반영 검토</th><td>검토의견서, 최종 원고, 반영 전 원고, 출력본 PDF</td></tr>
            <tr><th scope="row">문장 추천</th><td>원고 또는 직접 입력한 문장</td></tr>
            <tr><th scope="row">원고 분량</th><td>최종 원고, 기존 원고, 출력본 PDF. 입력한 단가와 계약 분량, 산정 결과</td></tr>
            <tr><th scope="row">업스케일링</th><td>원고(hwpx)와 그 안의 그림</td></tr>
            <tr><th scope="row">권리 증빙 점검</th><td>원고, 제출 서류(사진·삽화 수록 현황 목록, 제작 목록, 이용허락 동의서, 생성형 AI 결과물 집필자 서약서), 출력본 PDF</td></tr>
            <tr><th scope="row">이미지 저작권 DB</th><td>그림 파일, 그림의 수록 위치와 출처, 권리 정보, 증빙 서류의 이름 또는 보관 위치, 입력한 ‘변경한 사람’ 이름</td></tr>
            <tr><th scope="row">이미지 추천</th><td>입력한 문단, 능력단위 코드, 수행준거 번호</td></tr>
          </tbody>
        </table>
      </div>

      <h2 className="section-title">2. 보관과 삭제</h2>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>자료별 보관 기간과 삭제 방법</caption>
          <thead><tr><th scope="col">자료</th><th scope="col">보관</th><th scope="col">삭제</th></tr></thead>
          <tbody>
            <tr><th scope="row">올린 문서</th><td>처리하는 동안만 서버의 임시 폴더에 둡니다. 원고 검수와 업스케일링은 올린 문서를 이어서 쓰기 위해 10분 동안 보관하며, 업스케일링 작업을 계속하는 동안에는 이 시간이 늘어납니다.</td><td>처리가 끝나거나 보관 시간이 지나면 자동으로 삭제합니다.</td></tr>
            <tr><th scope="row">원고 검수 결과</th><td>운영자가 정한 저장 위치(서버의 결과 폴더 또는 데이터베이스)에 남습니다. 데이터베이스를 쓰는 서버에서는 수정 메모 원고를 다시 만들 수 있도록 원고(hwpx) 파일도 검수 이력과 함께 보관합니다.</td><td>데이터베이스에 남은 것은 검수 이력의 [삭제] 버튼으로 삭제하며, 보관한 원고 파일도 함께 삭제합니다. 결과 폴더에 남은 것은 운영자가 폴더에서 삭제합니다.</td></tr>
            <tr><th scope="row">원고 분량 산정 이력</th><td>데이터베이스를 쓰는 서버에서만 남습니다. 산정 결과, 입력한 값, 올린 파일의 이름과 크기, 같은 파일인지 확인하는 값을 보관합니다. 원고 파일은 보관하지 않습니다.</td><td>산정 이력의 [삭제] 버튼으로 삭제합니다.</td></tr>
            <tr><th scope="row">이미지 저작권 DB</th><td>등록한 그림 파일과 권리 정보, 변경 이력(변경한 사람 이름, 시각, 바꾼 내용)을 데이터베이스에 보관합니다. 증빙 서류는 이름이나 보관 위치만 적고 서류 파일은 올리지 않습니다.</td><td>증빙 기록은 화면에서 삭제합니다. 그림과 변경 이력은 화면에서 삭제할 수 없으므로 아래 문의처로 요청해 주세요.</td></tr>
            <tr><th scope="row">의견 반영 검토, 문장 추천, 권리 증빙 점검의 결과</th><td>서버에 저장하지 않습니다. 화면에만 보이며 창을 닫으면 사라집니다. 권리 증빙 점검에서 [이미지 저작권 DB에 등록]을 누른 경우에만 그림과 수록 위치가 이미지 저작권 DB에 들어갑니다.</td><td>따로 삭제할 것이 없습니다.</td></tr>
            <tr><th scope="row">개발계획서 작성에서 입력한 값</th><td>초안(hwpx)을 만드는 데만 쓰고 서버에 저장하지 않습니다. 만든 초안도 서버에 남기지 않습니다.</td><td>따로 삭제할 것이 없습니다.</td></tr>
            <tr><th scope="row">생성형 AI 응답</th><td>같은 내용을 다시 묻지 않도록 서버에 30일 동안 보관합니다. 응답에는 보냈던 원고 문장이 들어 있을 수 있습니다.</td><td>30일이 지나면 자동으로 삭제합니다.</td></tr>
          </tbody>
        </table>
      </div>

      <h2 className="section-title">3. 외부로 보내는 내용</h2>
      <p className="section-desc">
        이 누리집은 운영자의 컴퓨터 또는 지정한 서버에서 실행됩니다. 올린 문서 전체를 외부로 보내는 일은 없습니다.
        아래 경우에만 문서의 일부나 낱말을 외부 서비스로 보내며, 모두 운영자가 서버에 인증 정보를 설정해 둔 경우에만 동작합니다.
      </p>
      <div className="krds-table-wrap">
        <table className="tbl col data">
          <caption>외부 서비스로 보내는 내용과 조건</caption>
          <thead><tr><th scope="col">보내는 곳</th><th scope="col">보내는 내용</th><th scope="col">보내는 때</th></tr></thead>
          <tbody>
            <tr>
              <th scope="row">생성형 AI 서비스(운영자가 설정한 OpenAI 호환 서비스 또는 Claude)</th>
              <td>
                원고 검수: 수행 내용 ②의 재료와 기기 줄, 수행 내용 ③의 안전과 유의 사항 줄, 평가 ④의 학습 목표와 평가 항목.<br />
                의견 반영 검토: 검토 의견과 그 의견이 가리키는 범위의 원고 문단.<br />
                문장 추천: 작성 규칙을 확인할 문장.<br />
                이미지 추천: 입력한 문단과 수행준거.
              </td>
              <td>운영자가 인증 정보와 외부 전송 승인을 <strong>둘 다</strong> 설정한 서버에서만 보냅니다. 이미지 추천은 화면에서 생성형 AI 사용을 켰을 때만 보냅니다. 둘 중 하나라도 없으면 보내지 않고 해당 항목을 판단불가로 둡니다.</td>
            </tr>
            <tr><th scope="row">NCS(공공데이터포털)</th><td>세분류 코드</td><td>개발계획서 작성에서 요소와 수행준거를 받아 올 때</td></tr>
            <tr><th scope="row">법제처 국가법령정보</th><td>개발계획서에 적힌 법령 이름</td><td>개발계획서 점검에서 법령 이름이 현행인지 확인할 때</td></tr>
            <tr><th scope="row">국립국어원 표준국어대사전</th><td>학습 내용명 등에 쓰인 낱말</td><td>낱말이 행동을 나타내는 명사인지 확인할 때</td></tr>
          </tbody>
        </table>
      </div>
      <ul className="krds-info-list dash">
        <li>이미지 추천의 그림 유사도 계산과 업스케일링은 서버 안에서만 하며 그림을 외부로 보내지 않습니다.</li>
        <li>올린 문서와 결과를 위 경우 말고 다른 곳에 제공하지 않습니다.</li>
      </ul>

      <h2 className="section-title">4. 브라우저에 남는 것</h2>
      <ul className="krds-info-list dash">
        <li>이미지 저작권 DB와 권리 증빙 점검에서 적은 ‘변경한 사람’ 이름은 다시 적지 않도록 지금 쓰는 브라우저에 기억해 둡니다. 브라우저의 사이트 데이터를 지우면 함께 지워집니다.</li>
        <li>그 밖에 쿠키나 방문 기록 추적은 쓰지 않습니다.</li>
      </ul>

      <h2 className="section-title">5. 문의와 삭제 요청</h2>
      <p>자료 삭제 요청이나 문의는 <a href="mailto:dgu2026protocol@gmail.com">dgu2026protocol@gmail.com</a>으로 보내 주세요.</p>
      <p className="meta">시행일 2026년 11월 21일(처음 시행 2026년 11월 10일)</p>
      <p className="meta"><Link to="/">원고 검수로 돌아가기</Link></p>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
