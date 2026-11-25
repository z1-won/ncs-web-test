// 사진·삽화 만들기(REQ-02-006 ① AI 생성) — 이미지 AI 생성 페이지가 유형을 사진이나 삽화로 골랐을 때 후보와 고치고 받기 자리에 놓는다.
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
const ASSET_LABEL = { photo: "사진", illustration: "삽화", table: "도표", graph: "그래프", screenshot: "화면 캡처", other: "기타" };
const CONFIRMS = [
  ["face", "얼굴이 드러난 사람이 없습니다(뒷모습, 멀리 있는 모습, 손은 됩니다)"],
  ["letters", "읽히는 글자, 로고, 상표가 없습니다"],
  ["real", "실제 장비와 작업 모습과 다르지 않습니다"],
];
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const dataUrl = (png) => `data:image/png;base64,${png}`;
async function toBlob(png) { return (await fetch(dataUrl(png))).blob(); }

// 같은 갈래의 지적은 한 줄로 묶는다('얼굴이 드러나는 그림은 만들지 않습니다: 웃는, 얼굴, portrait')
const PROBLEM_LEAD = {
  face: ["얼굴이 드러나는 그림은 만들지 않습니다", "뒷모습, 멀리 있는 모습, 손은 됩니다."],
  imitate: ["특정 작가·작품·상표의 화풍을 따르게 하지 않습니다", ""],
  brand: ["상표·상품명은 넣지 않습니다", "일반 명칭으로 바꿔 주세요."],
};
function groupProblems(problems) {
  const groups = new Map();
  for (const problem of problems) groups.set(problem.kind, [...(groups.get(problem.kind) || []), problem.text]);
  return [...groups].map(([kind, texts]) => {
    const [lead, tail] = PROBLEM_LEAD[kind] || ["만들지 않는 내용입니다", ""];
    return `${lead}: ${texts.join(", ")}${tail ? `. ${tail}` : ""}`;
  });
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
  const [busy, setBusy] = useState("");                         // "" | "translate" | "image"
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

  function choose(entry) {
    setScene({ ko: entry.ko, en: entry.en }); setMade(null); setPick(null); setMakeError(null);
    setTimeout(() => document.getElementById("generate-edit")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  async function translate() {
    setBusy("translate"); setMakeError(null);
    const { ok, data, error: message } = await api.generate.prompt({ text, criterion, kind, focus, scene: scene.ko });
    setBusy("");
    if (!ok) { setMakeError({ error: message }); return; }
    const first = data.scenes[0];
    if (!first) { setMakeError({ error: plainReason(data.note) || "영어 글을 만들지 못했습니다. 직접 적어 주세요." }); return; }
    setScene({ ko: scene.ko, en: first.en });
    if (!first.ok) setMakeError({ error: "이 장면으로는 만들지 않습니다.", problems: first.problems });
  }

  async function make() {
    setBusy("image"); setMakeError(null); setMade(null); setPick(null);
    const { ok, data, error: message } = await api.generate.image({ scene: scene.en, scene_ko: scene.ko, kind, shape: options.shape, count: options.count });
    setBusy("");
    if (!ok) { setMakeError({ error: message, problems: data?.problems }); return; }
    setMade(data);
  }

  async function save() {
    saveBlob(await toBlob(image.png), `${(mark.title || KIND_LABEL[kind]).replace(/[\\/:*?"<>|]+/g, "_")}.png`);
    setDone(`그림을 내려받았습니다. 원고에는 가로 ${seen?.["300 DPI 폭"] || ""}mm 이하로 놓아야 300 DPI가 됩니다.`);
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
  return (
    <>
    <section id="generate-candidates" className="nav-anchor image-section" aria-live="polite">
      <h2 className="section-title">후보{drafted && !request.manual && <span className="meta"> 장면 {drafted.scenes.length}개 가운데 {drafted.usable}개 통과</span>}</h2>
      {error && <PageAlert kind="danger">{error}</PageAlert>}
      {!drafted && !error && <Spinner label="장면을 만드는 중" />}
      {!engine?.["사용 가능"] && (
        <PageAlert kind="info">이 서버에서는 지금 그림을 만들 수 없습니다. {engine?.이유}{"\n"}장면과 모델에 보낼 글까지는 만들 수 있습니다. 바깥 도구로 만든 그림의 표기와 결과물 현황은 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.</PageAlert>
      )}
      {drafted && !request.manual && (<>
        <p className="recommend-method">
          <span className={`krds-badge ${drafted.method === "llm" ? "bg-light-information" : "bg-light-gray"}`}>{drafted.method === "llm" ? `생성형 AI${drafted.model ? `(${drafted.model})` : ""}` : "생성형 AI 사용 안 함"}</span>
          <span className="meta"> {plainReason(drafted.note)}{drafted.reason ? ` 생성형 AI의 설명: ${drafted.reason}` : ""}</span>
        </p>
        <ul className="gen-candidates">
          {drafted.scenes.map((entry, i) => (
            <li key={i} className={`gen-candidate${entry.ok ? "" : " is-rejected"}`}>
              <h3><span className="gen-candidate-name">장면 {i + 1}</span>
                <span className="gen-candidate-badges"><span className={`krds-badge ${entry.ok ? "bg-light-success" : "bg-light-danger"}`}>{entry.ok ? "검사 통과" : "쓰지 않음"}</span></span></h3>
              <p className="gen-scene">{entry.ko}</p>
              <p className="gen-scene meta" lang="en">{entry.en}</p>
              <Problems problems={entry.problems} notes={entry.notes} />
              <div className="gen-candidate-actions">
                <button type="button" className={`krds-btn small ${entry.ok ? "primary" : "tertiary"}`} onClick={() => choose(entry)}>
                  {entry.ok ? "이 장면 고르기" : "고쳐서 쓰기"}<span className="sr-only"> 장면 {i + 1}</span></button>
              </div>
            </li>
          ))}
        </ul>
        {!scene && (
          <div className="run-buttons image-actions gen-enter">
            <button type="button" className="krds-btn medium secondary" onClick={() => choose({ ko: focus || "", en: "" })}>장면을 직접 적기</button>
          </div>
        )}
      </>)}
    </section>

    {scene && (
    <section id="generate-edit" className="nav-anchor image-section">
      <h2 className="section-title">고치고 받기<span className="meta"> {KIND_LABEL[kind]}, 표기 예 {usage}({usage === 1 ? "문단을 바탕으로 생성" : "AI 창작"})</span></h2>
      <PageAlert kind="warning">만든 그림이 문단의 내용과 맞는지, 실제 장비·작업과 다르지 않은지는 자동으로 검사하지 못합니다. 그림을 직접 보고 확인해 주세요.</PageAlert>
      <div className="gen-work">
        <div className="gen-work-left">
          {text.trim() && <blockquote className="gen-source"><strong>문단</strong>{text}</blockquote>}
          <div className="gen-editor">
            <div className="gen-field">
              <label htmlFor="gen-scene-ko">장면(한국어)</label>
              <textarea id="gen-scene-ko" className="krds-input" rows={3} maxLength={400} value={scene.ko} disabled={!!busy} onChange={(e) => setScene({ ...scene, ko: e.target.value })} />
            </div>
            <div className="gen-editor-actions">
              <button type="button" className="krds-btn small tertiary" disabled={!!busy || !scene.ko.trim()} onClick={translate}>{busy === "translate" ? "옮기는 중" : "이 장면으로 영어 글 다시 쓰기"}</button>
            </div>
            <div className="gen-field">
              <label htmlFor="gen-scene-en">모델에 보내는 장면 글(영어)</label>
              <textarea id="gen-scene-en" className="krds-input" rows={4} maxLength={800} lang="en" value={scene.en} disabled={!!busy} onChange={(e) => setScene({ ...scene, en: e.target.value })} />
            </div>
            <p className="form-hint">이 글 뒤에 화풍과 제한 문구(얼굴이 드러난 사람 없음, 글자·로고·워터마크 없음)가 항상 붙습니다. [영어 글 다시 쓰기]는 한국어 장면을 외부 생성형 AI 서비스로 보냅니다.</p>
            <div className="gen-mark-fields">
              <div className="gen-field"><label htmlFor="gen-shape">모양</label>
                <select id="gen-shape" className="krds-form-select" value={options.shape} disabled={!!busy} onChange={(e) => setOptions({ ...options, shape: e.target.value })}>
                  {(engine?.모양 || []).map((entry) => <option key={entry.shape} value={entry.shape}>{entry.이름} {entry.width}×{entry.height}</option>)}
                </select></div>
              <div className="gen-field"><label htmlFor="gen-count">장수</label>
                <select id="gen-count" className="krds-form-select" value={options.count} disabled={!!busy} onChange={(e) => setOptions({ ...options, count: Number(e.target.value) })}>
                  {Array.from({ length: engine?.["최대 장수"] || 4 }, (_, i) => <option key={i} value={i + 1}>{i + 1}장</option>)}
                </select></div>
            </div>
          </div>
          {makeError && <PageAlert kind="danger">{makeError.error}</PageAlert>}
          {makeError?.problems && <Problems problems={makeError.problems} />}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn medium primary" disabled={!!busy || !scene.en.trim() || !engine?.["사용 가능"]} onClick={make}>{busy === "image" ? "만드는 중" : made ? "다시 만들기" : "그림 만들기"}</button>
            <button type="button" className="krds-btn medium secondary" disabled={!scene.en.trim()} onClick={async () => setDone((await copyText(scene.en)) ? "모델에 보내는 장면 글을 복사했습니다." : "복사하지 못했습니다.")}>장면 글 복사</button>
          </div>
        </div>
        <div className="gen-work-right" aria-live="polite">
          {busy === "image" && <div className="gen-preview is-loading"><Spinner label="서버의 모델이 그림을 만드는 중입니다. 컴퓨터에 따라 몇 분이 걸릴 수 있습니다" /></div>}
          {!made && busy !== "image" && <p className="meta">장면을 고친 뒤 [그림 만들기]를 누르면 여기에 그림이 보입니다.</p>}
          {made && (<>
            <Problems notes={made.notes} />
            <ul className="gen-pictures">
              {made.images.map((one, i) => (
                <li key={one.seed} className={pick === i ? "is-picked" : undefined}>
                  <img src={dataUrl(one.png)} alt={`만든 그림 ${i + 1}`} />
                  <button type="button" className={`krds-btn small ${pick === i ? "primary" : "secondary"}`} aria-pressed={pick === i} onClick={() => setPick(i)}>
                    {pick === i ? "고른 그림" : "이 그림 고르기"}<span className="sr-only"> {i + 1}</span></button>
                </li>
              ))}
            </ul>
            <p className="meta gen-sent">모델({made.model})에 보낸 글: <span lang="en">{made.prompt}</span></p>
          </>)}
        </div>
      </div>

      {image && (<>
      <h3 className="form-section-title gen-mark-title">받기 전에 확인할 것</h3>
      {!seen && <Spinner label="그림을 확인하는 중" />}
      {seen?.error && <PageAlert kind="danger">{seen.error}</PageAlert>}
      {seen && !seen.error && (<>
        <PageAlert kind={seen.충분 ? "success" : "warning"}>
          {seen.width}×{seen.height}px, 가로 {seen.width_mm}mm에 놓으면 {seen.dpi} DPI입니다.
          {seen.충분 ? "" : ` 300 DPI가 되려면 가로 ${seen["300 DPI 폭"]}mm 이하로 놓거나, 원고에 넣은 뒤 업스케일링으로 화질을 높여야 합니다.`}
        </PageAlert>
        {similar && (similar["닮은 그림"].length === 0
          ? <p className="form-hint">{similar.범위} {similar["대조한 그림"]}장과 견주어 닮은 그림을 찾지 못했습니다.</p>
          : (<>
            <PageAlert kind="warning">이미지 저작권 DB에 닮은 그림이 있습니다. 같은 그림이거나 지나치게 닮았는지 직접 보고 판단해 주세요.</PageAlert>
            <ul className="gen-similar">
              {similar["닮은 그림"].map((entry) => (
                <li key={entry.id}>
                  <img src={canManage ? api.images.fileUrl(entry.id) : api.images.recommendableFileUrl(entry.id)} alt={entry.title || "제목 없는 그림"} loading="lazy" />
                  <div><strong>{entry.title || "제목 없음"}</strong>
                    <span className="meta">{ASSET_LABEL[entry.kind] || "종류 없음"}, {entry.방법}{entry.거리 > 0 ? ` 거리 ${entry.거리}` : ""}, 점수 {entry.점수}, {entry.확정 ? "기관 확정" : "확정 전"}</span></div>
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
        <p className="form-hint">세 가지를 모두 확인해야 내려받거나 이미지 저작권 DB에 올릴 수 있습니다. 하나라도 아니면 장면을 고쳐 다시 만들어 주세요.</p>
      </>)}

      <h3 className="form-section-title gen-mark-title">원고에 붙일 표기</h3>
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
          <button type="button" className="krds-btn small secondary" onClick={async () => setDone((await copyText(marking.lines.join("\n"))) ? "표기 줄을 복사했습니다." : "복사하지 못했습니다.")}>표기 줄 복사</button>
        </div>
      )}
      {marking?.note && <p className="form-hint">{marking.note}</p>}
      <p className="form-hint">서약서에 붙일 결과물 현황은 그림을 원고에 넣은 뒤 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.</p>
      {done && <PageAlert kind="success">{done}</PageAlert>}
      <div className="run-buttons image-actions">
        <button type="button" className="krds-btn medium primary" disabled={!allConfirmed} onClick={save}>그림(PNG) 내려받기</button>
      </div>

      {hasDb && canManage && (<>
        <h3 className="form-section-title gen-mark-title">이미지 저작권 DB</h3>
        <p className="form-hint">이 그림을 이미지 저작권 DB에 올립니다. 분류는 집필진 제작, AI 활용 유형은 {usage}로 도구와 일자와 함께 적습니다. 권리 귀속과 재사용 범위는 정하지 않으므로 확정하기 전에는 추천에 나오지 않습니다.</p>
        <div className="gen-mark-fields">
          <div className="gen-field"><label htmlFor="gen-module">모듈 코드 <span className="meta">(선택)</span></label>
            <input id="gen-module" type="text" className="krds-input" maxLength={30} value={store.module} placeholder="예: LM1203020201_24v3" onChange={(e) => setStore({ ...store, module: e.target.value })} /></div>
          {needsName && (
            <div className="gen-field"><label htmlFor="gen-by">올리는 사람</label>
              <input id="gen-by" type="text" className="krds-input" maxLength={80} value={store.by} onChange={(e) => setStore({ ...store, by: e.target.value })} /></div>
          )}
        </div>
        {store.error && <PageAlert kind="danger">{store.error}</PageAlert>}
        {store.result && <PageAlert kind="success">{store.result["새 그림"] ? "이미지 저작권 DB에 올렸습니다." : "같은 그림이 이미 있어 정보를 합쳤습니다."} <Link to="/images">이미지 저작권 DB</Link>에서 권리 정보를 확인하고 확정해 주세요.</PageAlert>}
        <div className="run-buttons image-actions">
          <button type="button" className="krds-btn medium secondary" disabled={!allConfirmed || store.busy || !mark.tool.trim() || (needsName && !store.by.trim())} onClick={register}>{store.busy ? "올리는 중" : "이미지 저작권 DB에 올리기"}</button>
        </div>
      </>)}
      </>)}
    </section>
    )}
    </>
  );
}
