// 원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 원고(모듈 코드)마다 남은 기록을 단계 7개와 진행도로 보여 준다.
// 읽기 전용이다. 단계의 상태는 서버(ncs_service.progress)가 기록으로 미룬 값이고 담당자가 확정한 값이 아니다.
// 서버가 DB 이력을 쓸 때만(/api/health의 history) 목록이 있다. 고른 원고는 주소(?code=)에 남아 새로 고침·공유에도 같은 화면이 열린다.
import React, { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { CHECKS } from "../lib/checks.js";
import { formatDate } from "../lib/format.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";
import "../progress.css";

const STAGE_COUNT = 7;
const CHECK_LABEL = Object.fromEntries(CHECKS.map((c) => [c.value, c.label]));
const CHECK_ORDER = CHECKS.map((c) => c.value);   // 편집 검수 표는 확인서 순서로
const day = (iso) => (iso ? formatDate(iso) : "-");

export default function ProgressPage() {
  usePageTitle("원고 진행 현황");
  const [params, setParams] = useSearchParams();
  const code = params.get("code") || "";
  const [history, setHistory] = useState(null);       // null: 확인 중, false: DB 없음
  const [list, setList] = useState(null);
  const [listError, setListError] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      const health = await api.health();
      if (!alive) return;
      const on = Boolean(health.ok && health.data?.history);
      setHistory(on);
      if (!on) return;
      const { ok, data, error } = await api.manuscripts.list();
      if (!alive) return;
      if (ok) setList(data); else setListError(error);
    })();
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!code || history !== true) { setDetail(null); setDetailError(null); return undefined; }
    let alive = true;
    setLoading(true);
    setDetailError(null);
    (async () => {
      const { ok, data, error } = await api.manuscripts.get(code);
      if (!alive) return;
      setLoading(false);
      if (ok) setDetail(data); else { setDetail(null); setDetailError(error); }
    })();
    return () => { alive = false; };
  }, [code, history]);

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page progress-page">
      <h1 className="page-title">원고 진행 현황</h1>
      <p className="page-desc">
        원고마다 남아 있는 기록(개발계획서 점검, 원고 검수, 의견 반영 검토, 원고 분량, 권리 증빙 점검, 이미지 저작권 DB)을 모아 단계와 검수 진행도로 보여 줍니다.
        파일 이름에 모듈 코드(LM으로 시작)가 있는 원고의 기록만 모입니다. 이 화면은 보기 전용이며 단계는 기록으로 미루어 표시한 것입니다.
      </p>

      {history === null && <Spinner label="기록을 확인하는 중" />}
      {history === false && <PageAlert kind="info">데이터베이스가 연결된 서버에서만 진행 현황을 볼 수 있습니다. 관리자에게 문의해 주세요.</PageAlert>}
      <PageAlert kind="danger">{listError}</PageAlert>

      {history && list && (
        <section aria-labelledby="progress-list-title">
          <h2 className="section-title" id="progress-list-title">원고 목록 <span className="meta">최근 기록순, {list.length}건</span></h2>
          {list.length === 0 ? (
            <p className="meta">아직 기록이 없습니다. 파일 이름에 모듈 코드가 있는 원고로 검수나 산정을 하면 여기에 모입니다.</p>
          ) : (
            <div className="krds-table-wrap">
              <table className="tbl col data" aria-labelledby="progress-list-title">
                <thead>
                  <tr><th scope="col">모듈 코드</th><th scope="col">학습모듈명</th><th scope="col">기록이 있는 단계</th><th scope="col">기록 수</th><th scope="col">최근 기록</th><th scope="col">보기</th></tr>
                </thead>
                <tbody>
                  {list.map((row) => (
                    <tr key={row.module_code} className={row.module_code === code ? "is-selected" : ""}>
                      <th scope="row">{row.module_code}</th>
                      <td>{row.name || "-"}</td>
                      <td>{row.stages_recorded} / {STAGE_COUNT}</td>
                      <td>{row.records}</td>
                      <td>{day(row.last_at)}</td>
                      <td className="progress-list-actions">
                        <button type="button" className="krds-btn small tertiary" aria-pressed={row.module_code === code}
                                onClick={() => setParams({ code: row.module_code })}>
                          진행 현황 보기<span className="sr-only"> {row.module_code}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {loading && <Spinner label="진행 현황을 불러오는 중" />}
      <PageAlert kind="danger">{detailError}</PageAlert>
      {detail && !loading && <ProgressDetail detail={detail} />}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function ProgressDetail({ detail }) {
  const progress = detail.진행도;
  const editing = progress["편집 검수"];
  const content = progress["내용 검수"];
  const rights = progress["저작권 검수"]["권리 증빙"];
  const images = progress["저작권 검수"]["이미지 저작권 DB"];
  const volume = progress.분량;
  const recorded = detail.단계.filter((s) => s.상태 === "기록 있음").length;
  return (
    <section className="progress-detail" aria-labelledby="progress-detail-title">
      <h2 className="section-title" id="progress-detail-title">
        {detail.module_code}{detail.학습모듈명 && ` ${detail.학습모듈명}`} <span className="meta">기록이 있는 단계 {recorded} / {STAGE_COUNT}</span>
      </h2>

      <h3 className="table-title" id="progress-numbers-title">검수 진행도</h3>
      <dl className="upscale-summary" aria-labelledby="progress-numbers-title">
        <div>
          <dt>편집 검수</dt>
          {editing.항목 ? (
            <>
              <dd><strong>{editing["적합 비율"] ?? "-"}</strong>% 적합</dd>
              <dd className="meta">적합 {editing.항목.적합}, 부적합 {editing.항목.부적합}, 판단불가 {editing.항목.판단불가} (구성요소 {editing.구성요소.length}개의 최근 검수)</dd>
            </>
          ) : <dd className="meta">기록 없음</dd>}
        </div>
        <div>
          <dt>내용 검수(의견 반영)</dt>
          {content.합계 ? (
            <>
              <dd>의견 <strong>{content.합계["총 의견"]}</strong>개</dd>
              <dd className="meta">반영 후보 {content.합계["반영 후보"]}, 미반영 후보 {content.합계["미반영 후보"]}, 확인 필요 {content.합계["확인 필요"]}</dd>
            </>
          ) : <dd className="meta">기록 없음</dd>}
        </div>
        <div>
          <dt>저작권 검수</dt>
          {rights ? (
            <>
              <dd>권리 증빙 <Badge value={rights.판정} /></dd>
              <dd className="meta">원고 그림 {rights["원고 그림"] ?? "-"}개, 누락 {rights.누락 ?? "-"}건, 확인 필요 {rights["확인 필요"] ?? "-"}건</dd>
            </>
          ) : <dd className="meta">권리 증빙 점검 기록 없음</dd>}
          <dd className="meta">이미지 저작권 DB: 그림 {images.그림}개 중 확정 {images.확정}개</dd>
        </div>
        <div>
          <dt>원고 분량</dt>
          {volume ? (
            <>
              <dd><strong>{volume.pages}</strong>매{volume.estimated && " (추정)"}</dd>
              <dd className="meta">집필료 {volume.fee.toLocaleString()}원, {day(volume.created_at)} 산정</dd>
            </>
          ) : <dd className="meta">기록 없음</dd>}
        </div>
      </dl>

      <h3 className="table-title" id="progress-steps-title">단계 <span className="meta">{detail["단계 근거"]}</span></h3>
      <p className="meta section-desc">{detail["단계 안내"]}</p>
      <ol className="progress-steps" aria-labelledby="progress-steps-title">
        {detail.단계.map((stage) => (
          <li key={stage.번호} className={stage.상태 === "기록 있음" ? "is-recorded" : ""}>
            <span className="progress-step-no" aria-hidden="true">{stage.번호}</span>
            <div className="progress-step-body">
              <div className="progress-step-head">
                <h3><span className="sr-only">{stage.번호}단계 </span>{stage.이름}</h3>
                <span className={`krds-badge ${stage.상태 === "기록 있음" ? "bg-light-success" : "bg-light-gray"}`}>{stage.상태}</span>
                <Link className="krds-btn small text" to={stage.경로}>{stage.기능} 열기</Link>
              </div>
              <p className="meta">{stage.담당}</p>
              {stage.내용 && <p>{stage.내용}{stage.일시 && <span className="meta"> ({day(stage.일시)})</span>}</p>}
            </div>
          </li>
        ))}
      </ol>

      {editing.구성요소.length > 0 && (
        <>
          <h3 className="table-title" id="progress-editing-title">편집 검수 <span className="meta">구성요소마다 가장 최근 검수의 확인서 항목 수</span></h3>
          <div className="krds-table-wrap">
            <table className="tbl col data" aria-labelledby="progress-editing-title">
              <thead><tr><th scope="col">구성요소</th><th scope="col">판정</th><th scope="col">적합</th><th scope="col">부적합</th><th scope="col">판단불가</th><th scope="col">검수한 때</th></tr></thead>
              <tbody>
                {[...editing.구성요소].sort((a, b) => CHECK_ORDER.indexOf(a.검수) - CHECK_ORDER.indexOf(b.검수)).map((row) => (
                  <tr key={row.검수}>
                    <th scope="row">{CHECK_LABEL[row.검수] || row.검수}</th><td><Badge value={row.판정} /></td>
                    <td>{row.적합}</td><td>{row.부적합}</td><td>{row.판단불가}</td><td>{day(row.일시)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {content.차수.length > 0 && (
        <>
          <h3 className="table-title" id="progress-content-title">내용 검수 <span className="meta">차수마다 가장 최근 의견 반영 검토의 개수</span></h3>
          <div className="krds-table-wrap">
            <table className="tbl col data" aria-labelledby="progress-content-title">
              <thead><tr><th scope="col">차수</th><th scope="col">총 의견</th><th scope="col">반영 후보</th><th scope="col">미반영 후보</th><th scope="col">확인 필요</th><th scope="col">조치 불필요</th><th scope="col">검토한 때</th></tr></thead>
              <tbody>
                {content.차수.map((row) => (
                  <tr key={row.차수}>
                    <th scope="row">{row.차수}</th><td>{row["총 의견"]}</td><td>{row["반영 후보"]}</td><td>{row["미반영 후보"]}</td>
                    <td>{row["확인 필요"]}</td><td>{row["조치 불필요"]}</td><td>{day(row.일시)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta">의견 문장과 원고 문단은 저장하지 않고 개수만 남깁니다. 반영 후보와 미반영 후보는 담당자가 확정하기 전의 값입니다.</p>
        </>
      )}
    </section>
  );
}
