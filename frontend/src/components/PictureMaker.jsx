// 사진·삽화 만들기(REQ-02-006 ① AI 생성) — 이미지 AI 생성 페이지가 유형을 사진이나 삽화로 골랐을 때 후보와 수정과 내려받기 자리에 놓는다.
// 흐름: 장면 후보(생성형 AI가 문단에서 쓴 한국어 장면과 영어 글, 프롬프트 검사) → 장면을 골라 고침 → 서버의 모델이 그림을 만듦 → 한 장을 골라 확인 → 받기.
// 그림은 서버에 올린 공개 모델이 만든다(외부 전송 없음). 엔진이 꺼진 서버에서는 장면과 모델에 보낼 글까지만 만든다.
// 그림 자체는 규칙으로 검사하지 못한다. 그래서 프롬프트에서 막고(얼굴, 상표, 화풍 따라 하기), 받기 전에 사람이 세 가지를 확인해야 한다
// (얼굴이 드러난 사람 없음, 글자·로고 없음, 실제 장비·작업과 다르지 않음). 서버는 놓을 폭에서의 해상도와 이미지 저작권 DB의 닮은 그림을 알려 준다.
// 만든 그림은 서버에 남기지 않는다 — 에디터·직능연이 [이미지 저작권 DB에 올리기]를 누른 그림만 남는다.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api, saveBlob } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { copyText } from "../lib/clipboard.js";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";

const KIND_LABEL = { photo: "사진", illustration: "삽화" };
const METHOD_LABEL = { "같은 파일": "같은 파일", "지각 해시": "크기나 형식만 바뀐 그림", "임베딩": "내용이 비슷한 그림" };      // 서버가 알려 주는 찾은 방법을 화면의 말로
const ASSET_LABEL = { photo: "사진", illustration: "삽화", table: "도표", graph: "그래프", screenshot: "화면 캡처", other: "기타" };
const CONFIRMS = [
  ["face", "얼굴이 드러난 사람이 없습니다(뒷모습, 멀리 있는 모습, 손은 허용)"],
  ["letters", "읽을 수 있는 글자, 로고, 상표가 없습니다"],
  ["real", "실제 장비, 작업 모습과 다르지 않습니다"],
];
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const dataUrl = (png) => `data:image/png;base64,${png}`;
async function toBlob(png) { return (await fetch(dataUrl(png))).blob(); }

// 같은 갈래의 지적은 한 줄로 묶는다('얼굴이 드러나는 그림은 만들지 않습니다: 웃는, 얼굴, portrait')
const PROBLEM_LEAD = {
  face: ["얼굴이 드러나는 그림은 만들지 않습니다", "뒷모습, 멀리 있는 모습, 손은 사용할 수 있습니다."],
  imitate: ["특정 작가, 작품, 상표의 화풍은 따라 하지 않습니다", ""],
  brand: ["상표와 상품명은 넣지 않습니다", "일반 명칭으로 바꿔 주세요."],
};
function groupProblems(problems) {
  const groups = new Map();
  for (const problem of problems) groups.set(problem.kind, [...(groups.get(problem.kind) || []), problem.text]);
  return [...groups].map(([kind, texts]) => {
    const [lead, tail] = PROBLEM_LEAD[kind] || ["만들지 않는 내용입니다", ""];
    return `${lead}: ${texts.join(", ")}${tail ? `. ${tail}` : ""}`;
  });
}

// 남은 시간과 걸린 시간을 읽기 쉬운 말로: 45초, 3분, 3분 20초
function duration(seconds) {
  if (seconds === null || seconds === undefined) return "";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}초`;
  return s % 60 >= 10 && s < 600 ? `${Math.floor(s / 60)}분 ${Math.floor((s % 60) / 10) * 10}초` : `${Math.round(s / 60)}분`;
}

const newJob = () => (globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `job-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);

