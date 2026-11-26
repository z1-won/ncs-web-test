// 원고 진행 현황(REQ-02-007 '원고별 편집·내용·저작권 검수 진행도 확인') — 원고(모듈 코드)마다 남은 기록을 단계 7개와 진행도로 보여 준다.
// 단계의 완료는 담당자가 여기서 직접 표시한다(누가·언제·메모, 되돌릴 수 있고 이력이 남는다). 기록은 완료를 판단할 근거로 옆에 보일 뿐이다.
// 누가 표시했는지는 로그인한 계정에서 서버가 읽는다(화면에서 이름을 받지 않는다).
// 화면 짜임은 이미지 저작권 DB와 같다: 위쪽 입력 묶음(모듈 코드로 열기) → 목록 → 고른 원고의 상세가 목록 아래에 열리고 [닫기].
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

const STAGE_COUNT = 7;
const CHECK_LABEL = Object.fromEntries(CHECKS.map((c) => [c.value, c.label]));
const CHECK_ORDER = CHECKS.map((c) => c.value);   // 편집 검수 표는 확인서 순서로
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

// 남은 일 한 칸 — 편집·내용·저작권 검수를 모두 "남은 것 / 전체"로 보인다(서버 progress.remaining과 같은 값).
// left: {남음, 전체, …} 또는 null(기록 없음). unit: 전체 뒤에 붙는 말('항목', '개'). what: 남은 것의 이름('부적합', '미반영')
// 배지 색은 검수 결과 배지(components/Badge.jsx)와 같은 규칙: 남은 것이 없으면 적합의 초록, 남아 있으면 부적합의 빨강.
// 크기도 KRDS 배지 그대로(기본, 요약 칸의 큰 줄에서는 large) — 글자 크기를 따로 바꾸지 않는다
export function Remaining({ left, what, unit, extra, large = false }) {
  if (!left || left.전체 == null) return <span className="meta">{extra || "기록 없음"}</span>;   // 권리 증빙만 점검한 원고는 누락 수만 보인다
  const clear = left.남음 === 0;
  return (
    <span className="progress-left">
      <span className={`krds-badge ${large ? "large " : ""}${clear ? "bg-light-success" : "bg-light-danger"}`}>{what} {left.남음}</span>
      <span className="progress-left-total"> / {left.전체}{unit}</span>
      {extra && <span className="meta">{extra}</span>}
    </span>
  );
}

