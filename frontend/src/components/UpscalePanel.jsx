// 그림 해상도·업스케일: 원고(hwpx)의 목표 DPI 미만 그림을 원고에 나오는 순서로 한 줄씩 보여 준다(작은 그림 + 이름 + DPI + 상태).
// 줄을 펼치면 원본·결과를 나란히 본다. 체크한 그림을 한 번에 차례로 업스케일하고(서버는 한 번에 한 장), 화면 아래 실행 바에서 제안본 hwpx를 받는다.
// 결과 그림은 자동으로 내려받지 않는다 — 그림 파일이 필요하면 펼친 줄의 [결과 받기]를 누른다.
import React, { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
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

export function UpscalePanel({ token, manuscriptName, moduleCode }) {
  const [state, setState] = useState({ status: "loading" });   // { status: loading|ready|error, data, error }
  const [results, setResults] = useState({});                   // bin_id → 업스케일 결과 정보(서버 JSON)
  const [busy, setBusy] = useState(null);                       // 업스케일 중인 bin_id 또는 "proposal"
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
    setError(null);
    setNotice(null);
    api.pictures.list(token).then(({ ok, data, error: message }) => {
      if (!current) return;
      if (!ok) { setState({ status: "error", error: message }); return; }
      const done = {};
      data.pictures.forEach((p) => { if (p.upscaled) done[p.bin_id] = { ...p.upscaled, v: Date.now() }; });
      setResults(done);
      setState({ status: "ready", data });
    });
    return () => { current = false; };
  }, [token]);

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
  const ready = pictures.filter(isDone).length;
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
  async function runOne(binId) {
    setBusy(binId);
    const { ok, data: info, error: message } = await api.pictures.upscale(token, binId);
    if (!alive.current) return null;
    if (!ok) { setError(message); return null; }
    setResults((prev) => ({ ...prev, [binId]: { ...info, v: Date.now() } }));
    return info.status;
  }

  async function upscale(picture) {
    setError(null);
    setNotice(null);
    await runOne(picture.bin_id);
    if (alive.current) setBusy(null);
  }

  // 체크한 그림을 목록 순서대로 한 장씩. 서버가 한 번에 한 장만 돌리므로 요청도 차례로 보낸다
  async function runPicked() {
    const ids = pictures.filter((p) => picked.has(p.bin_id)).map((p) => p.bin_id);
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
    const { ok, error: message, summary } = await api.pictures.proposal(token, moduleCode, `${fileStem(manuscriptName)}_업스케일제안.hwpx`);
    setBusy(null);
    if (!ok) setError(message);
    else if (summary) setNotice(`업스케일한 그림 ${summary["바꾼 그림"]}장을 원고의 같은 자리에 넣은 제안본을 내려받았습니다. 한글에서 열어 그림을 확인하세요.`);
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
        <li>업스케일은 화질만 올립니다. 모델이 글자·선을 바꿀 수 있으니 줄을 펼쳐 결과를 원본과 나란히 놓고 확인하세요.</li>
      </ul>
      {!engine.available && <PageAlert kind="danger">업스케일 엔진을 쓸 수 없습니다. 그림 목록과 원본 보기만 됩니다.{"\n"}{engine.problem}</PageAlert>}
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
              return (
                <div key={p.bin_id} className="upscale-row">
                  <div className="krds-check-area">
                    <div className="krds-form-check">
                      <input type="checkbox" id={`upscale-pick-${p.bin_id}`} checked={picked.has(p.bin_id)} disabled={working}
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
                              ? <span className={`krds-badge ${dpiTone(result.out_dpi, data.target_dpi, data.min_dpi)}`}>{p.dpi} → {result.out_dpi} DPI</span>
                              : <span className={`krds-badge ${dpiTone(p.dpi, data.target_dpi, data.min_dpi)}`}>{p.dpi} DPI</span>}
                          </span>
                        </span>
                      </button>
                    </h3>
                    <div id={bodyId} className="accordion-collapse collapse" aria-labelledby={headId}>
                      {open && (
                        <div className="accordion-body">
                          <p className="meta">
                            {p.px[0]}×{p.px[1]}px · 출력 {p.mm[0]}×{p.mm[1]}mm · {p.format} · {p.places.join(", ")}
                            {" · "}목표까지 {p.need}배 필요, {p.scale}배로 키움{p.reaches_target ? "" : " (목표 미달)"}
                          </p>
                          <div className="upscale-pair">
                            <figure>
                              <img src={api.pictures.originalUrl(token, p.bin_id)} alt={`${name} 원본`} loading="lazy" />
                              <figcaption>원본 {p.px[0]}×{p.px[1]}px</figcaption>
                            </figure>
                            {done && (
                              <figure>
                                <img src={api.pictures.upscaledUrl(token, p.bin_id, result.v)} alt={`${name} 업스케일`} loading="lazy" />
                                <figcaption>업스케일 {result.out_px[0]}×{result.out_px[1]}px · {result.out_dpi} DPI · {result.seconds}초</figcaption>
                              </figure>
                            )}
                          </div>
                          {result?.note && <p className={`upscale-note${result.status === "실패" ? " failed" : ""}`}>{result.status === "실패" ? "실패: " : ""}{result.note}</p>}
                          <div className="upscale-actions">
                            <button type="button" className="krds-btn small secondary" disabled={!engine.available || working} onClick={() => upscale(p)}>
                              {running ? "업스케일 중…" : done ? "다시 업스케일링" : "이 그림만 업스케일링"}
                            </button>
                            {done && (
                              <a className="krds-btn small tertiary" href={api.pictures.downloadUrl(token, p.bin_id, `${base}_${name}_업스케일`)} download>
                                결과 받기
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
          <div className="bar-row">
          <span className="meta" role="status">
            {batch ? <>업스케일 중 <strong>{batch.done + 1}</strong> / {batch.total}장</>
              : <>선택 <strong>{picked.size}</strong>장 · 업스케일 완료 <strong>{ready}</strong> / {pictures.length}개</>}
          </span>
          <div className="bar-actions">
            {batch
              ? <button type="button" className="krds-btn medium tertiary" onClick={() => { stop.current = true; }}>이번 그림까지만 하고 중지</button>
              : <button type="button" className="krds-btn medium secondary" disabled={!engine.available || working || picked.size === 0} onClick={runPicked}>
                  선택한 {picked.size}장 업스케일링
                </button>}
            <button type="button" className="krds-btn medium primary" disabled={!ready || working} onClick={proposal}
                    title="업스케일한 그림만 원고의 같은 자리에 넣은 사본(hwpx). 본문·그림 크기·위치는 그대로">
              {busy === "proposal" ? "만드는 중…" : `제안본 hwpx 받기 (그림 ${ready}장)`}
            </button>
          </div>
          </div>
        </div>
      )}
    </section>
  );
}