// 그림을 만드는 동안의 진행 상황 — 서버가 알려 준 장과 단계, 걸린 시간과 남은 시간(어림). 한 장에 몇 분이 걸려서 멈춘 것처럼 보이지 않게 한다
function MakingProgress({ state, count, cancelling, onCancel }) {
  const running = state?.state === "running" && state.steps > 0;
  const label = !state ? "서버에 요청하는 중입니다"
    : state.state === "waiting" ? "다른 요청이 끝나기를 기다리는 중입니다"
      : state.state === "loading" ? "이미지 모델을 불러오는 중입니다"
        : running ? `${state.count}장 중 ${state.image}번째 그림을 만드는 중입니다. ${state.steps}단계 중 ${state.step}단계`
          : "그림을 만드는 중입니다";
  const percent = running ? state.percent : 0;
  return (
    <div className="gen-preview is-loading gen-progress" role="status">
      <p className="gen-progress-label"><strong>{cancelling ? "취소하는 중입니다. 지금 단계가 끝나면 멈춥니다" : label}</strong></p>
      <progress className="gen-progress-bar" max={100} value={running ? percent : undefined} aria-label="그림 만들기 진행률" />
      <p className="meta">
        {running ? `${percent}% 완료` : `${count}장을 만듭니다`}
        {state?.elapsed > 0 ? `, ${duration(state.elapsed)} 지남` : ""}
        {running && state.remaining !== null ? `, 약 ${duration(state.remaining)} 남음` : running ? ", 남은 시간을 계산하는 중" : ""}
      </p>
      <p className="form-hint">서버 성능에 따라 한 장에 몇 분이 걸립니다. 이 화면을 닫지 말고 기다려 주세요.</p>
      <button type="button" className="krds-btn small tertiary" disabled={cancelling} onClick={onCancel}>만들기 취소</button>
    </div>
  );
}

function Problems({ problems, notes }) {
  if (!problems?.length && !notes?.length) return null;
  return (
    <div className="gen-notes">
      {problems?.length > 0 && (
        <div className="page-alert danger"><i className="svg-icon" aria-hidden="true"></i>
          <div className="page-alert-body">{groupProblems(problems).map((line) => <p key={line}>{line}</p>)}</div></div>
      )}
      {notes?.length > 0 && (
        <div className="page-alert warning"><i className="svg-icon" aria-hidden="true"></i>
          <div className="page-alert-body">{notes.map((note, i) => <p key={i}>{note}</p>)}</div></div>
      )}
    </div>
  );
}

