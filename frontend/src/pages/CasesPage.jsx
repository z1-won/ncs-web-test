// 세분류 건(REQ-02-007) — 주문의 단위는 세분류 한 건이다. 건을 만들고(세분류 코드 → NCS 목록의 학습모듈이 권이 된다) 권마다 담당 집필자를 붙인다.
// 단계의 상태는 서버가 사건 기록을 접어서 준다(ncs_service.flow). 이 화면은 상태를 따로 계산하지 않고 받은 것을 보이기만 한다.
// 에디터와 직능연은 모든 건을 보고 만들 수 있다. 집필진은 자기가 담당인 권이 든 건만, 그 권만 본다(서버가 거른다).
// 일은 건 안에서 이어진다: 내 할 일 → 건 → 권 → 지금 단계에서 제출(원고 판본) → 검수(그 판본에 붙음) → 보완 요청 또는 완료 → 다음 단계.
// 화면 짜임: 내 할 일 → 건 만들기(접어 둠) → 건 목록 → 고른 건의 상세(권 목록) → 고른 권의 단계. 고른 건과 권은 주소(?case=&volume=)에 남는다.
import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.jsx";
import { Badge, Spinner } from "../components/Badge.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { ProgressFigures } from "./ProgressPage.jsx";

const ANCHORS = [{ id: "cases-list", label: "건 목록" }, { id: "cases-detail", label: "권과 단계" }];
const DONE = "완료", WAITING = "대기";
const CHECK_NAMES = { toc: "차례", overview: "개요", knowledge: "필요 지식", perform: "수행 내용", teaching: "교수학습 방법", evaluation: "평가",
                      references: "참고 자료", colophon: "판권", misc: "기타" };
const TOOLS = { opinion: ["/opinion", "의견 반영 검토"], volume: ["/volume", "원고 분량"], rights: ["/rights", "권리 증빙 점검"] };
const sizeText = (bytes) => (bytes >= 1 << 20 ? `${(bytes / (1 << 20)).toFixed(1)}MB` : `${Math.max(1, Math.round(bytes / 1024))}KB`);
const when = (iso) => (iso ? formatDate(iso) : "");

// 권 단계 진도 — 처음 화면과 진행 현황의 단계 막대와 같은 모양(칸 수는 고정 10, 비율로 채운다)
function ProgressBar({ done, total }) {
  const cells = 10;
  const on = total ? Math.round((done / total) * cells) : 0;
  return (
    <span className="home-recent-steps" aria-label={`완료한 단계 ${done}, 전체 ${total}`}>
      {Array.from({ length: cells }, (_, i) => <i key={i} className={i < on ? "is-on" : ""} aria-hidden="true" />)}
      <b>완료 {done} / {total}</b>
    </span>
  );
}