// 남은 일의 덧붙임 글(판단불가, 확인 필요, 증빙 누락) — 목록과 상세가 같은 글을 쓴다
export function leftNotes(left) {
  const editing = left?.["편집 검수"], content = left?.["내용 검수"], rights = left?.["저작권 검수"];
  return {
    editing: [editing?.판단불가 ? `판단불가 ${editing.판단불가}` : "", editing?.쪽 ? `쪽 기준 완료 ${editing.쪽.완료}/${editing.쪽.전체}` : ""].filter(Boolean).join(", "),
    content: content ? (content.확정 ? "담당자 확정 기준" : `담당자 확정 전${content["확인 필요"] ? `, 확인 필요 ${content["확인 필요"]}` : ""}`) : "",
    rights: rights?.["증빙 누락"] != null ? `권리 증빙 누락 ${rights["증빙 누락"]}` : "",
  };
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
        window.scrollTo(0, 0);      // 원고 하나만 보이는 화면으로 바뀌므로 맨 위에서 시작한다
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
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page progress-page">
      {/* 원고를 하나 열면 그 원고의 이름이 페이지 제목이다 — 목록용 설명은 빼고, 목록으로 돌아가는 버튼을 제목 줄 오른쪽에 둔다 */}
      {code ? (
        <div className="page-head-row">
          <h1 className="page-title">
            {detail ? (detail.학습모듈명 || detail.module_code) : "원고 진행 현황"}
            {detail?.학습모듈명 && <span className="meta">{detail.module_code}</span>}
          </h1>
          <button type="button" className="krds-btn small tertiary" onClick={() => setParams({})}>원고 목록으로</button>
        </div>
      ) : (
        <>
        <h1 className="page-title">원고 진행 현황</h1>
        <p className="page-desc">
          원고마다 편집, 내용, 저작권 검수에서 남은 일과 단계 7개의 완료 여부를 보여 줍니다. 숫자는 가장 최근 검수 기록에서 모은 값이고, 단계의 완료는 담당자가 직접 표시합니다.
        </p>
        </>
      )}

      {history === null && <Spinner label="기록을 확인하는 중" />}
      {history === false && <PageAlert kind="info">데이터베이스가 연결된 서버에서만 진행 현황을 볼 수 있습니다. 관리자에게 문의해 주세요.</PageAlert>}

      {/* 원고를 하나 열면(?code=) 그 원고만 보인다 — 코드 입력 칸과 목록은 접는다. 목록으로는 상세의 [원고 목록으로]로 돌아간다 */}
      {history && !code && (
        <form className="fieldset review-form is-sectioned" onSubmit={openTyped}>
          <div className="form-section-grid">
            <div className="form-group">
              <div className="form-tit"><label htmlFor="progress-code">모듈 코드로 원고 열기</label></div>
              <div className="form-conts progress-open">
                <input id="progress-code" type="text" className="krds-input" placeholder="예: LM1203020201_24v3" value={typed}
                       onChange={(e) => setTyped(e.target.value)} aria-describedby="progress-code-hint" />
                <button type="submit" className="krds-btn medium secondary" disabled={!typed.trim()}>열기</button>
              </div>
              <p className="form-hint" id="progress-code-hint">아직 기록이 없는 원고도 열어서 단계를 표시할 수 있습니다. 파일 이름에 모듈 코드가 있는 원고의 기록만 모입니다.</p>
            </div>
          </div>
        </form>
      )}

      {history && !code && (
        <section id="progress-list" className="nav-anchor">
          <div className="section-head">
            <h2 className="section-title">원고 목록{list ? <span className="meta"> {list.length}건, 최근 기록순</span> : null}</h2>
          </div>
          <PageAlert kind="danger">{listError}</PageAlert>
          {!list && !listError && <Spinner label="목록을 읽는 중" />}
          {list && (list.length === 0 ? (
            <p className="empty">아직 기록이 없습니다. 파일 이름에 모듈 코드(LM으로 시작)가 있는 원고로 검수나 산정을 하면 여기에 모입니다.</p>
          ) : (
            <>
            <ListSummary list={list} />
            <div className="krds-table-wrap">
              <table className="tbl col data progress-table">
                <caption>원고마다 남은 일(남은 것 / 전체)과 완료한 단계</caption>
                <thead>
                  <tr><th scope="col">학습모듈</th><th scope="col">편집 검수</th><th scope="col">내용 검수</th><th scope="col">저작권 검수</th>
                      <th scope="col">완료한 단계</th><th scope="col">최근 기록</th><th scope="col">열기</th></tr>
                </thead>
                <tbody>
                  {list.map((row) => (
                    <tr key={row.module_code} className={row.module_code === code ? "is-open" : ""}>
                      <th scope="row">{row.name || row.module_code}{row.name && <span className="meta">{row.module_code}</span>}</th>
                      <td><Remaining left={row["남은 일"]?.["편집 검수"]} what="부적합" unit="항목" extra={leftNotes(row["남은 일"]).editing} /></td>
                      <td><Remaining left={row["남은 일"]?.["내용 검수"]} what="미반영" unit="개" extra={leftNotes(row["남은 일"]).content} /></td>
                      <td><Remaining left={row["남은 일"]?.["저작권 검수"]} what="정정 필요" unit="개" extra={leftNotes(row["남은 일"]).rights} /></td>
                      <td><StageBar done={row.stages_done} /></td>
                      <td>{dateOnly(row.last_at)}<span className="meta">기록 {row.records}건</span></td>
                      <td>
                        <button type="button" className="krds-btn small tertiary" aria-pressed={row.module_code === code}
                                aria-label={`${row.name || row.module_code} 열기`} onClick={() => setParams({ code: row.module_code })}>열기</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          ))}
        </section>
      )}

      <div id="progress-detail" className="nav-anchor">
        {loading && <Spinner label="진행 현황을 불러오는 중" />}
        <PageAlert kind="danger">{detailError}</PageAlert>
        {detail && !loading && (
          <ProgressDetail detail={detail}
                          onChange={(next) => { setDetail(next); refreshList(); }} />
        )}
      </div>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

// 목록 위 한 줄 — 보이는 원고 가운데 남은 일이 있는 권 수. 사업 담당자가 가장 먼저 찾는 값
function ListSummary({ list }) {
  const has = (row, key) => (row["남은 일"]?.[key]?.남음 || 0) > 0;
  const none = (row, key) => !row["남은 일"]?.[key] || row["남은 일"][key].전체 == null;
  const parts = [["편집 검수", "부적합이 남은 원고"], ["내용 검수", "미반영 의견이 남은 원고"], ["저작권 검수", "정정이 필요한 원고"]];
  return (
    <dl className="upscale-summary progress-summary" aria-label="원고 전체 요약">
      <div><dt>원고</dt><dd><strong>{list.length}</strong>권</dd></div>
      {parts.map(([key, label]) => (
        <div key={key}>
          <dt>{label}</dt>
          <dd><strong>{list.filter((row) => has(row, key)).length}</strong>권</dd>
          <dd className="meta">{key} 기록 없음 {list.filter((row) => none(row, key)).length}권</dd>
        </div>
      ))}
    </dl>
  );
}

function ProgressDetail({ detail, onChange }) {
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

  return (
    <section className="progress-detail" aria-label={`${detail.학습모듈명 || detail.module_code} 진행 현황`}>
      {/* 읽는 순서: 남은 일(요약) → 단계(지금 어디인가) → 구성요소·차수별 표(자세한 값) */}
      <ProgressSummary detail={detail} />

      {detail.건 ? (
        <PageAlert kind="info">
          이 원고는 세분류 건 ‘{detail.건.name} {detail.건.year}년’에 들어 있습니다. 단계는 건 화면에서 진행합니다.{" "}
          <Link to={`/cases?case=${detail.건.case_id}&volume=${detail.건.volume_id}`}>건 화면에서 이 권 열기</Link>
        </PageAlert>
      ) : (
        <>
      <h3 className="table-title" id="progress-steps-title">단계 <span className="meta">{detail["단계 근거"]}</span></h3>
      <p className="progress-overall"><StageBar done={detail["완료 단계 수"]} /></p>
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
                {/* 오른쪽 자리는 줄마다 같다: 그 단계의 기능 열기 → 완료 표시(또는 되돌리기). 자주 쓰는 '열기'가 버튼이고 되돌리기는 글자 버튼으로 약하게 */}
                <span className="progress-step-actions">
                  <Link className="krds-btn small tertiary" to={stage.경로}>{stage.기능} 열기</Link>
                  {stage.완료 ? (
                    <button type="button" className="krds-btn small text" disabled={saving} onClick={() => mark(stage.번호, false)}>
                      되돌리기<span className="sr-only"> {stage.이름}</span>
                    </button>
                  ) : (
                    <button type="button" className="krds-btn small secondary" disabled={saving} aria-expanded={marking === stage.번호}
                            onClick={() => { setMarking(marking === stage.번호 ? null : stage.번호); setNote(""); setMarkError(null); }}>
                      완료로 표시<span className="sr-only"> {stage.이름}</span>
                    </button>
                  )}
                </span>
              </div>
              {stage.완료 && (
                <p className="progress-step-done">{stage["완료한 사람"]}, {dateOnly(stage["완료 시각"])}{stage.메모 && <span className="meta"> {stage.메모}</span>}</p>
              )}
              <p className="meta">근거 기록: {stage.내용 ? <>{stage.내용}{stage.일시 && ` (${dateOnly(stage.일시)})`}</> : "없음"}</p>
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

        </>
      )}
      <ProgressTables detail={detail} />
    </section>
  );
}

// 남은 일 칸의 내역 한 줄 — 이름(왼쪽, 한 열로 맞춤)과 값(오른쪽)
function Row({ label, children }) {
  return <dd className="progress-row"><span className="progress-row-label">{label}</span><span className="progress-row-value">{children}</span></dd>;
}

// 검수 진행도 — 남아 있는 기록에서 모은 값(편집·내용·저작권 검수, 분량)과 그 표. 세분류 건의 권 화면은 둘을 이어서 쓴다
export function ProgressFigures({ detail }) {
  return <><ProgressSummary detail={detail} /><ProgressTables detail={detail} /></>;
}

// 남은 일 — 칸 넷(편집 검수, 내용 검수, 저작권 검수, 원고 분량)
export function ProgressSummary({ detail }) {
  const progress = detail.진행도;
  const editing = progress["편집 검수"];
  const content = progress["내용 검수"];
  const rights = progress["저작권 검수"]["권리 증빙"];
  const images = progress["저작권 검수"]["이미지 저작권 DB"];
  const figures = progress["저작권 검수"]["그림 검수"];      // 그림 검수(REQ-02-005)의 가장 최근 개수
  const cited = progress["저작권 검수"]["출처 검토"];        // 출처 검토(REQ-02-008)의 가장 최근 개수
  const copyright = progress["저작권 검수"].합계;            // 총 저작권 개수 / 정정 필요 개수(그림 + 출처)
  const confirmed = content.확정;                           // 의견 반영 검토의 담당자 확정
  const volume = progress.분량;
  const left = detail["남은 일"] || {};                       // 서버 progress.remaining — 목록과 같은 값
  // 칸의 첫 줄: 남은 것 / 전체. 기록이 없는 칸은 네 칸 모두 같은 작은 글 '기록 없음' 한 줄로 맞춘다
  const head = (key, what, unit) => (left[key]?.전체 != null
    ? <dd className="progress-headline"><Remaining left={left[key]} what={what} unit={unit} large /></dd>
    : <dd className="progress-empty">기록 없음</dd>);
  const unread = figures ? Math.max(0, (figures["검수 대상"] ?? figures.그림 ?? 0) - (figures.고위험 || 0) - (figures["확인 필요"] || 0) - (figures.문제없음 || 0)) : 0;
  return (
    <>
      <h3 className="table-title" id="progress-numbers-title">남은 일 <span className="meta">가장 최근 검수 기록에서 모은 값(남은 것 / 전체)</span></h3>
      {/* 칸 안의 글은 세 층: 이름(굵게) → 남은 것 / 전체(큰 글) → 구분선 아래 내역 줄(작은 글, '무엇 | 값'). 내역 줄의 이름은 한 열로 맞춘다 */}
      <dl className="upscale-summary progress-summary" aria-labelledby="progress-numbers-title">
        <div className={left["편집 검수"]?.전체 != null ? "" : "is-empty"}>
          <dt>편집 검수</dt>
          {head("편집 검수", "부적합", "항목")}
          {editing.항목 && <Row label="판정">적합 {editing.항목.적합}, 부적합 {editing.항목.부적합}, 판단불가 {editing.항목.판단불가}</Row>}
          {editing.쪽 && (
            <Row label="쪽 기준">
              진행완료 {editing.쪽.완료}쪽 / 총 {editing.쪽.전체}쪽
              <span className="progress-row-note">부적합이 놓인 쪽 {editing.쪽.남음}쪽{editing.쪽["못 찾은 항목"] > 0 && `, 자리를 찾지 못한 부적합 ${editing.쪽["못 찾은 항목"]}개는 뺌`}</span>
            </Row>
          )}
          {editing.항목?.판단불가 > 0 && <dd className="progress-note">판단불가는 담당자가 확인할 항목입니다.</dd>}
        </div>
        <div className={left["내용 검수"]?.전체 != null || content.합계 ? "" : "is-empty"}>
          <dt>내용 검수(의견 반영)</dt>
          {head("내용 검수", "미반영", "개")}
          {content.합계 && (
            <>
              <Row label="의견">{content.합계["총 의견"]}개: 반영 후보 {content.합계["반영 후보"]}, 미반영 후보 {content.합계["미반영 후보"]}, 확인 필요 {content.합계["확인 필요"]}</Row>
              <Row label="담당자 확정">{confirmed
                ? `${confirmed.확정}개: 반영 ${confirmed.반영}, 미반영 ${confirmed.미반영}${confirmed.오차율 ? ` (후보 대비 오차율 ${confirmed.오차율})` : ""}`
                : "확정 전"}</Row>
            </>
          )}
        </div>
        <div>
          <dt>저작권 검수</dt>
          {copyright ? head("저작권 검수", "정정 필요", "개") : <dd className="progress-empty">그림 검수와 출처 검토 기록 없음</dd>}
          {figures && <Row label="그림 검수">{figures.그림}개: 고위험 {figures.고위험}, 확인 필요 {figures["확인 필요"]}, 문제없음 {figures.문제없음}{unread > 0 && <span className="progress-row-note">그림 판독 전이라 판정하지 않은 그림 {unread}개</span>}</Row>}
          {cited && <Row label="출처 검토">{cited["총 출처"]}개: 부적합 {cited.부적합}, 판단불가 {cited.판단불가}, 적합 {cited.적합}</Row>}
          <Row label="권리 증빙">{rights
            ? <><b className={rights.판정 === "적합" ? "" : "progress-flag"}>{rights.판정}</b>, 원고 그림 {rights["원고 그림"] ?? "-"}개 중 누락 {rights.누락 ?? "-"}건, 확인 필요 {rights["확인 필요"] ?? "-"}건</>
            : "점검 기록 없음"}</Row>
          <Row label="이미지 DB">그림 {images.그림}개 중 확정 {images.확정}개</Row>
        </div>
        <div className={volume ? "" : "is-empty"}>
          <dt>원고 분량</dt>
          {volume ? (
            <>
              <dd className="progress-headline"><strong>{volume.pages}</strong>매{volume.estimated && " (추정)"}</dd>
              <Row label="집필료">{volume.fee.toLocaleString()}원</Row>
              <Row label="산정한 날">{dateOnly(volume.created_at)}</Row>
            </>
          ) : <dd className="progress-empty">기록 없음</dd>}
        </div>
      </dl>
    </>
  );
}

// 구성요소별(편집 검수), 차수별(내용 검수) 표 — 숫자 열은 가운데로 맞추고 검수한 때는 날짜만 적는다(시각까지는 검수 이력에 있다)
export function ProgressTables({ detail }) {
  const editing = detail.진행도["편집 검수"];
  const content = detail.진행도["내용 검수"];
  return (
    <>
      {editing.구성요소.length > 0 && (
        <>
          <h3 className="table-title" id="progress-editing-title">편집 검수 <span className="meta">구성요소마다 가장 최근 검수의 확인서 항목 수</span></h3>
          <div className="krds-table-wrap">
            <table className="tbl col data progress-numbers" aria-labelledby="progress-editing-title">
              <thead><tr><th scope="col">구성요소</th><th scope="col">판정</th><th scope="col">적합</th><th scope="col">부적합</th><th scope="col">판단불가</th><th scope="col">검수한 때</th></tr></thead>
              <tbody>
                {[...editing.구성요소].sort((a, b) => CHECK_ORDER.indexOf(a.검수) - CHECK_ORDER.indexOf(b.검수)).map((row) => (
                  <tr key={row.검수}>
                    <th scope="row">{CHECK_LABEL[row.검수] || row.검수}</th><td><Badge value={row.판정} /></td>
                    <td>{row.적합}</td><td>{row.부적합}</td><td>{row.판단불가}</td><td>{dateOnly(row.일시)}</td>
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
            <table className="tbl col data progress-numbers" aria-labelledby="progress-content-title">
              <thead><tr><th scope="col">차수</th><th scope="col">총 의견</th><th scope="col">반영 후보</th><th scope="col">미반영 후보</th><th scope="col">확인 필요</th><th scope="col">조치 불필요</th><th scope="col">검토한 때</th></tr></thead>
              <tbody>
                {content.차수.map((row) => (
                  <tr key={row.차수}>
                    <th scope="row">{row.차수}</th><td>{row["총 의견"]}</td><td>{row["반영 후보"]}</td><td>{row["미반영 후보"]}</td>
                    <td>{row["확인 필요"]}</td><td>{row["조치 불필요"]}</td><td>{dateOnly(row.일시)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="meta">의견 문장과 원고 문단은 저장하지 않고 개수만 남깁니다. 반영 후보와 미반영 후보는 담당자가 확정하기 전의 값입니다.</p>
        </>
      )}
    </>
  );
}
