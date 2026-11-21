// 원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 원고(모듈 코드)마다 남은 기록을 단계 7개와 진행도로 보여 준다.
// 단계의 완료는 담당자가 여기서 직접 표시한다(누가·언제·메모, 되돌릴 수 있고 이력이 남는다). 기록은 완료를 판단할 근거로 옆에 보일 뿐이다.
// 누가 표시했는지는 로그인한 계정에서 서버가 읽는다(화면에서 이름을 받지 않는다).
// 화면 짜임은 이미지 저작권 DB와 같다: 위쪽 입력 묶음(모듈 코드로 열기) → 목록 → 고른 원고의 상세가 목록 아래에 열리고 [닫기].
// 서버가 DB 이력을 쓸 때만(/api/health의 history) 목록이 있다. 고른 원고는 주소(?code=)에 남아 새로 고침·공유에도 같은 화면이 열린다.
import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { CHECKS } from "../lib/checks.js";
import { formatDate } from "../lib/format.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";

const STAGE_COUNT = 7;
const CHECK_LABEL = Object.fromEntries(CHECKS.map((c) => [c.value, c.label]));
const CHECK_ORDER = CHECKS.map((c) => c.value);   // 편집 검수 표는 확인서 순서로
const ANCHORS = [{ id: "progress-list", label: "원고 목록" }, { id: "progress-detail", label: "단계와 진행도" }];
const day = (iso) => (iso ? formatDate(iso) : "-");
const dateOnly = (iso) => (iso ? new Date(iso).toLocaleDateString("ko-KR") : "");

