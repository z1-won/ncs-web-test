// 처음 화면(/) — 위쪽 띠(무엇을 할지 묻는 제목 + 원고 검수 시작), 최근 원고의 진행 현황 미리 보기, 묶음별 기능 카드.
// 미리 보기는 서버가 DB 이력을 쓸 때만(/api/health의 history) 보인다. 전체 목록과 한 원고의 단계·진행도는 /progress(머리글의 '진행 현황').
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { usePageTitle } from "../lib/hooks.js";
import "../progress.css";

const PREVIEW = 3;        // 미리 보기에 보이는 원고 수 — 아래 기능 묶음과 같은 3열 한 줄
const STAGE_COUNT = 7;
// 기능 묶음 셋, 묶음마다 카드 셋(3 × 3이라 빈 자리가 없다). 번호를 붙이지 않는다(이미지 작업은 검수와 나란히 가고, 묶음이 곧 순서는 아니다). 카드: 무엇을 하는지 한 줄 + 필요한 파일.
// ai: 원고 문장이나 입력한 글 일부가 생성형 AI 서비스로 나가는 기능(개인정보처리방침 '외부로 보내는 내용'과 같아야 한다)
const GROUPS = [
  { title: "집필과 정산", items: [
    { path: "/plan", label: "개발계획서 작성", desc: "세분류를 고르면 NCS 기준정보를 채운 초안을 만들고, 작성한 계획서를 점검합니다.",
      files: "초안은 파일 없이 세분류 선택. 점검은 개발계획서(hwp, hwpx)" },
    { path: "/suggest", label: "문장 추천", desc: "작성 규칙에 맞지 않는 문장을 찾아 고칠 후보를 보여 줍니다.", files: "원고(hwp, hwpx)", ai: "생성형 AI 사용" },
    { path: "/volume", label: "원고 분량", desc: "계약서 기준으로 원고 분량(매)과 집필료를 산정합니다.", files: "최종 원고(hwp, hwpx). 기존 원고와 출력본 PDF는 선택" },
  ] },
  { title: "검수", items: [
    { path: "/review", label: "원고 검수", desc: "검수 확인서 항목별로 적합 여부와 위치, 사유를 보여 줍니다.", main: true,
      files: "원고(hwp, hwpx). 개발계획서와 출력본 PDF는 선택", ai: "일부 항목에 생성형 AI 사용" },
    { path: "/opinion", label: "의견 반영 검토", desc: "검토의견서와 심의의견서의 의견이 최종 원고에 반영되었는지 대조합니다.",
      files: "검토의견서 또는 심의의견서, 최종 원고", ai: "생성형 AI 사용" },
    { path: "/rights", label: "권리 증빙 점검", desc: "원고의 그림과 제출 서류를 대조해 빠진 증빙과 기한을 알려 줍니다.", files: "원고, 제출 서류(수록 현황 목록, 동의서, 서약서)" },
  ] },
  { title: "이미지", items: [
    { path: "/upscale", label: "업스케일링", desc: "해상도가 낮은 그림의 화질을 높인 제안본을 만듭니다.", files: "원고(hwpx)" },
    { path: "/images", label: "이미지 저작권 DB", desc: "그림과 권리 정보를 등록하고 기관이 확정합니다.", files: "그림 파일과 권리 정보(JSON)" },
    { path: "/recommend", label: "이미지 추천", desc: "문단에 어울리는 그림을 이미지 저작권 DB에서 찾아 줍니다.", files: "파일 없이 문단을 화면에 입력", ai: "켰을 때만 생성형 AI 사용" },
  ] },
];

export default function HomePage() {
  usePageTitle("");
  const [list, setList] = useState(null);      // null: DB 없음 또는 확인 전(미리 보기 자리를 그리지 않는다)

  useEffect(() => {
    let alive = true;
    (async () => {
      const health = await api.health();
      if (!alive || !(health.ok && health.data?.history)) return;
      const { ok, data } = await api.manuscripts.list();
      if (alive && ok) setList(data);
    })();
    return () => { alive = false; };
  }, []);

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page home-page">
      <div className="home-hero">
        <div>
          <h1 className="page-title">어떤 업무를 하시겠습니까?</h1>
          <p className="page-desc">개발계획서 작성부터 원고 검수, 그림의 권리 확인까지 한곳에서 할 수 있습니다. 결과는 모두 참고용이며 최종 판단은 담당자가 합니다.</p>
        </div>
        <Link className="krds-btn large primary" to="/review">원고 검수 시작</Link>
      </div>

      {list && (
        <section aria-labelledby="home-recent-title">
          <div className="home-section-head">
            <h2 className="section-title" id="home-recent-title">최근 원고 <span className="meta">기록이 있는 단계, {STAGE_COUNT}단계 중</span></h2>
            <Link className="krds-btn small tertiary" to="/progress">진행 현황 전체 보기</Link>
          </div>
          {list.length === 0 ? (
            <p className="meta">아직 기록이 없습니다. 파일 이름에 모듈 코드가 있는 원고로 검수나 산정을 하면 여기에 보입니다.</p>
          ) : (
            <ul className="home-grid home-recent">
              {list.slice(0, PREVIEW).map((row) => (
                <li key={row.module_code}>
                  <Link to={`/progress?code=${encodeURIComponent(row.module_code)}`}>
                    <strong className="home-card-title">{row.name || row.module_code}</strong>
                    <span className="home-card-files">{row.module_code}</span>
                    <span className="home-recent-steps" aria-label={`기록이 있는 단계 ${row.stages_recorded}, 전체 ${STAGE_COUNT}`}>
                      {Array.from({ length: STAGE_COUNT }, (_, i) => <i key={i} className={i < row.stages_recorded ? "is-on" : ""} aria-hidden="true" />)}
                      <b>{row.stages_recorded} / {STAGE_COUNT}</b>
                    </span>
                    <span className="home-card-files">최근 기록 {new Date(row.last_at).toLocaleDateString("ko-KR")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section aria-labelledby="home-groups-title">
        <h2 className="sr-only" id="home-groups-title">기능</h2>
        <div className="home-grid home-groups">
          {GROUPS.map((group) => (
            <div key={group.title} className="home-group">
              <h3 className="home-group-title">{group.title}</h3>
              <ul>
                {group.items.map((item) => (
                  <li key={item.path}>
                    <Link to={item.path} className={item.main ? "is-main" : ""}>
                      <strong className="home-card-title">{item.label}</strong>
                      <span className="home-card-desc">{item.desc}</span>
                      <span className="home-card-files">필요한 파일: {item.files}</span>
                      {/* 표시는 카드 맨 아래 줄에 둔다 — 제목 옆에 두면 표시가 있는 카드만 제목 줄이 두 줄이 되어 카드마다 글 위치가 달라진다 */}
                      <span className="home-card-tags">{item.ai && <span className="krds-badge bg-light-gray">{item.ai}</span>}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
