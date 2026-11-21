// 처음 화면(/) — 최근 원고의 진행 현황 미리 보기와 기능 바로 가기.
// 미리 보기는 서버가 DB 이력을 쓸 때만(/api/health의 history) 보인다. 전체 목록과 한 원고의 단계·진행도는 /progress(머리글의 '진행 현황').
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { SERVICE_NAME, usePageTitle } from "../lib/hooks.js";
import "../progress.css";

const PREVIEW = 5;        // 미리 보기에 보이는 원고 수
const STAGE_COUNT = 7;
// 작업 순서대로. 설명은 한 줄 — 무엇을 올리면 무엇이 나오는지
const SHORTCUTS = [
  { path: "/plan", label: "개발계획서 작성", desc: "세분류를 고르면 NCS 기준정보를 채운 초안을 만들고, 작성한 계획서를 점검합니다." },
  { path: "/review", label: "원고 검수", desc: "원고를 올리면 검수 확인서 항목별로 적합 여부와 위치, 사유를 보여 줍니다." },
  { path: "/opinion", label: "의견 반영 검토", desc: "검토의견서와 심의의견서의 의견이 최종 원고에 반영되었는지 후보를 보여 줍니다." },
  { path: "/upscale", label: "업스케일링", desc: "원고 속 저화질 그림을 찾아 화질을 높인 제안본을 만듭니다." },
  { path: "/images", label: "이미지 저작권 DB", desc: "그림의 권리 정보를 등록하고 기관이 확정합니다." },
  { path: "/recommend", label: "이미지 추천", desc: "수행준거와 문단에 맞는, 권리가 확정된 그림을 찾아 줍니다." },
  { path: "/rights", label: "권리 증빙 점검", desc: "원고의 그림과 제출 서류를 대조해 빠진 증빙과 기한을 알려 줍니다." },
  { path: "/volume", label: "원고 분량", desc: "계약서 기준으로 원고 분량(매)과 집필료를 산정합니다." },
  { path: "/suggest", label: "문장 추천", desc: "원고 문장을 작성 규칙과 문맥에 맞게 다듬은 후보를 보여 줍니다." },
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
      <h1 className="page-title">{SERVICE_NAME}</h1>
      <p className="page-desc">
        NCS 학습모듈 원고의 집필과 검수를 돕는 도구 모음입니다. 아래에서 필요한 기능을 고르세요. 결과는 모두 참고용이며 최종 판단은 담당자가 합니다.
      </p>

      {list && (
        <section aria-labelledby="home-recent-title">
          <div className="home-section-head">
            <h2 className="section-title" id="home-recent-title">최근 원고 <span className="meta">기록이 있는 단계, {STAGE_COUNT}단계 중</span></h2>
            <Link className="krds-btn small tertiary" to="/progress">진행 현황 전체 보기</Link>
          </div>
          {list.length === 0 ? (
            <p className="meta">아직 기록이 없습니다. 파일 이름에 모듈 코드가 있는 원고로 검수나 산정을 하면 여기에 보입니다.</p>
          ) : (
            <ul className="home-recent">
              {list.slice(0, PREVIEW).map((row) => (
                <li key={row.module_code}>
                  <Link to={`/progress?code=${encodeURIComponent(row.module_code)}`}>
                    <strong>{row.name || row.module_code}</strong>
                    <span className="meta">{row.module_code}</span>
                    <span className="home-recent-steps" aria-label={`기록이 있는 단계 ${row.stages_recorded}, 전체 ${STAGE_COUNT}`}>
                      {Array.from({ length: STAGE_COUNT }, (_, i) => <i key={i} className={i < row.stages_recorded ? "is-on" : ""} aria-hidden="true" />)}
                      <b>{row.stages_recorded} / {STAGE_COUNT}</b>
                    </span>
                    <span className="meta">최근 기록 {formatDate(row.last_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section aria-labelledby="home-shortcuts-title">
        <h2 className="section-title" id="home-shortcuts-title">기능 바로 가기</h2>
        <ul className="home-shortcuts">
          {SHORTCUTS.map((item) => (
            <li key={item.path}>
              <Link to={item.path}><strong>{item.label}</strong><span>{item.desc}</span></Link>
            </li>
          ))}
        </ul>
      </section>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