// 단계 막대 — 처음 화면의 최근 원고 카드와 같은 모양(완료한 단계 수만큼 채운다)
export function StageBar({ done }) {
  return (
    <span className="home-recent-steps" aria-label={`완료한 단계 ${done}, 전체 ${STAGE_COUNT}`}>
      {Array.from({ length: STAGE_COUNT }, (_, i) => <i key={i} className={i < done ? "is-on" : ""} aria-hidden="true" />)}
      <b>완료 {done} / {STAGE_COUNT}</b>
    </span>
  );
}

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
  const [typed, setTyped] = useState("");            // 목록에 없는 원고를 모듈 코드로 여는 칸
  const detailBox = useRef(null);

  async function refreshList() {
    const { ok, data, error } = await api.manuscripts.list();
    if (ok) { setList(data); setListError(null); } else setListError(error);
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      const health = await api.health();
      if (!alive) return;
      const on = Boolean(health.ok && health.data?.history);
      setHistory(on);
      if (on) refreshList();
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
      if (ok) {
        setDetail(data);
        requestAnimationFrame(() => detailBox.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
      } else { setDetail(null); setDetailError(error); }
    })();
    return () => { alive = false; };
  }, [code, history]);

  function openTyped(e) {
    e.preventDefault();
    const value = typed.trim();
    if (value) { setParams({ code: value }); setTyped(""); }
  }

  return (
    <>
    <Header anchors={history ? ANCHORS : []} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page progress-page">
      <h1 className="page-title">원고 진행 현황</h1>
      <p className="page-desc">
        원고마다 단계 7개의 완료 여부와 검수 진행도를 보여 줍니다. 단계의 완료는 담당자가 직접 표시하고, 남아 있는 기록은 완료를 판단할 근거로 함께 보입니다.
        파일 이름에 모듈 코드(LM으로 시작)가 있는 원고의 기록만 모입니다.
      </p>

      {history === null && <Spinner label="기록을 확인하는 중" />}
      {history === false && <PageAlert kind="info">데이터베이스가 연결된 서버에서만 진행 현황을 볼 수 있습니다. 관리자에게 문의해 주세요.</PageAlert>}

      {history && (
        <form className="fieldset review-form is-sectioned" onSubmit={openTyped}>
          <div className="form-section-grid">
            <div className="form-group">
              <div className="form-tit"><label htmlFor="progress-code">모듈 코드로 원고 열기</label></div>
              <div className="form-conts progress-open">
                <input id="progress-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={typed}
                       onChange={(e) => setTyped(e.target.value)} aria-describedby="progress-code-hint" />
                <button type="submit" className="krds-btn medium secondary" disabled={!typed.trim()}>열기</button>
              </div>
              <p className="form-hint" id="progress-code-hint">아직 기록이 없는 원고도 열어서 단계를 표시할 수 있습니다.</p>
            </div>
          </div>
        </form>
      )}

      {history && (
        <section id="progress-list" className="nav-anchor">
          <div className="section-head">
            <h2 className="section-title">원고 목록{list ? <span className="meta"> {list.length}건, 최근 기록순</span> : null}</h2>
          </div>
          <PageAlert kind="danger">{listError}</PageAlert>
          {!list && !listError && <Spinner label="목록을 읽는 중" />}
          {list && (list.length === 0 ? (
            <p className="empty">아직 기록이 없습니다. 파일 이름에 모듈 코드가 있는 원고로 검수나 산정을 하면 여기에 모입니다.</p>
          ) : (
            <div className="krds-table-wrap">
              <table className="tbl col data progress-table">
                <caption>기록이 있는 원고와 완료한 단계</caption>
                <thead>
                  <tr><th scope="col">학습모듈</th><th scope="col">완료한 단계</th><th scope="col">근거 기록</th><th scope="col">최근 기록</th><th scope="col">열기</th></tr>
                </thead>
                <tbody>
                  {list.map((row) => (
                    <tr key={row.module_code} className={row.module_code === code ? "is-open" : ""}>
                      <th scope="row">{row.name || row.module_code}{row.name && <span className="meta">{row.module_code}</span>}</th>
                      <td><StageBar done={row.stages_done} /></td>
                      <td>{row.records}건<span className="meta">{row.stages_recorded}개 단계</span></td>
                      <td>{dateOnly(row.last_at)}</td>
                      <td>
                        <button type="button" className="krds-btn small tertiary" aria-pressed={row.module_code === code}
                                aria-label={`${row.name || row.module_code} 열기`} onClick={() => setParams({ code: row.module_code })}>열기</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      )}

      <div id="progress-detail" ref={detailBox} className="nav-anchor">
        {loading && <Spinner label="진행 현황을 불러오는 중" />}
        <PageAlert kind="danger">{detailError}</PageAlert>
        {detail && !loading && (
          <ProgressDetail detail={detail}
                          onChange={(next) => { setDetail(next); refreshList(); }} onClose={() => setParams({})} />
        )}
      </div>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function ProgressDetail({ detail, onChange, onClose }) {
  const [marking, setMarking] = useState(null);      // 메모를 적으려고 연 단계 번호
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [markError, setMarkError] = useState(null);

  async function mark(stage, done) {
    setSaving(true);
    setMarkError(null);
    const { ok, data, error } = await api.manuscripts.markStage(detail.module_code, stage, { done, note: done ? note.trim() : "" });
    setSaving(false);
    if (!ok) { setMarkError(error); return; }
    setMarking(null);
    setNote("");
    onChange(data);
  }

  const progress = detail.진행도;
  const editing = progress["편집 검수"];
  const content = progress["내용 검수"];
  const rights = progress["저작권 검수"]["권리 증빙"];
  const images = progress["저작권 검수"]["이미지 저작권 DB"];
  const volume = progress.분량;
  return (
    <section className="progress-detail" aria-labelledby="progress-detail-title">
      <div className="section-head">
        <h2 className="section-title" id="progress-detail-title">
          {detail.학습모듈명 || detail.module_code}{detail.학습모듈명 && <span className="meta"> {detail.module_code}</span>}
        </h2>
        <button type="button" className="krds-btn small tertiary" onClick={onClose}>닫기</button>
      </div>
      <p className="progress-overall"><StageBar done={detail["완료 단계 수"]} /></p>

      <h3 className="table-title" id="progress-steps-title">단계 <span className="meta">{detail["단계 근거"]}</span></h3>
      <PageAlert kind="danger">{markError}</PageAlert>
      <ol className="progress-steps" aria-labelledby="progress-steps-title">
        {detail.단계.map((stage) => (
          <li key={stage.번호} className={stage.완료 ? "is-done" : ""}>
            <span className="progress-step-no" aria-hidden="true">{stage.번호}</span>
            <div className="progress-step-body">
              <div className="progress-step-head">
                <h4><span className="sr-only">{stage.번호}단계 </span>{stage.이름}</h4>
                <span className={`krds-badge ${stage.완료 ? "bg-light-success" : "bg-light-gray"}`}>{stage.완료 ? "완료" : "완료 전"}</span>
                <span className="progress-step-who">{stage.담당}</span>
                {stage.완료 ? (
                  <button type="button" className="krds-btn small tertiary" disabled={saving} onClick={() => mark(stage.번호, false)}>
                    되돌리기<span className="sr-only"> {stage.이름}</span>
                  </button>
                ) : (
                  <button type="button" className="krds-btn small secondary" disabled={saving} aria-expanded={marking === stage.번호}
                          onClick={() => { setMarking(marking === stage.번호 ? null : stage.번호); setNote(""); setMarkError(null); }}>
                    완료로 표시<span className="sr-only"> {stage.이름}</span>
                  </button>
                )}
              </div>
              {stage.완료 && (
                <p className="progress-step-done">{stage["완료한 사람"]}, {dateOnly(stage["완료 시각"])}{stage.메모 && <span className="meta"> {stage.메모}</span>}</p>
              )}
              <p className="meta">
                근거 기록: {stage.내용 ? <>{stage.내용}{stage.일시 && ` (${dateOnly(stage.일시)})`}</> : "없음"}
                <Link className="progress-step-link" to={stage.경로}>{stage.기능} 열기</Link>
              </p>
              {marking === stage.번호 && !stage.완료 && (
                <form className="progress-mark" onSubmit={(e) => { e.preventDefault(); mark(stage.번호, true); }}>
                  <label htmlFor={`mark-note-${stage.번호}`}>메모(선택)</label>
                  <input id={`mark-note-${stage.번호}`} type="text" className="krds-input" maxLength={300} value={note} autoFocus
                         placeholder="예: 직능연 승인 확인" onChange={(e) => setNote(e.target.value)} />
                  <button type="submit" className="krds-btn medium primary" disabled={saving}>{saving ? "저장하는 중" : "완료로 표시"}</button>
                  <button type="button" className="krds-btn medium tertiary" disabled={saving} onClick={() => setMarking(null)}>취소</button>
                </form>
              )}
            </div>
          </li>
        ))}
      </ol>

      {detail.이력.length > 0 && (
        <details className="progress-history">
          <summary>완료 표시 이력 {detail.이력.length}건</summary>
          <div className="krds-table-wrap">
            <table className="tbl col data">
              <caption>단계 완료 표시와 되돌림 이력</caption>
              <thead><tr><th scope="col">때</th><th scope="col">단계</th><th scope="col">한 일</th><th scope="col">사람</th><th scope="col">메모</th></tr></thead>
              <tbody>
                {detail.이력.map((row, i) => (
                  <tr key={i}>
                    <td>{day(row.at)}</td><td>{row.stage}. {detail.단계.find((x) => x.번호 === row.stage)?.이름}</td>
                    <td>{row.action === "done" ? "완료로 표시" : "되돌림"}</td><td>{row.by}</td><td>{row.note || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      <h3 className="table-title" id="progress-numbers-title">검수 진행도 <span className="meta">남아 있는 기록에서 모은 값</span></h3>
      <dl className="upscale-summary" aria-labelledby="progress-numbers-title">
        <div>
          <dt>편집 검수</dt>
          {editing.항목 ? (
            <>
              <dd><strong>{editing["적합 비율"] ?? "-"}</strong>% 적합</dd>
              <dd className="meta">적합 {editing.항목.적합}, 부적합 {editing.항목.부적합}, 판단불가 {editing.항목.판단불가}</dd>
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
              <dd className="meta">집필료 {volume.fee.toLocaleString()}원, {dateOnly(volume.created_at)} 산정</dd>
            </>
          ) : <dd className="meta">기록 없음</dd>}
        </div>
      </dl>

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
