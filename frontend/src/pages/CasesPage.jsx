// 세분류 건(REQ-02-007) — 주문의 단위는 세분류 한 건이다. 건을 만들고(세분류 코드 → NCS 목록의 학습모듈이 권이 된다) 권마다 담당 집필자를 붙인다.
// 단계의 상태는 서버가 사건 기록을 접어서 준다(ncs_service.flow). 이 화면은 상태를 따로 계산하지 않고 받은 것을 보이기만 한다.
// 에디터와 직능연은 모든 건을 보고 만들 수 있다. 집필진은 자기가 담당인 권이 든 건만, 그 권만 본다(서버가 거른다).
// 화면 짜임은 원고 진행 현황과 같다: 위쪽 입력 묶음(건 만들기) → 목록 → 고른 건의 상세가 목록 아래에 열리고 [닫기]. 고른 건은 주소(?case=)에 남는다.
import React, { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.jsx";
import { Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { usePageTitle } from "../lib/hooks.js";

const ANCHORS = [{ id: "cases-list", label: "건 목록" }, { id: "cases-detail", label: "권과 단계" }];
const DONE = "완료", WAITING = "대기";

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
  const [history, setHistory] = useState(null);       // null: 확인 중, false: DB 없음
  const [list, setList] = useState(null);             // { cases, can_manage }
  const [listError, setListError] = useState(null);
  const [options, setOptions] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [loading, setLoading] = useState(false);
  const detailBox = useRef(null);

  async function refreshList() {
    const { ok, data, error } = await api.cases.list();
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
  }, [caseId, history]);

  const cases = list?.cases;
  return (
    <>
    <Header anchors={ANCHORS} />
    <main id="main" className="inner page">
      <h1 className="page-title">세분류 건</h1>
      <p className="page-desc">세분류 한 건이 일의 단위입니다. 건을 만들면 그 세분류의 학습모듈이 권으로 들어가고, 권마다 담당 집필자를 정합니다. 단계가 바뀔 때마다 누가 언제 무엇을 했는지 기록에 남습니다.</p>

      {history === null && <Spinner label="기록을 확인하는 중" />}
      {history === false && <PageAlert kind="info">데이터베이스가 연결된 서버에서만 세분류 건을 쓸 수 있습니다. 관리자에게 문의해 주세요.</PageAlert>}

      {history && list?.can_manage && options && (
        <CreateForm options={options} onCreated={(created) => { refreshList(); setParams({ case: created.id }); }} />
      )}

      {history && (
        <section id="cases-list" className="nav-anchor">
          <div className="section-head">
            <h2 className="section-title">건 목록{cases ? <span className="meta"> {cases.length}건</span> : null}</h2>
          </div>
          <PageAlert kind="danger">{listError}</PageAlert>
          {!list && !listError && <Spinner label="목록을 읽는 중" />}
          {cases && (cases.length === 0 ? (
            <p className="empty">{list.can_manage ? "아직 만든 건이 없습니다. 위에서 세분류 코드로 건을 만들어 주세요." : "담당으로 정해진 권이 아직 없습니다. 에디터가 권에 담당을 정하면 여기에 나타납니다."}</p>
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
                                aria-label={`${row.name || row.subclass} ${row.year}년 건 열기`} onClick={() => setParams({ case: row.id })}>열기</button>
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
          <CaseDetail detail={detail} authors={options?.authors || []}
                      onChange={(next) => { setDetail(next); refreshList(); }} onClose={() => setParams({})} />
        )}
      </div>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function CaseDetail({ detail, authors, onChange, onClose }) {
  const [saving, setSaving] = useState(null);         // 담당을 바꾸는 중인 권 id
  const [error, setError] = useState(null);
  const volumeStages = detail.stages.filter((stage) => stage.unit === "권");

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

  // 권에서 지금 움직이고 있는 단계(대기도 완료도 아닌 것)
  const moving = (volume) => volumeStages.filter((stage) => ![DONE, WAITING].includes(volume.stages[stage.key].state))
    .map((stage) => `${stage.name}: ${volume.stages[stage.key].state}`);

  return (
    <section className="progress-detail" aria-labelledby="case-detail-title">
      <div className="section-head">
        <h2 className="section-title" id="case-detail-title">
          {detail.name || detail.subclass} <span className="meta">{detail.subclass}, {detail.year}년, {detail.improvement}</span>
        </h2>
        <button type="button" className="krds-btn small tertiary" onClick={onClose}>닫기</button>
      </div>
      <p className="progress-overall"><ProgressBar done={detail.progress.done} total={detail.progress.total} /></p>

      <h3 className="table-title">권 <span className="meta">{detail.volumes.length}권{detail.can_manage ? ", 담당 집필자는 집필진 계정에서 고릅니다" : ""}</span></h3>
      <PageAlert kind="danger">{error}</PageAlert>
      <div className="krds-table-wrap">
        <table className="tbl col data progress-table">
          <caption>권마다 담당 집필자와 단계 진도</caption>
          <thead>
            <tr><th scope="col">학습모듈</th><th scope="col">담당 집필자</th><th scope="col">완료한 단계</th><th scope="col">진행 중인 단계</th><th scope="col">원고 기록</th></tr>
          </thead>
          <tbody>
            {detail.volumes.map((volume) => (
              <tr key={volume.id}>
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
                <td>{volume.done} / {volume.total}</td>
                <td>{moving(volume).length ? moving(volume).map((line) => <span key={line} className="meta">{line}</span>) : "-"}</td>
                <td><Link to={`/progress?code=${encodeURIComponent(volume.module_code)}`} className="krds-btn small text">진행 현황</Link></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail.can_manage && authors.length === 0 && (
        <p className="form-hint">집필진 계정이 아직 없습니다. 관리자가 집필진 역할의 계정을 만들면 여기서 고를 수 있습니다.</p>
      )}

      <h3 className="table-title">단계 <span className="meta">{detail.basis}</span></h3>
      <div className="krds-table-wrap">
        <table className="tbl col data progress-table">
          <caption>단계마다 단위, 확인 방식, 담당과 지금 진도</caption>
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

      <h3 className="table-title">기록 <span className="meta">최근 것부터 {detail.events.length}건. 지우거나 고칠 수 없습니다</span></h3>
      <div className="krds-table-wrap">
        <table className="tbl col data progress-table">
          <caption>누가 언제 무엇을 했는지</caption>
          <thead>
            <tr><th scope="col">일시</th><th scope="col">누가</th><th scope="col">권</th><th scope="col">단계</th><th scope="col">무엇을</th><th scope="col">메모</th></tr>
          </thead>
          <tbody>
            {detail.events.map((event) => (
              <tr key={event.id}>
                <td>{formatDate(event.at)}</td>
                <td>{event.actor}{event.proxy && <span className="meta">대신 기록</span>}</td>
                <td>{event.module_code || "건 전체"}</td>
                <td>{event.stage_name || "-"}</td>
                <td>{event.action_name}</td>
                <td>{event.note || "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