// request: { kind, text, criterion, focus, width, manual } — 페이지가 [장면 만들기]나 [직접 적기]를 누를 때 새로 만들어 key와 함께 넘긴다
export default function PictureMaker({ request, engine, hasDb, canManage, needsName, onStage }) {
  const { kind, text, criterion, focus, width } = request;
  const [drafted, setDrafted] = useState(request.manual ? { method: "none", note: "", scenes: [], usage: text.trim() ? 1 : 4 } : null);   // 장면 후보 응답
  const [error, setError] = useState(null);
  const [scene, setScene] = useState(request.manual ? { ko: focus || "", en: "" } : null);       // 고치는 중인 장면
  const [options, setOptions] = useState({ shape: "landscape", count: 2 });
  const [chosen, setChosen] = useState(null);                   // 고른 후보의 순번(직접 입력이면 null)
  const [showCandidates, setShowCandidates] = useState(true);   // 장면을 고르면 후보는 한 줄 요약으로 접는다(확인, 문단과 같은 방식)
  const [syncedKo, setSyncedKo] = useState(null);               // 지금의 영어 장면이 옮겨진 한국어 장면 — 한국어를 고치면 영어가 낡았다고 알린다
  const [busy, setBusy] = useState("");                         // "" | "translate" | "image"
  const [job, setJob] = useState(null);                         // 만드는 중인 작업 { id, state(서버의 진행 상황), cancelling }
  const [stopped, setStopped] = useState(false);                // 방금 만들기를 취소했는가 — 그림 자리에 알린다
  const [sentCopied, setSentCopied] = useState("");             // '보낸 내용 복사'의 결과 알림
  const [made, setMade] = useState(null);                       // { prompt, images, tool, notes }
  const [makeError, setMakeError] = useState(null);             // { error, problems }
  const [pick, setPick] = useState(null);                       // 고른 그림의 순번
  const [seen, setSeen] = useState(null);                       // 고른 그림의 확인 결과 { dpi, … } | { error }
  const [confirmed, setConfirmed] = useState({});
  const [mark, setMark] = useState({ title: "", tool: engine?.도구 || "", date: today(), number: "" });
  const [marking, setMarking] = useState(null);
  const [store, setStore] = useState({ module: "", by: "", busy: false, result: null, error: null });
  const [done, setDone] = useState(null);
  const usage = drafted?.usage || (text.trim() ? 1 : 4);
  const image = made && pick !== null ? made.images[pick] : null;

  useEffect(() => {
    if (request.manual) return undefined;
    let alive = true;
    api.generate.prompt({ text, criterion, kind, focus }).then(({ ok, data, error: message }) => {
      if (!alive) return;
      if (ok) setDrafted(data); else setError(message);
    });
    return () => { alive = false; };
  }, []);                                                       // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { onStage?.(image ? 5 : scene ? 4 : 3); }, [image, scene]);      // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!image) { setSeen(null); return undefined; }
    let alive = true;
    setSeen(null); setConfirmed({}); setDone(null); setStore((old) => ({ ...old, result: null, error: null }));
    api.generate.inspect({ png: image.png, width_mm: width }).then(({ ok, data, error: message }) => { if (alive) setSeen(ok ? data : { error: message }); });
    return () => { alive = false; };
  }, [image, width]);

  useEffect(() => {
    if (!image || !mark.tool.trim()) { setMarking(null); return undefined; }
    let alive = true;
    api.generate.marking({ title: mark.title, tool: mark.tool, date: mark.date, kind, number: mark.number, usage }).then(({ ok, data, error: message }) => {
      if (alive) setMarking(ok ? data : { error: message });
    });
    return () => { alive = false; };
  }, [image, mark.title, mark.tool, mark.date, mark.number, kind, usage]);

  function choose(entry, index = null) {
    setScene({ ko: entry.ko, en: entry.en }); setMade(null); setPick(null); setMakeError(null);
    setChosen(index); setShowCandidates(false); setSyncedKo(entry.en ? entry.ko : null);
    setTimeout(() => document.getElementById("generate-edit")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  function choosePicture(i) {
    setPick(i);
    setTimeout(() => document.getElementById("generate-finish")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  async function translate() {
    setBusy("translate"); setMakeError(null);
    const { ok, data, error: message } = await api.generate.prompt({ text, criterion, kind, focus, scene: scene.ko });
    setBusy("");
    if (!ok) { setMakeError({ error: message }); return; }
    const first = data.scenes[0];
    if (!first) { setMakeError({ error: plainReason(data.note) || "영어 장면을 만들지 못했습니다. 직접 입력해 주세요." }); return; }
    setScene({ ko: scene.ko, en: first.en }); setSyncedKo(scene.ko);
    if (!first.ok) setMakeError({ error: "이 장면으로는 그림을 만들지 않습니다.", problems: first.problems });
  }

  // 만드는 동안 2초마다 서버에 진행 상황을 묻는다. 요청이 끝나면(job이 비면) 멈춘다
  useEffect(() => {
    if (!job?.id) return undefined;
    let alive = true;
    const ask = () => api.generate.progress(job.id).then(({ ok, data }) => {
      if (alive && ok) setJob((current) => (current?.id === job.id ? { ...current, state: data } : current));
    });
    const timer = setInterval(ask, 2000);
    ask();
    return () => { alive = false; clearInterval(timer); };
  }, [job?.id]);

  async function make() {
    const id = newJob();
    setBusy("image"); setMakeError(null); setMade(null); setPick(null); setStopped(false); setSentCopied(""); setJob({ id, state: null, cancelling: false });
    // 버튼은 왼쪽 열 아래, 진행률은 오른쪽 열 위라서 누른 자리에서는 진행률이 보이지 않는다 — 진행률 자리로 옮긴다
    setTimeout(() => document.getElementById("generate-result")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    const { ok, data, error: message, status } = await api.generate.image({ scene: scene.en, scene_ko: scene.ko, kind, shape: options.shape, count: options.count, job: id });
    setBusy(""); setJob(null);
    if (!ok) {
      if (status === 409 && data?.cancelled) { setStopped(true); return; }
      setMakeError({ error: message, problems: data?.problems });
      return;
    }
    setMade(data);
  }

  async function cancelMaking() {
    if (!job?.id) return;
    setJob((current) => (current ? { ...current, cancelling: true } : current));
    await api.generate.cancel(job.id);
  }

  async function save() {
    saveBlob(await toBlob(image.png), `${(mark.title || KIND_LABEL[kind]).replace(/[\\/:*?"<>|]+/g, "_")}.png`);
    setDone(`그림을 내려받았습니다. 원고에 가로 ${seen?.["300 DPI 폭"] || ""}mm 이하로 넣어야 300 DPI가 됩니다.`);
  }

  async function register() {
    setStore((old) => ({ ...old, busy: true, result: null, error: null }));
    const { ok, data, error: message } = await api.generate.registerImage({
      png: image.png, kind, usage, title: mark.title, tool: mark.tool, date: mark.date, module_code: store.module.trim(),
      number: store.module.trim() ? mark.number : "", by: store.by });
    setStore((old) => ({ ...old, busy: false, result: ok ? data : null, error: ok ? null : message }));
  }

  const allConfirmed = CONFIRMS.every(([key]) => confirmed[key]);
  const similar = seen?.["닮은 그림"];
  const stale = !!scene && !!scene.en.trim() && syncedKo !== null && scene.ko.trim() !== syncedKo.trim();      // 한국어 장면을 고쳤는데 영어는 그대로다
  const shapeNow = (engine?.모양 || []).find((entry) => entry.shape === options.shape);
  const folded = !request.manual && !!scene && !showCandidates;
  return (
    <>
    {folded && (
      <ul className="gen-trail gen-trail-more" aria-label="완료한 단계">
        <li>
          <span><strong>후보</strong> 장면 {drafted.scenes.length}개 가운데 {drafted.usable}개 통과, {chosen !== null ? `장면 ${chosen + 1}을 선택했습니다.` : "장면을 직접 입력 중입니다."}</span>
          <button type="button" className="krds-btn small tertiary" onClick={() => setShowCandidates(true)}>후보 다시 보기</button>
        </li>
      </ul>
    )}
    {!folded && (!request.manual || !engine?.["사용 가능"]) && (
    <section id="generate-candidates" className="nav-anchor image-section" aria-live="polite">
      <h2 className="section-title">{request.manual ? "그림 만들기 안내" : "후보"}</h2>
      {error && <PageAlert kind="danger">{error}</PageAlert>}
      {!drafted && !error && <Spinner label="장면을 만드는 중" />}
      {!engine?.["사용 가능"] && (
        <PageAlert kind="info">이 서버에서는 지금 그림을 만들 수 없습니다. {engine?.이유}{"\n"}장면과 이미지 모델에 보낼 영어 장면까지는 만들 수 있습니다. 다른 도구로 만든 그림의 표기와 결과물 현황은 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.</PageAlert>
      )}
      {drafted && !request.manual && (<>
        <p className="recommend-method">
          <span className={`krds-badge ${drafted.method === "llm" ? "bg-light-information" : "bg-light-gray"}`}>{drafted.method === "llm" ? `생성형 AI${drafted.model ? `(${drafted.model})` : ""}` : "생성형 AI 사용 안 함"}</span>
          <span className="meta"> {plainReason(drafted.note)}{drafted.reason ? ` 생성형 AI의 설명: ${drafted.reason}` : ""}</span>
        </p>
        {drafted.usable === 0 && !scene && (
          <div className="gen-none">
            <p><strong>통과한 장면이 없습니다.</strong> 제외된 장면을 [수정해서 사용]으로 고치거나, 장면을 직접 입력해 주세요.</p>
            <button type="button" className="krds-btn medium primary" onClick={() => choose({ ko: focus || "", en: "" })}>장면 직접 입력</button>
          </div>
        )}
        <ul className="gen-candidates is-scenes">
          {drafted.scenes.map((entry, i) => (
            <li key={i} className={`gen-candidate${entry.ok ? "" : " is-rejected"}${chosen === i ? " is-chosen" : ""}`}>
              <h3><span className="gen-candidate-name">장면 {i + 1}</span>
                <span className="gen-candidate-badges"><span className={`krds-badge ${entry.ok ? "bg-light-success" : "bg-light-danger"}`}>{entry.ok ? "검사 통과" : "제외"}</span></span></h3>
              <p className="gen-scene">{entry.ko}</p>
              {/* 집필자가 읽고 고르는 것은 한국어 장면이다. 영어는 모델에 보내는 글이라 접어 둔다(지적이 영어 낱말을 가리킬 때 펼쳐 본다) */}
              <details className="gen-en-detail" open={!entry.ok}><summary>영어 장면 보기</summary><p className="gen-scene meta" lang="en">{entry.en}</p></details>
              <Problems problems={entry.problems} notes={entry.notes} />
              <div className="gen-candidate-actions">
                <button type="button" className={`krds-btn small ${entry.ok ? "primary" : "secondary"}`} onClick={() => choose(entry, i)}>
                  {chosen === i ? "선택한 장면" : entry.ok ? "이 장면 선택" : "수정해서 사용"}<span className="sr-only"> 장면 {i + 1}</span></button>
              </div>
            </li>
          ))}
        </ul>
        {!scene && drafted.usable > 0 && (
          <div className="run-buttons image-actions gen-enter">
            <button type="button" className="krds-btn medium secondary" onClick={() => choose({ ko: focus || "", en: "" })}>장면 직접 입력</button>
          </div>
        )}
      </>)}
    </section>
    )}

    {scene && (
    <section id="generate-edit" className="nav-anchor image-section">
      <h2 className="section-title">장면 수정과 {KIND_LABEL[kind]} 만들기</h2>
      <div className="gen-work is-picture">
        <div className="gen-work-left">
          <div className="gen-editor">
            <div className="gen-field">
              <label htmlFor="gen-scene-ko">장면(한국어)</label>
              <textarea id="gen-scene-ko" className="krds-input" rows={4} maxLength={400} value={scene.ko} disabled={!!busy} onChange={(e) => setScene({ ...scene, ko: e.target.value })} />
            </div>
            <div className="gen-editor-actions">
              <button type="button" className={`krds-btn small ${stale || !scene.en.trim() ? "secondary" : "tertiary"}`} disabled={!!busy || !scene.ko.trim()} onClick={translate}>{busy === "translate" ? "번역하는 중" : scene.en.trim() ? "영어로 다시 번역" : "영어로 번역"}</button>
              <span className="form-hint">누르면 한국어 장면이 외부 생성형 AI 서비스로 전송됩니다.</span>
            </div>
            {stale && <p className="form-hint gen-stale" role="status">한국어 장면을 수정했습니다. [영어로 다시 번역]을 눌러야 그림에 반영됩니다.</p>}
            {!scene.en.trim() && <p className="form-hint gen-stale" role="status">이미지 모델은 영어 장면으로 그림을 만듭니다. 한국어 장면을 적고 [영어로 번역]을 눌러 주세요.</p>}
            {/* 모델에 보내는 영어 장면은 접어 둔다 — 집필자가 다루는 것은 한국어 장면이고, 영어를 직접 고칠 사람만 펼친다 */}
            <details className="gen-en-detail">
            <summary>영어 장면 직접 수정</summary>
            <div className="gen-field">
              <label htmlFor="gen-scene-en">이미지 모델에 보내는 장면(영어)</label>
              <textarea id="gen-scene-en" className="krds-input" rows={6} maxLength={800} lang="en" value={scene.en} disabled={!!busy} onChange={(e) => setScene({ ...scene, en: e.target.value })} />
            </div>
            <p className="form-hint">이 장면에 화풍과 제한 문구(얼굴이 드러난 사람 없음, 글자, 로고, 워터마크 없음)가 항상 붙습니다.</p>
            <button type="button" className="krds-btn small tertiary" disabled={!scene.en.trim()} onClick={async () => setDone((await copyText(scene.en)) ? "영어 장면을 복사했습니다." : "복사하지 못했습니다.")}>영어 장면 복사</button>
            </details>
            <div className="gen-options">
              <div className="gen-field"><label htmlFor="gen-shape">비율</label>
                <select id="gen-shape" className="krds-form-select" value={options.shape} disabled={!!busy} onChange={(e) => setOptions({ ...options, shape: e.target.value })}>
                  {(engine?.모양 || []).map((entry) => <option key={entry.shape} value={entry.shape}>{entry.이름} {entry.width}×{entry.height}</option>)}
                </select></div>
              <div className="gen-field"><label htmlFor="gen-count">만들 장수</label>
                <select id="gen-count" className="krds-form-select" value={options.count} disabled={!!busy} onChange={(e) => setOptions({ ...options, count: Number(e.target.value) })}>
                  {Array.from({ length: engine?.["최대 장수"] || 4 }, (_, i) => <option key={i} value={i + 1}>{i + 1}장</option>)}
                </select></div>
            </div>
          </div>
          {/* 지적(problems)이 있으면 그 상자 하나만 보인다 — 서버의 한 줄 요약과 같은 내용이라 둘 다 보이면 같은 말이 두 번 나온다 */}
          {makeError && (makeError.problems?.length ? <Problems problems={makeError.problems} /> : <PageAlert kind="danger">{makeError.error}</PageAlert>)}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn medium primary" disabled={!!busy || !scene.en.trim() || !engine?.["사용 가능"]} onClick={make}>{busy === "image" ? "만드는 중" : made ? "다시 만들기" : "그림 만들기"}</button>
          </div>
        </div>
        <div id="generate-result" className="nav-anchor gen-work-right" aria-live="polite">
          {busy === "image" && <MakingProgress state={job?.state} count={options.count} cancelling={!!job?.cancelling} onCancel={cancelMaking} />}
          {stopped && busy !== "image" && <PageAlert kind="info">그림 만들기를 취소했습니다. 만들던 그림은 저장되지 않았습니다.</PageAlert>}
          {!made && busy !== "image" && (<>
            <ul className="gen-pictures is-empty" aria-hidden="true">
              {Array.from({ length: options.count }, (_, i) => (
                <li key={i}><div className="gen-slot" style={{ aspectRatio: shapeNow ? `${shapeNow.width} / ${shapeNow.height}` : "4 / 3" }}>{KIND_LABEL[kind]} {i + 1}</div></li>
              ))}
            </ul>
            <p className="meta gen-sent">[그림 만들기]를 누르면 이 자리에 {KIND_LABEL[kind]} {options.count}장이 표시됩니다.</p>
          </>)}
          {made && (<>
            <PageAlert kind="warning">만든 그림이 문단의 내용과 맞는지, 실제 장비나 작업과 다르지 않은지는 자동으로 검사하지 못합니다. 그림을 직접 확인해 주세요.</PageAlert>
            <Problems notes={made.notes} />
            <ul className="gen-pictures">
              {made.images.map((one, i) => (
                <li key={one.seed} className={pick === i ? "is-picked" : undefined}>
                  <img src={dataUrl(one.png)} alt={`만든 그림 ${i + 1}`} />
                  <button type="button" className={`krds-btn small ${pick === i ? "primary" : "secondary"}`} aria-pressed={pick === i} onClick={() => choosePicture(i)}>
                    {pick === i ? "선택한 그림" : "이 그림 선택"}<span className="sr-only"> {i + 1}</span></button>
                </li>
              ))}
            </ul>
            {/* 집필자에게는 한 줄만: 무엇으로 만들었고 무엇을 직접 확인해야 하는가. 모델에 보낸 영어 원문은 기록·재현용이라 접어 둔다 */}
            <p className="meta gen-sent">{made.tool ? `${made.tool} 모델로` : "이미지 모델로"} 만든 {KIND_LABEL[kind]}입니다. 얼굴, 글자, 로고가 나오지 않도록 요청했지만 그림에 남아 있을 수 있으니 직접 확인해 주세요.</p>
            <details className="gen-sent-detail">
              <summary>이미지 모델에 보낸 내용 보기</summary>
              <dl>
                <div><dt>보낸 장면</dt><dd lang="en">{made.sent?.prompt || made.prompt}</dd></div>
                {made.sent?.negative && <div><dt>제외하도록 요청한 것</dt><dd lang="en">{made.sent.negative}</dd></div>}
                <div><dt>모델</dt><dd>{made.model}</dd></div>
              </dl>
              <button type="button" className="krds-btn small tertiary"
                      onClick={async () => setSentCopied((await copyText([made.sent?.prompt || made.prompt, made.sent?.negative].filter(Boolean).join("\n\n"))) ? "복사했습니다." : "복사하지 못했습니다.")}>
                보낸 내용 복사</button>
              {sentCopied && <span className="meta" role="status"> {sentCopied}</span>}
            </details>
          </>)}
        </div>
      </div>

      {/* 고른 뒤의 일(확인, 표기 문구, 내려받기, DB 등록)은 2단 밖 전체 폭에 둔다 — 오른쪽 열에 두면 칸이 좁아 값이 잘리고 왼쪽 열 아래가 빈다 */}
      {image && (<div id="generate-finish" className="nav-anchor gen-finish">
      <h3 className="form-section-title gen-mark-title">내려받기 전 확인 사항</h3>
      <div className="gen-finish-check">
        <figure className="gen-finish-picture"><img src={dataUrl(image.png)} alt={`선택한 그림 ${pick + 1}`} /><figcaption>선택한 그림. 아래 세 가지를 이 그림에서 확인해 주세요.</figcaption></figure>
        <div>
      {!seen && <Spinner label="그림을 확인하는 중" />}
      {seen?.error && <PageAlert kind="danger">{seen.error}</PageAlert>}
      {seen && !seen.error && (<>
        <PageAlert kind={seen.충분 ? "success" : "warning"}>
          {seen.width}×{seen.height}px, 가로 {seen.width_mm}mm 기준 {seen.dpi} DPI입니다.
          {seen.충분 ? "" : ` 300 DPI가 되려면 가로 ${seen["300 DPI 폭"]}mm 이하로 넣거나, 원고에 넣은 뒤 업스케일링으로 화질을 높여야 합니다.`}
        </PageAlert>
        {similar && (similar["닮은 그림"].length === 0
          ? <p className="form-hint">{similar.범위} {similar["대조한 그림"]}장과 비교했습니다. 유사한 그림을 찾지 못했습니다.</p>
          : (<>
            <PageAlert kind="warning">이미지 저작권 DB에 유사한 그림이 있습니다. 같은 그림이거나 지나치게 비슷한지 직접 확인해 주세요.</PageAlert>
            <ul className="gen-similar">
              {similar["닮은 그림"].map((entry) => (
                <li key={entry.id}>
                  <img src={canManage ? api.images.fileUrl(entry.id) : api.images.recommendableFileUrl(entry.id)} alt={entry.title || "제목 없는 그림"} loading="lazy" />
                  <div><strong>{entry.title || "제목 없음"}</strong>
                    <span className="meta">{ASSET_LABEL[entry.kind] || "종류 없음"}, {METHOD_LABEL[entry.방법] || entry.방법}, 유사도 {entry.점수}, {entry.확정 ? "기관 확정" : "확정 전"}</span></div>
                </li>
              ))}
            </ul>
          </>))}
        <div className="gen-confirms">
          {CONFIRMS.map(([key, label]) => (
            <div className="krds-form-check" key={key}>
              <input type="checkbox" id={`gen-confirm-${key}`} checked={!!confirmed[key]} onChange={(e) => setConfirmed({ ...confirmed, [key]: e.target.checked })} />
              <label htmlFor={`gen-confirm-${key}`}>{label}</label>
            </div>
          ))}
        </div>
        <p className="form-hint">세 가지를 모두 확인해야 내려받거나 이미지 저작권 DB에 등록할 수 있습니다. 하나라도 해당하지 않으면 장면을 수정해 다시 만들어 주세요.</p>
      </>)}
        </div>
      </div>

      <h3 className="form-section-title gen-mark-title">원고 표기 문구<span className="meta"> 표기 예 {usage}({usage === 1 ? "문단을 바탕으로 생성" : "AI 창작"})</span></h3>
      <div className="gen-mark-fields is-four">
        <div className="gen-field"><label htmlFor="gen-title">제목</label>
          <input id="gen-title" type="text" className="krds-input" maxLength={40} value={mark.title} onChange={(e) => setMark({ ...mark, title: e.target.value })} /></div>
        <div className="gen-field"><label htmlFor="gen-tool">활용한 AI 도구</label>
          <input id="gen-tool" type="text" className="krds-input" maxLength={40} value={mark.tool} onChange={(e) => setMark({ ...mark, tool: e.target.value })} /></div>
        <div className="gen-field"><label htmlFor="gen-date">활용 일자</label>
          <input id="gen-date" type="date" className="krds-input" value={mark.date} onChange={(e) => setMark({ ...mark, date: e.target.value || today() })} /></div>
        <div className="gen-field"><label htmlFor="gen-number">번호 <span className="meta">(선택)</span></label>
          <input id="gen-number" type="text" className="krds-input" maxLength={10} value={mark.number} placeholder="예: 1-2" onChange={(e) => setMark({ ...mark, number: e.target.value.trim() })} /></div>
      </div>
      {marking?.error && <p className="form-hint-invalid" role="alert">{marking.error}</p>}
      {marking?.lines && (
        <div className="recommend-credit gen-mark-lines">
          <code>{marking.lines.map((line) => <span key={line}>{line}</span>)}</code>
          <button type="button" className="krds-btn small secondary" onClick={async () => setDone((await copyText(marking.lines.join("\n"))) ? "표기 문구를 복사했습니다." : "복사하지 못했습니다.")}>표기 문구 복사</button>
        </div>
      )}
      {marking?.note && <p className="form-hint">{marking.note}</p>}
      <p className="form-hint">서약서에 첨부할 결과물 현황은 그림을 원고에 넣은 뒤 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.</p>
      {done && <PageAlert kind="success">{done}</PageAlert>}
      <div className="run-buttons image-actions">
        <button type="button" className="krds-btn medium primary" disabled={!allConfirmed} onClick={save}>그림(PNG) 내려받기</button>
      </div>

      {hasDb && canManage && (<>
        <h3 className="form-section-title gen-mark-title">이미지 저작권 DB</h3>
        <p className="form-hint">내려받기와 별개이며 선택 사항입니다. 다른 집필자의 추천 후보로 쓰려면 이 그림을 이미지 저작권 DB에 등록합니다. 분류는 ‘집필진 제작’, AI 활용 유형은 {usage}로 도구, 일자와 함께 기록합니다. 권리 귀속과 재사용 범위는 정하지 않습니다. 확정하기 전에는 추천 목록에 나오지 않습니다.</p>
        <div className="gen-mark-fields">
          <div className="gen-field"><label htmlFor="gen-module">모듈 코드 <span className="meta">(선택)</span></label>
            <input id="gen-module" type="text" className="krds-input" maxLength={30} value={store.module} placeholder="예: LM1203020201_24v3" onChange={(e) => setStore({ ...store, module: e.target.value })} /></div>
          {needsName && (
            <div className="gen-field"><label htmlFor="gen-by">등록자</label>
              <input id="gen-by" type="text" className="krds-input" maxLength={80} value={store.by} onChange={(e) => setStore({ ...store, by: e.target.value })} /></div>
          )}
        </div>
        {store.error && <PageAlert kind="danger">{store.error}</PageAlert>}
        {store.result && <PageAlert kind="success">{store.result["새 그림"] ? "이미지 저작권 DB에 등록했습니다." : "같은 그림이 이미 있어 정보를 합쳤습니다."} <Link to="/images">이미지 저작권 DB</Link>에서 권리 정보를 확인하고 확정해 주세요.</PageAlert>}
        <div className="run-buttons image-actions">
          <button type="button" className="krds-btn medium secondary" disabled={!allConfirmed || store.busy || !mark.tool.trim() || (needsName && !store.by.trim())} onClick={register}>{store.busy ? "등록하는 중" : "이미지 저작권 DB에 등록"}</button>
        </div>
      </>)}
      </div>)}

    </section>
    )}
    </>
  );
}
