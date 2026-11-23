// 그림 해상도·업스케일: 원고(hwpx)의 목표 DPI 미만 그림을 원고에 나오는 순서로 한 줄씩 보여 준다(작은 그림 + 이름 + DPI + 상태).
// 줄을 펼치면 원본·결과를 나란히 본다. 체크한 그림을 한 번에 차례로 업스케일하고(서버는 한 번에 한 장), 화면 아래 실행 바에서 제안본 hwpx를 받는다.
// 결과 그림은 자동으로 내려받지 않는다 — 그림 파일이 필요하면 펼친 줄의 [결과 내려받기]를 누른다.
import React, { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { useCanManage } from "../lib/auth.jsx";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";

function fileStem(name) {
  return (name || "원고").replace(/\.[^.]+$/, "");
}

// 서버는 그림 이름을 검수 비고 규칙대로 「캡션」으로 감싸 보낸다(원고에서 따온 문구 표시). 목록 제목·파일 이름에서는 인용 표시가 필요 없어 뗀다
function plainLabel(label) {
  return (label || "").replace(/^「([\s\S]*)」$/, "$1");
}

// DPI → KRDS 배지 색: 목표 이상 success, 최소 기준 이상 warning, 그 아래 danger
function dpiTone(dpi, target, min) {
  return dpi >= target ? "bg-light-success" : dpi >= min ? "bg-light-warning" : "bg-light-danger";
}

// targetDpi: 해상도 기준(150/300). 바뀌면 부모가 key를 바꿔 목록을 새로 읽는다(같은 기준으로 업스케일한 결과만 다시 보인다 — 다른 기준의 결과는 다시 키워야 한다)
export function UpscalePanel({ token, manuscriptName, moduleCode, targetDpi }) {
  const [state, setState] = useState({ status: "loading" });   // { status: loading|ready|error, data, error }
  const [results, setResults] = useState({});                   // bin_id → 업스케일 결과 정보(서버 JSON) — 마지막에 돌린 것(제안본에 들어감)
  const [variants, setVariants] = useState({});                 // bin_id → { 모델 이름: 결과 정보 } — 모델별 결과를 나란히 보기 위한 것
  const [busy, setBusy] = useState(null);                       // 업스케일 중인 bin_id 또는 "proposal" · "register"
  const [aiMark, setAiMark] = useState(true);                   // 제안본에 AI 활용 줄을 함께 넣는다 — 화질 보정은 AI 수정 보완이라 표기 대상(REQ-02-006 ②③)
  const [imageDb, setImageDb] = useState(false);                // 서버에 이미지 저작권 DB가 있는가
  const canManage = useCanManage();
  useEffect(() => { api.health().then(({ ok, data }) => { if (ok) setImageDb(!!data.image_db); }); }, []);
  const [busyEngine, setBusyEngine] = useState(null);           // 한 장 업스케일에서 고른 모델 이름(버튼 문구용)
  const [batch, setBatch] = useState(null);                     // 여러 장 실행 중: { total, done }
  const [picked, setPicked] = useState(() => new Set());        // 체크한 bin_id
  const [opened, setOpened] = useState(() => new Set());        // 펼친 bin_id
  const [filter, setFilter] = useState("all");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const stop = useRef(false);    // [중지] — 지금 돌고 있는 한 장이 끝나면 멈춘다
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; stop.current = true; }; }, []);

  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    setResults({});
    setVariants({});
    setError(null);
    setNotice(null);
    api.pictures.list(token, targetDpi).then(({ ok, data, error: message }) => {
      if (!current) return;
      if (!ok) { setState({ status: "error", error: message }); return; }
      const done = {};
      const sides = {};
      data.pictures.forEach((p) => {
        if (p.upscaled) done[p.bin_id] = { ...p.upscaled, v: Date.now() };
        Object.entries(p.variants || {}).forEach(([name, info]) => { sides[p.bin_id] = { ...sides[p.bin_id], [name]: { ...info, v: Date.now() } }; });
      });
      setResults(done);
      setVariants(sides);
      setState({ status: "ready", data });
    });
    return () => { current = false; };
  }, [token, targetDpi]);

  const data = state.data;
  const pictures = useMemo(() => data?.pictures || [], [data]);
  const isDone = (p) => results[p.bin_id]?.status === "완료";
  const FILTERS = data ? [
    ["all", "전체", () => true],
    ["low", `${data.min_dpi} DPI 미만`, (p) => p.dpi < data.min_dpi],
    ["mid", `${data.min_dpi}~${data.target_dpi - 1} DPI`, (p) => p.dpi >= data.min_dpi],
    ["todo", "업스케일 전", (p) => !isDone(p)],
  ] : [];
  const shown = pictures.filter((FILTERS.find(([key]) => key === filter) || FILTERS[0] || [null, null, () => true])[2]);

  if (state.status === "loading") {
    return <section className="upscale-panel"><Spinner label="원고의 그림을 읽는 중" /></section>;
  }
  if (state.status === "error") {
    return <section className="upscale-panel"><PageAlert kind="danger">{state.error}</PageAlert></section>;
  }

  const base = moduleCode || fileStem(manuscriptName);
  const engine = data.engine || {};
  // 한 장 업스케일에서 고를 수 있는 모델(앞의 것이 기본). 예전 서버 응답에는 없으므로 기본 엔진 하나로 대신한다
  const engines = data.engines?.length ? data.engines : [{ name: "", label: "", available: engine.available }];
  const missing = engines.filter((e) => e.name && !e.available);
  const ready = pictures.filter(isDone).length;
  const slow = pictures.filter((p) => p.scale >= 4).length;   // 4배로 키울 그림 수
  const low = pictures.filter((p) => p.dpi < data.min_dpi).length;      // 최소 기준에도 못 미침
  const mid = pictures.length - low;                                    // 최소 기준 이상, 목표 미만
  const { 그림: total = 0, "그림 파일": fileCount = 0 } = data.counts;
  const working = busy !== null;
  const pickedShown = shown.filter((p) => picked.has(p.bin_id));
  const allPicked = shown.length > 0 && pickedShown.length === shown.length;

  function toggle(set, update, id) {
    const next = new Set(set);
    if (next.has(id)) next.delete(id); else next.add(id);
    update(next);
  }
  function pickAll(on) {
    const next = new Set(picked);
    shown.forEach((p) => (on ? next.add(p.bin_id) : next.delete(p.bin_id)));
    setPicked(next);
  }

  // 한 장 업스케일. 결과 상태("완료"/"실패")나 요청 오류(null)를 돌려준다
  async function runOne(binId, engineName) {
    setBusy(binId);
    setBusyEngine(engineName || null);
    const { ok, data: info, error: message } = await api.pictures.upscale(token, binId, targetDpi, engineName);
    if (!alive.current) return null;
    if (!ok) { setError(message); return null; }
    const stamped = { ...info, v: Date.now() };
    setResults((prev) => ({ ...prev, [binId]: stamped }));
    if (info.engine) setVariants((prev) => ({ ...prev, [binId]: { ...prev[binId], [info.engine]: stamped } }));
    return info.status;
  }

  async function upscale(picture, engineName) {
    setError(null);
    setNotice(null);
    await runOne(picture.bin_id, engineName);
    if (alive.current) setBusy(null);
  }

  // 체크한 그림을 목록 순서대로 한 장씩. 서버가 한 번에 한 장만 돌리므로 요청도 차례로 보낸다
  async function runPicked() {
    const ids = pictures.filter((p) => picked.has(p.bin_id) && !p.locked).map((p) => p.bin_id);
    if (!ids.length) return;
    setError(null);
    setNotice(null);
    stop.current = false;
    let done = 0, failed = 0, tried = 0;
    for (const id of ids) {
      if (stop.current) break;
      setBatch({ total: ids.length, done: tried });
      const status = await runOne(id);
      if (!alive.current) return;
      tried += 1;
      if (status === "완료") done += 1;
      else { failed += 1; if (status === null) break; }   // 요청 자체가 실패(토큰 만료 등)하면 나머지도 실패하므로 멈춘다
    }
    setBusy(null);
    setBatch(null);
    setPicked(new Set());
    setNotice(`그림 ${ids.length}장 가운데 ${done}장을 업스케일했습니다.${failed ? ` 실패 ${failed}장.` : ""}${tried < ids.length ? ` ${ids.length - tried}장은 실행하지 않았습니다.` : ""}`);
  }

  async function proposal() {
    setBusy("proposal");
    setError(null);
    setNotice(null);
    const { ok, error: message, summary } = await api.pictures.proposal(token, moduleCode, `${fileStem(manuscriptName)}_업스케일제안.hwpx`, targetDpi, aiMark);
    setBusy(null);
    if (!ok) setError(message);
    else if (summary) {
      const marked = summary["AI 표기"];
      const markText = !marked ? ""
        : ` 그림 ${marked.넣음}개의 캡션 위에 AI 활용 줄을 넣었습니다${marked["이미 있음"] ? `(이미 있던 그림 ${marked["이미 있음"]}개는 그대로)` : ""}${marked["넣지 못함"] ? `. 캡션을 찾지 못한 ${marked["넣지 못함"]}개는 직접 적어 주세요` : ""}.`;
      setNotice(`업스케일한 그림 ${summary["바꾼 그림"]}장을 원고의 같은 자리에 넣은 제안본을 내려받았습니다.${markText} 한글에서 열어 그림을 확인하세요.`);
    }
  }

  // 보정한 그림을 이미지 저작권 DB에 올린다 — 원본과 업스케일본, 수록 위치, AI 활용 정보(기존 이미지 보정, 수정 보완, 도구, 오늘 날짜)
  async function register() {
    setBusy("register");
    setError(null);
    setNotice(null);
    const { ok, data, error: message } = await api.pictures.register(token, moduleCode, targetDpi);
    setBusy(null);
    if (!ok) { setError(message); return; }
    const skipped = data["캡션 없음"].length;
    setNotice(`보정한 그림 ${data.그림}개를 이미지 저작권 DB에 올렸습니다(새 그림 ${data["새 그림"]}개, 모듈 ${data["모듈 코드"]}).`
      + `${data["확정 유지"] ? ` 기관이 확정한 ${data["확정 유지"]}개는 권리 정보를 그대로 두었습니다.` : ""}`
      + `${skipped ? ` 캡션을 찾지 못한 ${skipped}개는 올리지 않았습니다.` : ""}`
      + `${data.거부.length ? ` 형식이 맞지 않아 ${data.거부.length}개는 올리지 못했습니다.` : ""}`);
  }

  return (
    <section className="upscale-panel">
      <h2 className="section-title">해상도 점검 결과</h2>
      {/* 한눈에: 원고 그림 수 → 기준 미달 수(등급별) → 업스케일 진행. 숫자를 먼저, 설명은 그 아래 작은 글씨로 */}
      <dl className="upscale-summary">
        <div>
          <dt>원고의 그림</dt>
          <dd><strong>{total}</strong>개</dd>
          <dd className="meta">{fileCount !== total ? `같은 그림을 여러 번 쓴 곳을 묶으면 그림 파일 ${fileCount}개` : "원고에 넣은 그림 전체"}</dd>
        </div>
        <div>
          <dt>해상도 기준 미달</dt>
          <dd><strong>{pictures.length}</strong>개</dd>
          <dd className="meta">
            {pictures.length === 0 ? `모두 ${data.target_dpi} DPI 이상`
              : <>
                  <span className="krds-badge bg-light-danger">{data.min_dpi} DPI 미만 {low}</span>{" "}
                  <span className="krds-badge bg-light-warning">{data.min_dpi}~{data.target_dpi - 1} DPI {mid}</span>
                </>}
          </dd>
        </div>
        <div>
          <dt>업스케일 완료</dt>
          <dd><strong>{ready}</strong> / {pictures.length}개</dd>
          <dd className="meta">완료한 그림만 제안본에 들어갑니다</dd>
        </div>
      </dl>
      <ul className="krds-info-list dash upscale-notes">
        <li>기준은 쪽에 출력되는 크기에서의 실효 해상도 {data.target_dpi} DPI입니다. 아래 목록은 원고에 그림이 나오는 순서입니다.</li>
        <li>2배로 기준에 닿지 않는 그림은 4배로 키웁니다. 4배는 한 장에 약 4배 오래 걸립니다{slow ? ` (이 원고는 ${slow}장)` : ""}.</li>
        {engines.length > 1 && <li>줄을 펼치면 모델을 골라 한 장씩 키울 수 있습니다. 모델별 결과는 원본 옆에 나란히 남고, 제안본에는 그림마다 마지막에 돌린 결과가 들어갑니다. 여러 장 한 번에 돌리기는 기본 모델({engines[0].label})을 씁니다. Real-ESRGAN (x4plus)은 항상 4배로 키운 뒤 필요한 크기로 줄이며 한 장에 몇 분이 걸릴 수 있습니다.</li>}
        {engine.available && missing.map((e) => <li key={e.name}>{e.label} 모델은 실행 파일이 없어 지금은 고를 수 없습니다. {plainReason(e.problem)}</li>)}
        <li>업스케일은 화질만 올립니다. 모델이 글자나 선을 바꿀 수 있으니 줄을 펼쳐 결과를 원본과 나란히 놓고 확인하세요.</li>
      </ul>
      {!engine.available && <PageAlert kind="danger">업스케일 엔진을 쓸 수 없습니다. 그림 목록과 원본 보기만 됩니다.{"\n"}{plainReason(engine.problem)}</PageAlert>}
      {pictures.length === 0 && <p className="empty">{data.target_dpi} DPI 미만 그림이 없습니다.</p>}

      {pictures.length > 0 && (
        <>
          {/* 걸러 보기 — KRDS 탭(결과 보기 전환과 같은 마크업). 괄호 안은 그 조건의 그림 수 */}
          <div className="krds-tab-area layer view-switch">
            <div className="tab line">
              <ul role="tablist" aria-label="그림 걸러 보기">
                {FILTERS.map(([key, label, test]) => (
                  <li key={key} role="tab" aria-selected={filter === key} className={filter === key ? "active" : ""}>
                    <button type="button" className="btn-tab" onClick={() => setFilter(key)}>
                      {label} ({pictures.filter(test).length}){filter === key && <i className="sr-only created"> 선택됨</i>}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="upscale-tools">
            <div className="krds-check-area">
              <div className="krds-form-check">
                <input type="checkbox" id="upscale-all" checked={allPicked} disabled={working || !shown.length}
                       ref={(el) => { if (el) el.indeterminate = pickedShown.length > 0 && !allPicked; }} onChange={(e) => pickAll(e.target.checked)} />
                <label htmlFor="upscale-all">보이는 그림 모두 선택</label>
              </div>
            </div>
            <button type="button" className="krds-btn small text" onClick={() => setOpened(opened.size ? new Set() : new Set(shown.map((p) => p.bin_id)))}>
              {opened.size ? "모두 접기" : "모두 펼치기"}
            </button>
          </div>
          {shown.length === 0 && <p className="empty">이 조건에 맞는 그림이 없습니다.</p>}

          {/* 그림 한 장 = 한 줄. KRDS 아코디언(전체 검수 결과와 같은 마크업) 앞에 체크박스를 둔다 — 버튼 안에는 입력을 넣을 수 없어 줄 바깥에 둔다 */}
          <div className="krds-accordion upscale-list">
            {shown.map((p) => {
              const result = results[p.bin_id];
              const done = result?.status === "완료";
              const running = busy === p.bin_id;
              const open = opened.has(p.bin_id);
              const headId = `upscale-head-${p.bin_id}`;
              const bodyId = `upscale-body-${p.bin_id}`;
              const name = plainLabel(p.label);
              // 이 그림을 성공적으로 키운 모델들(고를 수 있는 모델 순서)
              const sides = engines.map((choice) => [choice, variants[p.bin_id]?.[choice.name]]).filter(([choice, side]) => choice.name && side?.status === "완료");
              return (
                <div key={p.bin_id} className="upscale-row">
                  <div className="krds-check-area">
                    <div className="krds-form-check">
                      <input type="checkbox" id={`upscale-pick-${p.bin_id}`} checked={picked.has(p.bin_id) && !p.locked} disabled={working || !!p.locked}
                             onChange={() => toggle(picked, setPicked, p.bin_id)} />
                      <label htmlFor={`upscale-pick-${p.bin_id}`}><span className="sr-only">{name} 선택</span></label>
                    </div>
                  </div>
                  <div className={`accordion-item${open ? " active" : ""}`}>
                    <h3 className="accordion-header">
                      <button type="button" id={headId} className={`btn-accordion${open ? " active" : ""}`} aria-controls={bodyId} aria-expanded={open}
                              onClick={() => toggle(opened, setOpened, p.bin_id)}>
                        <span className="acc-title">
                          <img className="thumb" src={api.pictures.originalUrl(token, p.bin_id)} alt="" loading="lazy" />
                          <span className="acc-name">{name}</span>
                          <span className="item-status">
                            {running ? <Spinner label="업스케일 중" />
                              : result?.status === "실패" ? <span className="state failed">실패</span>
                              : done ? <span className="state done">완료</span> : null}
                            {done
                              ? <span className={`krds-badge ${dpiTone(result.out_dpi, data.target_dpi, data.min_dpi)}`}>{p.dpi} DPI에서 {result.out_dpi} DPI로</span>
                              : <span className={`krds-badge ${dpiTone(p.dpi, data.target_dpi, data.min_dpi)}`}>{p.dpi} DPI</span>}
                          </span>
                        </span>
                      </button>
                    </h3>
                    <div id={bodyId} className="accordion-collapse collapse" aria-labelledby={headId}>
                      {open && (
                        <div className="accordion-body">
                          <p className="meta">
                            {p.px[0]}×{p.px[1]}px, 출력 {p.mm[0]}×{p.mm[1]}mm, {p.format}, {p.places.join(", ")}
                            {", "}목표까지 {p.need}배 필요, {p.scale}배로 키움{p.scale >= 4 ? " (2배보다 약 4배 오래 걸림)" : ""}{p.reaches_target ? "" : " (목표 미달)"}
                          </p>
                          <div className={`upscale-pair${sides.length > 1 ? " three" : ""}`}>
                            <figure>
                              <img src={api.pictures.originalUrl(token, p.bin_id)} alt={`${name} 원본`} loading="lazy" />
                              <figcaption>원본 {p.px[0]}×{p.px[1]}px</figcaption>
                            </figure>
                            {/* 모델별 결과를 원본 옆에 모두 — 최대 3장(원본 + 모델 2개). 예전 서버(모델 구분 없음)면 마지막 결과 한 장 */}
                            {sides.length > 0
                              ? sides.map(([choice, side]) => (
                                <figure key={choice.name}>
                                  <img src={api.pictures.upscaledUrl(token, p.bin_id, side.v, choice.name)} alt={`${name} 업스케일 ${choice.label}`} loading="lazy" />
                                  <figcaption>
                                    {choice.label}, {side.out_px[0]}×{side.out_px[1]}px, {side.out_dpi} DPI, {side.seconds}초
                                    {sides.length > 1 && done && result.engine === choice.name ? ", 제안본에 들어감" : ""}
                                    {", "}<a href={api.pictures.downloadUrl(token, p.bin_id, `${base}_${name}_${choice.name}`, choice.name)} download>내려받기</a>
                                  </figcaption>
                                </figure>
                              ))
                              : done && (
                                <figure>
                                  <img src={api.pictures.upscaledUrl(token, p.bin_id, result.v)} alt={`${name} 업스케일`} loading="lazy" />
                                  <figcaption>업스케일 {result.out_px[0]}×{result.out_px[1]}px, {result.out_dpi} DPI, {result.seconds}초</figcaption>
                                </figure>
                              )}
                          </div>
                          {/* 변경금지 원본(공공누리 제3·4유형)은 AI 화질 보정을 하지 않는다(REQ-02-006 ⑥). 비상업 원본은 조건만 알린다 */}
                          {p.locked && <p className="upscale-note failed">업스케일 제외: {p.locked.이유}</p>}
                          {!p.locked && p.terms && <p className="upscale-note">{p.terms} — 결과물에도 이 조건을 표시해야 합니다.</p>}
                          {result?.note && <p className={`upscale-note${result.status === "실패" ? " failed" : ""}`}>{result.status === "실패" ? "실패: " : ""}{result.note}</p>}
                          <div className="upscale-actions">
                            {/* 모델마다 버튼 하나 — 같은 그림을 모델별로 돌려 비교한다(제안본에는 마지막에 돌린 결과가 들어간다) */}
                            {engines.map((choice) => (
                              <button key={choice.name || "default"} type="button" className="krds-btn small secondary"
                                      disabled={!choice.available || working || !!p.locked} onClick={() => upscale(p, choice.name)}
                                      title={choice.available ? choice.note : plainReason(choice.problem)}>
                                {running && (busyEngine || "") === choice.name ? "업스케일하는 중"
                                  : choice.label ? `${choice.label}로 업스케일링`
                                  : done ? "다시 업스케일링" : "이 그림만 업스케일링"}
                              </button>
                            ))}
                            {done && (
                              <a className="krds-btn small tertiary" href={api.pictures.downloadUrl(token, p.bin_id, `${base}_${name}_업스케일`)} download>
                                결과 내려받기
                              </a>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* 실행 바 — 목록이 길어도 화면 아래에 붙어 있다. 실행 결과 알림도 바 안에 둬 목록 어디에 있든 보인다. 왼쪽 진행 상황, 오른쪽 선택 실행 → 제안본 */}
      {pictures.length === 0 && error && <PageAlert kind="danger">{error}</PageAlert>}
      {pictures.length > 0 && (
        <div className="upscale-bar">
          {error && <PageAlert kind="danger">{error}</PageAlert>}
          {notice && !error && <PageAlert kind="success">{notice}</PageAlert>}
          <div className="krds-form-check bar-check">
            <input type="checkbox" id="upscale-ai-mark" checked={aiMark} onChange={(e) => setAiMark(e.target.checked)} />
            <label htmlFor="upscale-ai-mark">제안본에 AI 활용 표기 넣기<span className="meta"> (보정한 그림의 캡션 위에 ‘모델 이름을 활용하여 수정 보완함. 오늘 날짜’ 한 줄)</span></label>
          </div>
          <div className="bar-row">
          <span className="meta" role="status">
            {batch ? <>업스케일 중 <strong>{batch.done + 1}</strong> / {batch.total}장</>
              : <>선택 <strong>{picked.size}</strong>장, 업스케일 완료 <strong>{ready}</strong> / {pictures.length}개</>}
          </span>
          <div className="bar-actions">
            {batch
              ? <button type="button" className="krds-btn medium tertiary" onClick={() => { stop.current = true; }}>이번 그림까지만 하고 중지</button>
              : <button type="button" className="krds-btn medium secondary" disabled={!engine.available || working || picked.size === 0} onClick={runPicked}>
                  선택한 {picked.size}장 업스케일링
                </button>}
            {imageDb && canManage && (
              <button type="button" className="krds-btn medium tertiary" disabled={!ready || working} onClick={register}
                      title="보정한 그림과 업스케일본을 AI 활용 정보(기존 이미지 보정, 수정 보완)와 함께 이미지 저작권 DB에 올립니다">
                {busy === "register" ? "올리는 중" : "이미지 저작권 DB에 올리기"}
              </button>
            )}
            <button type="button" className="krds-btn medium primary" disabled={!ready || working} onClick={proposal}
                    title="업스케일한 그림만 원고의 같은 자리에 넣은 사본(hwpx). 본문과 그림의 크기, 위치는 그대로입니다">
              {busy === "proposal" ? "만드는 중" : `제안본 내려받기(그림 ${ready}장)`}
            </button>
          </div>
          </div>
        </div>
      )}
    </section>
  );
}