function CreateForm({ options, onCreated }) {
  const [subclass, setSubclass] = useState("");
  const [year, setYear] = useState(String(options.year));
  const [improvement, setImprovement] = useState(options.improvements[0]);
  const [listing, setListing] = useState(null);       // { name, volumes } — 세분류 코드로 찾은 NCS 목록
  const [picked, setPicked] = useState({});           // 모듈 코드 → 건에 넣을지
  const [busy, setBusy] = useState(null);             // "lookup" | "create"
  const [error, setError] = useState(null);
  const code = subclass.trim();
  const chosen = listing ? listing.volumes.filter((v) => picked[v.module_code]) : [];

  async function lookup(event) {
    event.preventDefault();
    setBusy("lookup");
    setError(null);
    const { ok, data, error: message } = await api.cases.lookup(code);
    setBusy(null);
    if (!ok) { setListing(null); setError(message); return; }
    if (!data.volumes.length) { setListing(null); setError("NCS 목록에 없는 세분류 코드입니다. 코드 8자리를 다시 확인해 주세요."); return; }
    setListing(data);
    setPicked(Object.fromEntries(data.volumes.map((v) => [v.module_code, true])));
  }

  async function create() {
    setBusy("create");
    setError(null);
    const { ok, data, error: message } = await api.cases.create({ subclass: listing.subclass, year: Number(year), improvement, name: listing.name, volumes: chosen });
    setBusy(null);
    if (!ok) { setError(message); return; }
    setSubclass("");
    setListing(null);
    onCreated(data);
  }

  return (
    <form className="fieldset review-form is-sectioned" onSubmit={lookup}>
      <div className="form-section-grid cases-create">
        <div className="form-group">
          <div className="form-tit"><label htmlFor="case-subclass">세분류 코드</label></div>
          <div className="form-conts progress-open">
            <input id="case-subclass" type="text" inputMode="numeric" className="krds-input" placeholder="예: 12030202" maxLength={8} value={subclass}
                   onChange={(e) => { setSubclass(e.target.value.replace(/\D/g, "")); setListing(null); }} aria-describedby="case-subclass-hint" />
            <button type="submit" className="krds-btn medium secondary" disabled={code.length !== 8 || !!busy}>{busy === "lookup" ? "찾는 중" : "권 불러오기"}</button>
          </div>
          <p className="form-hint" id="case-subclass-hint">모듈 코드에서 LM 다음의 숫자 8자리입니다. NCS 목록에서 그 세분류의 학습모듈을 불러옵니다.</p>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="case-year">사업 연도</label></div>
          <div className="form-conts">
            <input id="case-year" type="number" className="krds-input" min={2000} max={2100} value={year} onChange={(e) => setYear(e.target.value)} />
          </div>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="case-improvement">개선 유형</label></div>
          <div className="form-conts">
            <select id="case-improvement" className="krds-form-select completed" value={improvement} onChange={(e) => setImprovement(e.target.value)}>
              {options.improvements.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </div>
        </div>
      </div>
      <PageAlert kind="danger">{error}</PageAlert>
      {listing && (
        <div className="cases-pick">
          <h3 className="table-title">{listing.name} <span className="meta">{listing.subclass}, 학습모듈 {listing.volumes.length}권 중 {chosen.length}권 선택</span></h3>
          <ul className="cases-pick-list">
            {listing.volumes.map((volume) => (
              <li key={volume.module_code}>
                <div className="krds-form-check medium">
                  <input type="checkbox" id={`pick-${volume.module_code}`} checked={!!picked[volume.module_code]}
                         onChange={(e) => setPicked((prev) => ({ ...prev, [volume.module_code]: e.target.checked }))} />
                  <label htmlFor={`pick-${volume.module_code}`}>{volume.title} <span className="meta">{volume.module_code}</span></label>
                </div>
              </li>
            ))}
          </ul>
          <div className="form-actions">
            <button type="button" className="krds-btn large primary" disabled={!chosen.length || !!busy} onClick={create}>{busy === "create" ? "만드는 중" : "건 만들기"}</button>
          </div>
        </div>
      )}
    </form>
  );
}

export default function CasesPage() {
  usePageTitle("세분류 건");
  const [params, setParams] = useSearchParams();
  const caseId = params.get("case") || "";
  const volumeId = params.get("volume") || "";
  const [history, setHistory] = useState(null);       // null: 확인 중, false: DB 없음
  const [list, setList] = useState(null);             // { cases, can_manage }
  const [listError, setListError] = useState(null);
  const [todo, setTodo] = useState(null);
  const [options, setOptions] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [loading, setLoading] = useState(false);
  const detailBox = useRef(null);

  async function refreshList() {
    const [{ ok, data, error }, mine] = await Promise.all([api.cases.list(), api.cases.todo()]);
    if (mine.ok) setTodo(mine.data);
    if (!ok) { setListError(error); return; }
    setList(data);
    setListError(null);
    if (data.can_manage) {
      const found = await api.cases.options();
      if (found.ok) setOptions(found.data);
    }
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
    if (!caseId || history !== true) { setDetail(null); setDetailError(null); return undefined; }
    if (detail?.id === caseId) return undefined;      // 같은 건 안에서 권만 바꿀 때는 다시 읽지 않는다
    let alive = true;
    setLoading(true);
    setDetailError(null);
    (async () => {
      const { ok, data, error } = await api.cases.get(caseId);
      if (!alive) return;
      setLoading(false);
      if (ok) {
        setDetail(data);
        requestAnimationFrame(() => detailBox.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
      } else { setDetail(null); setDetailError(error); }
    })();
    return () => { alive = false; };
  }, [caseId, history]);   // eslint-disable-line react-hooks/exhaustive-deps

  const open = (next) => setParams(next.volume ? { case: next.case, volume: next.volume } : { case: next.case });
  const cases = list?.cases;
  return (
    <>
    <Header anchors={ANCHORS} />
    <main id="main" className="inner page">
      <h1 className="page-title">세분류 건</h1>
      <p className="page-desc">세분류 한 건이 일의 단위입니다. 권마다 단계를 순서대로 지나고, 제출과 확인이 오갈 때마다 누가 언제 무엇을 했는지 기록에 남습니다.</p>

      {history === null && <Spinner label="기록을 확인하는 중" />}
      {history === false && <PageAlert kind="info">데이터베이스가 연결된 서버에서만 세분류 건을 쓸 수 있습니다. 관리자에게 문의해 주세요.</PageAlert>}

      {history && todo && (
        <section className="cases-todo" aria-labelledby="cases-todo-title">
          <div className="section-head">
            <h2 className="section-title" id="cases-todo-title">내 할 일<span className="meta"> {todo.length}건</span></h2>
          </div>
          {todo.length === 0 ? <p className="empty">지금 내 차례인 일이 없습니다.</p> : (
            <ul className="cases-todo-list">
              {todo.map((item) => (
                <li key={`${item.case_id}-${item.volume_id || item.stage}`}>
                  <div>
                    <strong>{item.title}</strong> <span className="meta">{item.case_name} {item.year}년{item.module_code ? `, ${item.module_code}` : ""}</span>
                    <p>{item.stage_name}: {item.todo}{item.proxy && <span className="meta"> {item.turn.join(", ")} 차례이며 대신 기록할 수 있습니다.</span>}</p>
                    {item.note && <p className="meta">보완 요청 메모: {item.note}</p>}
                  </div>
                  <button type="button" className="krds-btn small secondary" onClick={() => open({ case: item.case_id, volume: item.volume_id })}>열기</button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {history && list?.can_manage && options && (
        <details className="cases-new">
          <summary>새 건 만들기</summary>
          <CreateForm options={options} onCreated={(created) => { setDetail(created); refreshList(); open({ case: created.id }); }} />
        </details>
      )}

      {history && (
        <section id="cases-list" className="nav-anchor">
          <div className="section-head">
            <h2 className="section-title">건 목록{cases ? <span className="meta"> {cases.length}건</span> : null}</h2>
          </div>
          <PageAlert kind="danger">{listError}</PageAlert>
          {!list && !listError && <Spinner label="목록을 읽는 중" />}
          {cases && (cases.length === 0 ? (
            <p className="empty">{list.can_manage ? "아직 만든 건이 없습니다. ‘새 건 만들기’에서 세분류 코드로 건을 만들어 주세요." : "담당으로 정해진 권이 아직 없습니다. 에디터가 권에 담당을 정하면 여기에 나타납니다."}</p>
          ) : (
            <div className="krds-table-wrap">
              <table className="tbl col data progress-table">
                <caption>세분류 건과 권 단계 진도</caption>
                <thead>
                  <tr><th scope="col">세분류</th><th scope="col">사업 연도</th><th scope="col">개선 유형</th><th scope="col">권</th><th scope="col">권 단계 진도</th><th scope="col">열기</th></tr>
                </thead>
                <tbody>
                  {cases.map((row) => (
                    <tr key={row.id} className={row.id === caseId ? "is-open" : ""}>
                      <th scope="row">{row.name || row.subclass}{row.name && <span className="meta">{row.subclass}</span>}</th>
                      <td>{row.year}</td>
                      <td>{row.improvement}</td>
                      <td>{row.volumes}권<span className="meta">담당 정함 {row.assigned}권</span></td>
                      <td><ProgressBar done={row.progress.done} total={row.progress.total} /></td>
                      <td>
                        <button type="button" className="krds-btn small tertiary" aria-pressed={row.id === caseId}
                                aria-label={`${row.name || row.subclass} ${row.year}년 건 열기`} onClick={() => open({ case: row.id })}>열기</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </section>
      )}

      <div id="cases-detail" ref={detailBox} className="nav-anchor">
        {loading && <Spinner label="건을 불러오는 중" />}
        <PageAlert kind="danger">{detailError}</PageAlert>
        {detail && !loading && (
          <CaseDetail detail={detail} authors={options?.authors || []} volumeId={volumeId}
                      onVolume={(id) => open({ case: detail.id, volume: id })}
                      onChange={(next) => { setDetail(next); refreshList(); }} onClose={() => setParams({})} />
        )}
      </div>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

// 단계 하나에서 할 수 있는 일: 메모, (원고를 올리는 단계의 제출이면) 파일, 행동 버튼. 검수하는 단계면 가장 최근 판본의 검수 실행과 결과.
function StageAction({ detail, volume, standing, onChange }) {
  const [note, setNote] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(null);             // 보내는 중인 행동, 또는 "review"
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(null);       // 검수 진행: { done, total, name }
  // 이미 제출된 것을 다른 역할이 대신 다시 내는 버튼은 보이지 않는다(확인할 차례에 제출 칸이 끼어들지 않게)
  const actions = standing.actions.filter((a) => !(a.action === "submit" && a.proxy && standing.state === "제출됨"));
  const canSubmitFile = standing.manuscript && actions.some((a) => a.action === "submit");
  const latest = volume ? (standing.manuscript ? volume.versions.find((v) => v.stage === standing.key) : volume.versions[0]) : null;
  const canReview = detail.can_manage && standing.review && latest && standing.state !== WAITING;
  const records = volume ? (volume.records[standing.key] || []) : [];
  const id = `act-${volume ? volume.id : "case"}-${standing.key}`;

  async function send(action) {
    setError(null);
    if (action.needs_note && !note.trim()) { setError("순서를 건너뛰어 완료하려면 사유를 메모에 적어 주세요."); return; }
    if (action.action === "submit" && standing.manuscript && !file) { setError("제출할 원고 파일을 골라 주세요."); return; }
    setBusy(action.action);
    const result = action.action === "submit" && standing.manuscript
      ? await api.cases.submitVersion(detail.id, volume.id, { stage: standing.key, note: note.trim(), file })
      : await api.cases.act(detail.id, { stage: standing.key, action: action.action, volumeId: volume ? volume.id : null, note: note.trim() });
    setBusy(null);
    if (!result.ok) { setError(result.error); return; }
    setNote("");
    setFile(null);
    onChange(result.data);
  }

  // 보관한 판본으로 원고 검수를 돌린다: 서버가 파일을 임시 업로드로 꺼내 주면, 원고만 있으면 되는 검수를 차례로 돌린다. 결과는 그 판본에 붙는다
  async function review() {
    setError(null);
    setBusy("review");
    const ready = await api.cases.versionUpload(detail.id, latest.id);
    if (!ready.ok) { setBusy(null); setError(ready.error); return; }
    const { upload, group, checks, module_code: moduleCode } = ready.data;
    const failed = [];
    for (let index = 0; index < checks.length; index += 1) {
      setRunning({ done: index, total: checks.length, name: CHECK_NAMES[checks[index]] || checks[index] });
      const result = await api.review({ check: checks[index], moduleCode, upload, group });
      if (!result.ok) failed.push(`${CHECK_NAMES[checks[index]] || checks[index]}: ${result.error}`);
    }
    await api.uploads.remove(upload);
    setRunning(null);
    setBusy(null);
    if (failed.length) setError(`검수 ${checks.length}개 중 ${failed.length}개를 마치지 못했습니다. ${failed[0]}`);
    const fresh = await api.cases.get(detail.id);
    if (fresh.ok) onChange(fresh.data);
  }

  return (
    <div className="cases-action">
      <p className="cases-action-state">
        <Badge value={standing.state} /> {standing.turn.length ? <span>{standing.turn.join(", ")} 차례입니다.</span> : null}
        {standing.by && <span className="meta"> 마지막 기록: {standing.by}, {when(standing.at)}</span>}
      </p>
      {standing.note && <p className="cases-action-note">메모: {standing.note}</p>}

      {latest && standing.review && (
        <div className="cases-review">
          <p>
            검수할 판본: <a href={api.cases.versionFileUrl(detail.id, latest.id)}>{latest.filename}</a> <span className="meta">{latest.stage_name} {latest.number}차, {latest.by}, {when(latest.at)}</span>
          </p>
          {latest.review ? (
            <p>
              검수 결과: <Badge value={latest.review.verdict} /> <span className="meta">검수 {latest.review.checks}개, {Object.entries(latest.review.counts).map(([k, n]) => `${k} ${n}`).join(", ")}, {when(latest.review.at)}</span>{" "}
              <Link to={`/review?group=${latest.review.group}`} className="krds-btn small text">결과 자세히 보기</Link>
            </p>
          ) : <p className="meta">이 판본은 아직 검수하지 않았습니다.</p>}
          {canReview && (
            <button type="button" className="krds-btn medium secondary" disabled={!!busy} onClick={review}>
              {running ? `검수 중 ${running.done + 1} / ${running.total}: ${running.name}` : latest.review ? "검수 다시 실행" : "이 판본으로 검수 실행"}
            </button>
          )}
        </div>
      )}

      {volume && standing.tools.length > 0 && (
        <div className="cases-review">
          <p>이 단계의 근거 기록{records.length === 0 && <span className="meta"> 아직 없습니다. 아래 도구를 여기서 열어 돌리면 이 단계에 붙습니다.</span>}</p>
          {records.length > 0 && (
            <ul className="cases-records">
              {records.map((record) => <li key={record.id}>{TOOLS[record.tool]?.[1] || record.tool}: {record.text} <span className="meta">{when(record.at)}</span></li>)}
            </ul>
          )}
          <p>
            {standing.tools.map((tool) => (
              <Link key={tool} className="krds-btn medium secondary" to={`${TOOLS[tool][0]}?case=${detail.id}&volume=${volume.id}&stage=${standing.key}&label=${encodeURIComponent(`${volume.title || volume.module_code}, ${standing.name}`)}`}>
                {TOOLS[tool][1]} 열기
              </Link>
            ))}
          </p>
        </div>
      )}

      {actions.length > 0 && (
        <form className="review-form cases-action-form" onSubmit={(e) => e.preventDefault()}>
          {canSubmitFile && (
            <FileSlot id={`${id}-file`} label="제출할 원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={!!busy}
                      hint="hwp, hwpx. 올린 파일은 판본으로 보관됩니다." />
          )}
          <div className="form-group">
            <div className="form-tit"><label htmlFor={`${id}-note`}>메모</label></div>
            <div className="form-conts">
              <input id={`${id}-note`} type="text" className="krds-input" maxLength={500} value={note} onChange={(e) => setNote(e.target.value)}
                     placeholder="보완 요청이면 무엇을 고칠지, 건너뛴 완료면 사유를 적습니다" />
            </div>
          </div>
          <div className="cases-action-buttons">
            {actions.map((action, index) => (
              <button key={`${action.action}-${action.needs_note}`} type="button" disabled={!!busy}
                      className={`krds-btn medium ${index === actions.length - 1 && !action.needs_note ? "primary" : "secondary"}`} onClick={() => send(action)}>
                {busy === action.action ? "보내는 중" : action.name}{action.proxy ? " (대신 기록)" : ""}
              </button>
            ))}
          </div>
        </form>
      )}
      {actions.length === 0 && standing.turn.length > 0 && <p className="meta">이 계정으로 할 일은 없습니다. {standing.turn.join(", ")}의 처리를 기다립니다.</p>}
      <PageAlert kind="danger">{error}</PageAlert>
    </div>
  );
}

// 권 하나: 단계를 순서대로(건 단위 단계 포함) 보이고, 지금 서 있는 단계에 할 일을 둔다. 아래에 판본과 이 권의 기록
function VolumePanel({ detail, volume, onChange, onClose }) {
  const [error, setError] = useState(null);
  const [figures, setFigures] = useState(null);       // 이 원고의 검수 진행도(편집·내용·저작권 검수, 분량) — 원고 진행 현황과 같은 값
  const current = volume.current;
  const stamp = `${volume.versions.length}-${volume.versions[0]?.review?.at || ""}-${Object.values(volume.records).flat().length}`;
  useEffect(() => {
    let alive = true;
    api.manuscripts.get(volume.module_code).then(({ ok, data }) => { if (alive && ok) setFigures(data); });
    return () => { alive = false; };
  }, [volume.module_code, stamp]);
  const stateOf = (stage) => (stage.unit === "건" ? detail.case_stages[stage.key] : volume.stages[stage.key]);
  const events = detail.events.filter((event) => event.volume_id === volume.id || (!event.volume_id && event.stage));

  async function reopen(stage) {
    setError(null);
    const { ok, data, error: message } = await api.cases.act(detail.id, { stage: stage.key, action: "reopen", volumeId: stage.unit === "건" ? null : volume.id, note: "" });
    if (ok) onChange(data); else setError(message);
  }

  return (
    <section className="cases-volume" aria-labelledby="cases-volume-title">
      <div className="section-head">
        <h3 className="table-title" id="cases-volume-title">{volume.title || volume.module_code} <span className="meta">{volume.module_code}, 담당 {volume.author ? volume.author.name : "없음"}</span></h3>
        <button type="button" className="krds-btn small tertiary" onClick={onClose}>권 닫기</button>
      </div>
      {!current && <PageAlert kind="success">이 권은 모든 단계를 마쳤습니다.</PageAlert>}
      <PageAlert kind="danger">{error}</PageAlert>
      <ol className="progress-steps">
        {detail.stages.map((stage, index) => {
          const state = stateOf(stage);
          const isCurrent = current?.key === stage.key;
          const canReopen = stage.unit === "건" ? detail.case_reopen.includes(stage.key) : volume.reopen.includes(stage.key);
          return (
            <li key={stage.key} className={`${state.state === DONE ? "is-done" : ""}${isCurrent ? " is-current" : ""}`} aria-current={isCurrent ? "step" : undefined}>
              <span className="progress-step-no" aria-hidden="true">{index + 1}</span>
              <div className="progress-step-body">
                <div className="progress-step-head">
                  <h4>{stage.name}</h4>
                  <span className="progress-step-who">{stage.unit === "건" ? "건 전체, " : ""}{stage.kind}. {stage.who}</span>
                  {!isCurrent && state.state !== WAITING && <Badge value={state.state} />}
                  {canReopen && <button type="button" className="krds-btn small text" onClick={() => reopen(stage)}>되돌리기</button>}
                </div>
                {!isCurrent && state.state === DONE && <p className="meta">{state.by}, {when(state.at)}{state.note ? `. ${state.note}` : ""}</p>}
                {isCurrent && <StageAction key={`${volume.id}-${stage.key}-${state.state}`} detail={detail} volume={stage.unit === "건" ? null : volume} standing={current} onChange={onChange} />}
              </div>
            </li>
          );
        })}
      </ol>

      <h4 className="table-title">판본 <span className="meta">{volume.versions.length}개. 제출한 원고 파일은 지우지 않고 보관합니다</span></h4>
      {volume.versions.length === 0 ? <p className="empty">아직 제출한 원고가 없습니다.</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data progress-table">
            <caption>이 권에 제출한 원고 판본과 검수 결과</caption>
            <thead><tr><th scope="col">단계</th><th scope="col">파일</th><th scope="col">제출</th><th scope="col">검수 결과</th></tr></thead>
            <tbody>
              {volume.versions.map((version) => (
                <tr key={version.id}>
                  <th scope="row">{version.stage_name}<span className="meta">{version.number}차 제출</span></th>
                  <td><a href={api.cases.versionFileUrl(detail.id, version.id)}>{version.filename}</a><span className="meta">{sizeText(version.byte_size)}</span></td>
                  <td>{version.by}<span className="meta">{when(version.at)}</span></td>
                  <td>{version.review ? (
                    <><Badge value={version.review.verdict} /> <Link to={`/review?group=${version.review.group}`} className="krds-btn small text">결과 보기</Link></>
                  ) : "검수 전"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h4 className="table-title">이 권의 기록 <span className="meta">최근 것부터. 지우거나 고칠 수 없습니다</span></h4>
      <EventTable events={events} showVolume={false} />
      {figures && <ProgressFigures detail={figures} />}
    </section>
  );
}

function EventTable({ events, showVolume }) {
  return (
    <div className="krds-table-wrap">
      <table className="tbl col data progress-table">
        <caption>누가 언제 무엇을 했는지</caption>
        <thead>
          <tr><th scope="col">일시</th><th scope="col">누가</th>{showVolume && <th scope="col">권</th>}<th scope="col">단계</th><th scope="col">무엇을</th><th scope="col">메모</th></tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td>{formatDate(event.at)}</td>
              <td>{event.actor}{event.proxy && <span className="meta">대신 기록</span>}</td>
              {showVolume && <td>{event.module_code || "건 전체"}</td>}
              <td>{event.stage_name || "-"}</td>
              <td>{event.action_name}{event.version_id ? " (원고 첨부)" : ""}</td>
              <td>{event.note || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CaseDetail({ detail, authors, volumeId, onVolume, onChange, onClose }) {
  const [saving, setSaving] = useState(null);         // 담당을 바꾸는 중인 권 id
  const [error, setError] = useState(null);
  const panel = useRef(null);
  const selected = detail.volumes.find((volume) => volume.id === volumeId) || null;
  // 건 단위 단계 가운데 지금 어느 권인가가 서 있는 것 — 건 화면에서 바로 처리한다
  const caseStanding = detail.stages.filter((stage) => stage.unit === "건" && detail.volumes.some((volume) => volume.current?.key === stage.key))
    .map((stage) => detail.case_actions[stage.key]);

  useEffect(() => {
    if (selected) requestAnimationFrame(() => panel.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
  }, [selected?.id]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function assign(volume, authorId) {
    setSaving(volume.id);
    setError(null);
    const { ok, data, error: message } = await api.cases.assignAuthor(detail.id, volume.id, authorId || null);
    setSaving(null);
    if (ok) onChange(data); else setError(message);
  }

  // 단계 하나의 진도: 건 단위는 그 상태, 권 단위는 상태별 권 수
  function stageProgress(stage) {
    if (stage.unit === "건") return detail.case_stages[stage.key]?.state || WAITING;
    const counts = {};
    detail.volumes.forEach((volume) => { const state = volume.stages[stage.key].state; counts[state] = (counts[state] || 0) + 1; });
    const others = Object.entries(counts).filter(([state]) => state !== DONE && state !== WAITING).map(([state, n]) => `${state} ${n}권`);
    return [`${detail.volumes.length}권 중 ${counts[DONE] || 0}권 완료`, ...others].join(", ");
  }

  return (
    <section className="progress-detail" aria-labelledby="case-detail-title">
      <div className="section-head">
        <h2 className="section-title" id="case-detail-title">
          {detail.name || detail.subclass} <span className="meta">{detail.subclass}, {detail.year}년, {detail.improvement}</span>
        </h2>
        <button type="button" className="krds-btn small tertiary" onClick={onClose}>닫기</button>
      </div>
      <p className="progress-overall"><ProgressBar done={detail.progress.done} total={detail.progress.total} /></p>

      {caseStanding.map((standing) => (
        <div key={standing.key} className="cases-case-stage">
          <h3 className="table-title">{standing.name} <span className="meta">건 전체가 함께 지나는 단계입니다. 끝나야 권들이 다음 단계로 갑니다</span></h3>
          <StageAction key={`case-${standing.key}-${standing.state}`} detail={detail} volume={null} standing={standing} onChange={onChange} />
        </div>
      ))}

      <h3 className="table-title">권 <span className="meta">{detail.volumes.length}권. 권을 열면 단계와 할 일이 나옵니다</span></h3>
      <PageAlert kind="danger">{error}</PageAlert>
      <div className="krds-table-wrap">
        <table className="tbl col data progress-table">
          <caption>권마다 담당 집필자, 지금 단계와 차례</caption>
          <thead>
            <tr><th scope="col">학습모듈</th><th scope="col">담당 집필자</th><th scope="col">지금 단계</th><th scope="col">누구 차례</th><th scope="col">완료한 단계</th><th scope="col">열기</th></tr>
          </thead>
          <tbody>
            {detail.volumes.map((volume) => (
              <tr key={volume.id} className={volume.id === volumeId ? "is-open" : ""}>
                <th scope="row">{volume.title || volume.module_code}{volume.title && <span className="meta">{volume.module_code}</span>}</th>
                <td>
                  {detail.can_manage ? (
                    <select className={`krds-form-select small${volume.author ? " completed" : ""}`} aria-label={`${volume.title || volume.module_code} 담당 집필자`} disabled={saving === volume.id}
                            value={volume.author?.id || ""} onChange={(e) => assign(volume, e.target.value)}>
                      <option value="">담당 없음</option>
                      {authors.map((author) => <option key={author.id} value={author.id}>{author.name}({author.login}){author.org ? `, ${author.org}` : ""}</option>)}
                    </select>
                  ) : (volume.author ? volume.author.name : "담당 없음")}
                </td>
                <td>{volume.current ? <>{volume.current.name}<span className="meta">{volume.current.state}</span></> : "모두 마침"}</td>
                <td>{volume.current?.turn.join(", ") || "-"}</td>
                <td>{volume.done} / {volume.total}</td>
                <td>
                  <button type="button" className="krds-btn small tertiary" aria-pressed={volume.id === volumeId}
                          aria-label={`${volume.title || volume.module_code} 열기`} onClick={() => onVolume(volume.id)}>열기</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail.can_manage && authors.length === 0 && (
        <p className="form-hint">집필진 계정이 아직 없습니다. 관리자가 집필진 역할의 계정을 만들면 여기서 고를 수 있습니다.</p>
      )}

      <div ref={panel} className="nav-anchor">
        {selected && <VolumePanel key={selected.id} detail={detail} volume={selected} onChange={onChange} onClose={() => onVolume("")} />}
      </div>

      <details className="progress-history">
        <summary>단계별 진도와 단계 정의표</summary>
        <div className="krds-table-wrap">
          <table className="tbl col data progress-table">
            <caption>단계마다 단위, 확인 방식, 담당과 지금 진도. {detail.basis}</caption>
            <thead>
              <tr><th scope="col">단계</th><th scope="col">단위</th><th scope="col">확인 방식</th><th scope="col">담당</th><th scope="col">근거 기록</th><th scope="col">진도</th></tr>
            </thead>
            <tbody>
              {detail.stages.map((stage, index) => (
                <tr key={stage.key}>
                  <th scope="row">{index + 1}. {stage.name}</th>
                  <td>{stage.unit}</td>
                  <td>{stage.kind}</td>
                  <td>{stage.who}</td>
                  <td>{stage.evidence}</td>
                  <td>{stageProgress(stage)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
      <details className="progress-history">
        <summary>건 전체 기록 {detail.events.length}건</summary>
        <EventTable events={detail.events} showVolume />
      </details>
    </section>
  );
}
