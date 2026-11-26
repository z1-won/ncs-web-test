// 이미지 저작권 DB — 그림 1건 상세: 그림 보기, 수록 위치·수행준거, 권리 정보 입력, 기관 확정/확정 취소, 증빙 등록·삭제, 그림 설명 확인, 변경 이력.
// 그림 설명(REQ-02-011 설명 색인)은 그림을 본 모델이 쓴 글이다. 에디터와 직능연이 그림과 견주어 읽고, 틀린 곳을 고쳐 확인한다.
// 추천은 사람이 확인한 설명을 먼저 읽는다. 설명은 권리 정보가 아니라서 기관 확정 여부와 상관없이 고칠 수 있다.
// 증빙은 기관 확정 여부와 상관없이 등록·삭제할 수 있다. 서류 파일은 올리지 않고 종류·파일 이름(보관 위치)·제출일·비고만 남긴다.
// 권리 정보는 자동 태깅 상태에서만 고칠 수 있다(확정된 것은 확정을 푼 뒤). 저장·확정 요청에는 화면이 열어 본 버전을 실어
// 그사이 다른 사람이 바꿨으면 서버가 409로 거절한다 — 그때는 다시 읽어 온다.
import React, { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.jsx";
import { conditionsLabel, conditionsOf, licenseChoice, licenseOptions, statusBadge, termOptions } from "../lib/imageTerms.js";
import { Spinner } from "./Badge.jsx";
import { KrdsDateField } from "./KrdsDateField.jsx";
import { KrdsSelect } from "./KrdsSelect.jsx";
import { PageAlert } from "./PageAlert.jsx";

const TEXT_FIELDS = ["author", "source_org", "source_url", "credit_line"];
const NEW_EVIDENCE = { kind: "", fileRef: "", submittedOn: "", note: "" };
// 그림 설명의 그림 종류(ncs_recommend.describe.KINDS)와 검사 기준(clean: 장면 10자 이상, 핵심어 2개 이상)
const DESCRIPTION_KIND_OPTIONS = [
  { value: "photo", label: "사진" }, { value: "illustration", label: "삽화" }, { value: "diagram", label: "도해" }, { value: "flowchart", label: "흐름도" },
  { value: "table", label: "표" }, { value: "graph", label: "그래프" }, { value: "screenshot", label: "화면 캡처" }, { value: "other", label: "기타" },
];
const MIN_SCENE = 10;
const MIN_KEYWORDS = 2;

const descriptionForm = (item) => ({ kind: item.kind || "other", scene: item.scene || "", keywords: (item.keywords || []).join(", "),
                                     visibleText: (item.visible_text || []).join("\n") });
const splitList = (text, pattern) => [...new Set(text.split(pattern).map((word) => word.trim()).filter(Boolean))];

// 그림 설명 한 벌(엔진 하나의 것): 읽고, 고치고, 확인한다. 대상 목록은 읽기만 한다(고치지 않고 그대로 보낸다)
function DescriptionCard({ item, index, readOnly, busy, onCheck, onUncheck }) {
  const [form, setForm] = useState(() => descriptionForm(item));
  useEffect(() => { setForm(descriptionForm(item)); }, [item]);
  const id = `image-description-${index}`;
  const dirty = JSON.stringify(form) !== JSON.stringify(descriptionForm(item));
  const keywords = splitList(form.keywords, /[,\n]/);
  const visibleText = splitList(form.visibleText, /\n/);
  const problem = form.scene.trim().length < MIN_SCENE ? `장면 설명을 ${MIN_SCENE}자 이상 적어 주세요.`
    : keywords.length < MIN_KEYWORDS ? `핵심어를 ${MIN_KEYWORDS}개 이상 적어 주세요.` : "";
  const checked = !!item.checked_by;
  const text = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  return (
    <div className="fieldset review-form is-sectioned image-evidence-form">
      <div className="form-section" role="group" aria-labelledby={`${id}-title`}>
        <h4 className="form-section-title" id={`${id}-title`}>
          {item.engine}{" "}
          <span className={`krds-badge ${checked ? "bg-light-success" : "bg-light-warning"}`}>{checked ? "사람이 확인함" : "확인 전"}</span>
          <span className="meta"> {checked ? `${item.checked_by}, ${formatDate(item.checked_at)}` : `모델이 씀, ${formatDate(item.created_at)}`}</span>
        </h4>
        <div className="form-section-grid">
          <div className="form-group">
            <div className="form-tit"><label htmlFor={`${id}-kind`}>그림 종류</label></div>
            <div className="form-conts">
              {readOnly
                ? <input id={`${id}-kind`} type="text" className="krds-input" value={DESCRIPTION_KIND_OPTIONS.find((o) => o.value === form.kind)?.label || ""} disabled readOnly />
                : <KrdsSelect id={`${id}-kind`} value={form.kind} options={DESCRIPTION_KIND_OPTIONS} onChange={(value) => setForm((prev) => ({ ...prev, kind: value }))} title="그림 종류 선택" />}
            </div>
          </div>
          <div className="form-group form-group-wide is-full">
            <div className="form-tit"><label htmlFor={`${id}-scene`}>장면 설명</label></div>
            <div className="form-conts">
              <textarea id={`${id}-scene`} className="krds-input" rows={4} maxLength={600} value={form.scene} onChange={text("scene")} disabled={readOnly} />
            </div>
            <p className="form-hint">그림에 보이는 것만 적습니다. 용도나 의도를 짐작해 쓴 문장은 지워 주세요.</p>
          </div>
          <div className="form-group form-group-wide is-full">
            <div className="form-tit"><label htmlFor={`${id}-keywords`}>핵심어</label></div>
            <div className="form-conts">
              <input id={`${id}-keywords`} type="text" className="krds-input" value={form.keywords} onChange={text("keywords")} disabled={readOnly} />
            </div>
            <p className="form-hint">쉼표로 나눠 적습니다. 추천이 문단의 낱말과 맞춰 보는 글입니다. 그림에 없는 낱말은 지우고, 같은 대상의 다른 이름은 더해 주세요(10개까지).</p>
          </div>
          <div className="form-group form-group-wide is-full">
            <div className="form-tit"><label htmlFor={`${id}-text`}>그림 속 글자</label></div>
            <div className="form-conts">
              <textarea id={`${id}-text`} className="krds-input" rows={3} value={form.visibleText} onChange={text("visibleText")} disabled={readOnly} />
            </div>
            <p className="form-hint">한 줄에 하나씩. 그림에 적힌 그대로인지 봐 주세요. 없으면 비워 둡니다.</p>
          </div>
        </div>
        {(item.objects || []).length > 0 && (
          <p className="form-hint">모델이 본 대상: {item.objects.map((object) => `${object.name}${object.position ? `(${object.position})` : ""}`).join(", ")}.
            대상 이름도 추천이 낱말로 맞춰 봅니다. 이 목록은 여기서 고치지 않습니다.</p>
        )}
      </div>
      {!readOnly && (
        <div className="form-actions">
          {problem && <PageAlert kind="warning">{problem}</PageAlert>}
          <div className="run-buttons image-actions">
            {checked && !dirty && <button type="button" className="krds-btn large tertiary" disabled={!!busy} onClick={() => onUncheck(item)}>확인 취소</button>}
            {(!checked || dirty) && (
              <button type="button" className="krds-btn large secondary" disabled={!!busy || !!problem}
                      onClick={() => onCheck(item, { engine: item.engine, kind: form.kind, scene: form.scene.trim(), objects: item.objects || [], visibleText, keywords }, dirty)}>
                {busy === "description" ? "처리하는 중" : dirty ? "고친 내용 저장하고 확인" : "그림과 맞음, 확인"}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// 서버의 rights → 입력칸 상태(모두 문자열·불리언)
function toForm(rights) {
  const r = rights || {};
  const text = (key) => r[key] ?? "";
  return {
    category: text("category"), ownership: text("ownership"), reuse_scope: r.reuse_scope || "unknown", release_class: text("release_class"),
    license: licenseChoice(r), kogl_ai: !!r.kogl_ai, license_note: text("license_note"),
    author: text("author"), source_org: text("source_org"), source_url: text("source_url"), credit_line: text("credit_line"),
    retrieved_on: text("retrieved_on"),
    ai_used: !!r.ai_used, ai_usage: r.ai_usage ? String(r.ai_usage) : "", ai_tool: text("ai_tool"), ai_date: text("ai_date"),
    ai_original_source: text("ai_original_source"), ai_tos_scope: text("ai_tos_scope"), ai_pledge_submitted: !!r.ai_pledge_submitted,
  };
}

// 입력칸 상태 → 수정 요청의 rights(레코드의 rights와 같은 모양, 비운 칸은 null)
function toRequest(form) {
  const blank = (value) => (value && value.trim() ? value.trim() : null);
  const note = blank(form.license_note);
  let license = null;
  if (form.license.startsWith("kogl-")) license = { kogl_type: Number(form.license.slice(5)), kogl_ai: form.kogl_ai, note };
  else if (form.license.startsWith("cc-")) license = { cc: form.license.slice(3), note };
  else if (form.license) license = { scheme: form.license, note };
  const ai = form.ai_used ? {
    used: true, usage: form.ai_usage ? Number(form.ai_usage) : null, tool: blank(form.ai_tool), date: blank(form.ai_date),
    original_source: blank(form.ai_original_source), tos_scope: blank(form.ai_tos_scope), pledge_submitted: form.ai_pledge_submitted,
  } : null;
  return {
    category: blank(form.category), ownership: blank(form.ownership), reuse_scope: form.reuse_scope || "unknown",
    release_class: blank(form.release_class), license, ai, retrieved_on: blank(form.retrieved_on),
    ...Object.fromEntries(TEXT_FIELDS.map((key) => [key, blank(form[key])])),
  };
}

const HISTORY_COLUMN_NAMES = {
  status: "확정 상태", confirmed_by: "확정자", category: "분류 체계", ownership: "권리 귀속", reuse_scope: "재사용 범위",
  release_class: "산출물 분류", license_scheme: "라이선스 체계", kogl_type: "공공누리 유형", kogl_ai: "AI유형 병행", cc_license: "CC 유형",
  license_note: "라이선스 메모", attribution: "출처표시", non_commercial: "상업적 이용금지", no_derivatives: "변경금지",
  share_alike: "동일조건변경허락", author: "저작자", source_org: "원 출처 기관", source_url: "출처 URL", retrieved_on: "확인 일자",
  credit_line: "출처 문구", ai_used: "AI 활용", ai_usage: "AI 활용 유형", ai_mode: "AI 활용 방식", ai_tool: "AI 도구", ai_date: "AI 활용 일자",
  ai_original_source: "원본 출처", ai_pledge_submitted: "서약서 제출", ai_tos_scope: "약관상 이용 범위",
  placements: "수록 위치", links: "수행준거 연결", rights: "권리 정보", evidence: "증빙",
};

function show(value) {
  if (value === null || value === undefined || value === "") return "없음";
  if (value === true) return "예";
  if (value === false) return "아니요";
  return String(value);
}

// 코드로 저장되는 열 → /api/images/terms의 어느 묶음에서 이름을 찾는가
const TERM_OF = { status: "status", category: "category", ownership: "ownership", reuse_scope: "reuse_scope", release_class: "release_class",
                  license_scheme: "license_scheme", ai_mode: "ai_mode" };

// 변경 이력 한 줄의 changes({열: [이전, 이후]} 또는 등록 때의 {placements: 2, …}) → 읽을 수 있는 글. 코드는 이름으로 바꿔 보여 준다
function changeText(entry, terms) {
  const parts = Object.entries(entry.changes || {}).map(([key, value]) => {
    const name = HISTORY_COLUMN_NAMES[key] || key;
    const named = (item) => (typeof item === "string" && terms?.[TERM_OF[key]]?.[item]) || show(item);
    return Array.isArray(value) ? `${name}: 이전 ${named(value[0])}, 이후 ${named(value[1])}` : `${name} ${show(value)}`;
  });
  return parts.join(", ");
}

export function ImageDetail({ imageId, terms, readOnly = false, onChanged, onClose }) {
  const [state, setState] = useState({ status: "loading" });   // { status: loading|ready|error, data, error }
  const [form, setForm] = useState(() => toForm(null));
  const [busy, setBusy] = useState(null);     // "save" | "confirm" | "unconfirm" | "evidence"
  const [evidence, setEvidence] = useState(NEW_EVIDENCE);   // 새로 등록할 증빙의 입력칸
  const [message, setMessage] = useState(null);   // { kind, text, at } — at: 알림을 보일 자리("rights" | "evidence" | "description")
  const [upscaledView, setUpscaledView] = useState(false);

  function accept(data) {
    setState({ status: "ready", data });
    setForm(toForm(data.rights));
  }

  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    setMessage(null);
    setUpscaledView(false);
    setEvidence(NEW_EVIDENCE);
    api.images.get(imageId).then(({ ok, data, error }) => {
      if (!current) return;
      if (!ok) { setState({ status: "error", error }); return; }
      accept(data);
    });
    return () => { current = false; };
  }, [imageId]);

  const data = state.data;
  const rights = data?.rights;
  const confirmed = rights?.status === "confirmed";
  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(toForm(rights)), [form, rights]);
  const licenseChoices = useMemo(() => licenseOptions(terms), [terms]);
  const usageOptions = useMemo(
    () => [{ value: "", label: "선택 안 함" },
           ...Object.entries(terms?.ai_usage || {}).map(([no, item]) => ({ value: no, label: `${no}. ${item.name} (${terms.ai_mode?.[item.mode] || item.mode})` }))],
    [terms]);

  if (state.status === "loading") return <section className="image-detail"><Spinner label="그림 정보를 읽는 중" /></section>;
  if (state.status === "error") return <section className="image-detail"><PageAlert kind="danger">{state.error}</PageAlert></section>;

  const [statusText, statusTone] = statusBadge(rights?.status, terms);
  const derived = conditionsOf(form.license, terms);
  const set = (key) => (value) => setForm((prev) => ({ ...prev, [key]: value }));
  const setText = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  const setCheck = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.checked }));

  // 요청 하나를 보내고 결과를 반영한다. 성공하면 받은 상세를 돌려준다(이어서 확정할 때 그 버전을 쓴다)
  async function send(kind, call, done) {
    setBusy(kind);
    setMessage(null);
    const { ok, data: next, error, status } = await call();
    const at = kind === "evidence" || kind === "description" ? kind : "rights";
    setBusy(null);
    if (!ok) {
      setMessage({ kind: "danger", text: error, at });
      if (status === 409) {   // 다른 사람이 먼저 바꿨거나 상태가 달라졌다 — 지금 값을 다시 읽어 보여 준다
        const fresh = await api.images.get(imageId);
        if (fresh.ok) setState({ status: "ready", data: fresh.data });
      }
      return null;
    }
    accept(next);
    setMessage({ kind: next.notice ? "info" : "success", text: next.notice ? `${done} ${next.notice}` : done, at });
    onChanged();
    return next;
  }

  const save = () => send("save", () => api.images.updateRights(imageId, { version: rights?.version, rights: toRequest(form) }), "저장했습니다.");

  async function confirm() {
    let version = rights?.version;
    if (dirty || !rights) {   // 고친 내용이 있으면 먼저 저장하고 그 버전으로 확정한다
      const saved = await save();
      if (!saved) return;
      version = saved.rights?.version;
    }
    await send("confirm", () => api.images.confirm(imageId, { version }), "기관 확정했습니다.");
  }

  const unconfirm = () => send("unconfirm", () => api.images.unconfirm(imageId, { version: rights?.version }), "확정을 취소했습니다. 이제 수정할 수 있습니다.");

  const evidenceOptions = termOptions(terms?.evidence_kind, "종류 선택");
  async function addEvidence() {
    const added = await send("evidence", () => api.images.addEvidence(imageId, evidence), "증빙을 등록했습니다.");
    if (added) setEvidence(NEW_EVIDENCE);
  }
  const removeEvidence = (item) => send("evidence", () => api.images.removeEvidence(imageId, item.id), "증빙을 삭제했습니다.");
  const checkDescription = (item, payload, edited) => send("description", () => api.images.checkDescription(imageId, payload),
    edited ? "고친 설명을 저장하고 확인했습니다. 추천은 이 설명을 먼저 읽습니다." : "설명을 확인했습니다. 추천은 이 설명을 먼저 읽습니다.");
  const uncheckDescription = (item) => send("description", () => api.images.uncheckDescription(imageId, item.engine), "확인을 취소했습니다. 설명의 내용은 그대로입니다.");
  const descriptions = data.descriptions || [];

  const name = data.placements[0]?.caption || data.title || data.filename || "이름 없는 그림";
  const field = (id, label, control, hint) => (
    <div className="form-group">
      <div className="form-tit"><label htmlFor={id}>{label}</label></div>
      <div className="form-conts">{control}</div>
      {hint && <p className="form-hint">{hint}</p>}
    </div>
  );
  const input = (key, label, { type = "text", hint, placeholder } = {}) => field(`image-${key}`, label,
    <input id={`image-${key}`} type={type} className="krds-input" value={form[key]} onChange={setText(key)} disabled={confirmed} placeholder={confirmed ? undefined : placeholder} />, hint);
  const select = (key, label, options, hint) => field(`image-${key}`, label,
    confirmed
      ? <input id={`image-${key}`} type="text" className="krds-input" value={options.find((o) => o.value === form[key])?.label || ""} disabled readOnly />
      : <KrdsSelect id={`image-${key}`} value={form[key]} options={options} onChange={set(key)} title={`${label} 선택`} />, hint);
  const check = (key, label) => (
    <div className="krds-form-check">
      <input type="checkbox" id={`image-${key}`} checked={form[key]} onChange={setCheck(key)} disabled={confirmed} />
      <label htmlFor={`image-${key}`}>{label}</label>
    </div>
  );

  return (
    <section className="image-detail" aria-labelledby="image-detail-title">
      <div className="section-head">
        <h2 className="section-title" id="image-detail-title">{name} <span className={`krds-badge ${statusTone}`}>{statusText}</span></h2>
        <button type="button" className="krds-btn small tertiary" onClick={onClose}>닫기</button>
      </div>

      <div className="image-detail-top">
        <figure className="image-view">
          {data.has_file
            ? <img src={api.images.fileUrl(data.id, upscaledView)} alt={name} />
            : <p className="empty">그림 파일 없이 메타데이터만 등록된 자료입니다.</p>}
          {data.has_upscaled && (
            <figcaption>
              <button type="button" className="krds-btn small text" onClick={() => setUpscaledView((v) => !v)}>
                {upscaledView ? "원본 보기" : "업스케일본 보기"}
              </button>
            </figcaption>
          )}
        </figure>
        <dl className="image-facts">
          <div><dt>제목</dt><dd>{data.title || "-"}</dd></div>
          <div><dt>파일</dt><dd>{data.filename || "-"}{data.format ? `, ${data.format}` : ""}{data.width_px ? `, ${data.width_px}×${data.height_px}px` : ""}</dd></div>
          {data.has_upscaled && <div><dt>업스케일본</dt><dd>{data.upscaled_width_px}×{data.upscaled_height_px}px{data.upscale_engine ? `, ${data.upscale_engine}` : ""}</dd></div>}
          <div><dt>유형</dt><dd>{terms?.kind?.[data.kind] || "-"}</dd></div>
          <div><dt>주요 키워드</dt><dd>{data.keywords.length ? data.keywords.join(", ") : "-"}</dd></div>
          {data.source_id && <div><dt>수집 번호</dt><dd className="mono">{data.source_id}</dd></div>}
          <div><dt>SHA-256</dt><dd className="mono">{data.sha256}</dd></div>
          <div><dt>증빙</dt><dd>{data.evidence.length ? data.evidence.map((e) => terms?.evidence_kind?.[e.kind] || e.kind).join(", ") : "등록된 증빙 없음"}</dd></div>
        </dl>
      </div>

      <h3 className="sub-title">수록 위치 {data.placements.length}곳</h3>
      {data.placements.length === 0 ? <p className="empty">원고에 실린 자리가 없습니다(수집 자료).</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data image-placements">
            <caption>이 그림이 실린 학습모듈과 자리</caption>
            <thead><tr><th scope="col">학습모듈</th><th scope="col">그림 번호</th><th scope="col">쪽</th><th scope="col">그림명</th><th scope="col">출처 줄</th><th scope="col">그림 사용 문장</th></tr></thead>
            <tbody>{data.placements.map((p) => (
              <tr key={p.id}>
                <td>{p.module_name ? <>{p.module_name}<br /></> : null}<span className="code">{p.module_code}</span></td>
                <td>{p.label || "-"}</td>
                <td className="num">{p.page ?? "-"}</td>
                <td>{p.caption || "-"}</td>
                <td>{p.source_line || "-"}</td>
                <td>{p.context_text || "-"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {data.links.length > 0 && (
        <p className="image-links">수행준거 연결: {data.links.map((l) => [l.unit_code, l.element_code && `요소 ${l.element_code.split(".").pop()}`, l.criterion_no && `수행준거 ${l.criterion_no}`].filter(Boolean).join(", ")).join(" / ")}</p>
      )}

      <h3 className="sub-title">권리 정보{rights ? <span className="meta"> 버전 {rights.version}{confirmed ? `, ${rights.confirmed_by} 확정(${formatDate(rights.confirmed_at)})` : ""}</span> : null}</h3>
      {confirmed && rights.reuse_scope === "unknown" && (
        <PageAlert kind="danger">확정됐지만 재사용 범위가 ‘미확인’이라 추천에 나오지 않습니다. 아래 ‘확정 취소’를 누르고 재사용 범위를 고른 뒤 다시 확정하세요.</PageAlert>
      )}
      {confirmed && <PageAlert kind="info">기관 확정된 권리 정보라 고칠 수 없습니다. 고치려면 확정을 취소한 뒤 수정하고 다시 확정하세요.</PageAlert>}
      {/* 입력 묶음은 구획 넷: 권리 → 출처 → 생성형 AI 활용 → 실행(다른 화면과 같은 구조). 구획 안에서만 3열 격자(.form-section-grid)를 쓴다 */}
      <div className="fieldset review-form is-sectioned image-rights-form">
        <div className="form-section" role="group" aria-labelledby="image-rights-title">
        <h4 className="form-section-title" id="image-rights-title">권리</h4>
        <div className="form-section-grid">
        {select("category", "분류 체계", termOptions(terms?.category, "선택 안 함"), "확정하려면 필요합니다.")}
        {select("ownership", "권리 귀속", termOptions(terms?.ownership, "선택 안 함"), "확정하려면 필요합니다.")}
        {select("reuse_scope", "재사용 범위", termOptions(terms?.reuse_scope), "‘미확인’이면 확정해도 추천 목록에 나오지 않습니다.")}
        {select("release_class", "산출물 분류", termOptions(terms?.release_class, "선택 안 함"), "‘비공개’는 추천 목록에 나오지 않습니다.")}
        {select("license", "라이선스 유형", licenseChoices)}
        <div className="form-group">
          <div className="form-tit"><span>이용조건</span></div>
          <div className="form-conts">
            <p className="derived">{form.license ? (derived ? conditionsLabel(derived) : "유형에서 정해지지 않음(메모에 적습니다)") : "-"}</p>
            {form.license.startsWith("kogl-") && form.license !== "kogl-0" && check("kogl_ai", "AI유형 함께 표시")}
          </div>
          <p className="form-hint">공공누리와 CC는 유형을 고르면 자동으로 정해집니다. AI유형이 붙어도 조건은 그대로입니다.</p>
        </div>
        {input("license_note", "라이선스 메모", { placeholder: "예: 공유마당 보호기간 만료 저작물" })}
        </div>
        </div>
        <div className="form-section" role="group" aria-labelledby="image-source-title">
        <h4 className="form-section-title" id="image-source-title">출처</h4>
        <div className="form-section-grid">
        {input("author", "저작자")}
        {input("source_org", "원 출처 기관")}
        {input("source_url", "출처 URL")}
        {input("retrieved_on", "확인 일자", { type: "date" })}
        {input("credit_line", "출처 문구")}
        </div>
        </div>
        <div className="form-section" role="group" aria-labelledby="image-ai-title">
        <h4 className="form-section-title" id="image-ai-title">생성형 AI 활용</h4>
        <div className="form-section-lead">{check("ai_used", "AI로 생성하거나 수정 보완한 그림입니다")}</div>
        {form.ai_used && <div className="form-section-grid">
          {select("ai_usage", "AI 활용 유형", usageOptions, "AI 도구 사용 표기 예 1~5. 고르면 ‘생성함/수정 보완함’이 정해집니다.")}
          {input("ai_tool", "활용 도구")}
          {input("ai_date", "활용 일자", { type: "date" })}
          {input("ai_original_source", "원본 출처", { hint: "수정 보완한 경우 원본의 출처" })}
          {input("ai_tos_scope", "약관상 이용 범위")}
          <div className="form-group">
            <div className="form-tit"><span>서약서</span></div>
            <div className="form-conts">{check("ai_pledge_submitted", "생성형 AI 결과물 집필자 서약서 제출됨")}</div>
          </div>
        </div>}
        </div>
        <div className="form-actions">
          {message && message.at !== "evidence" && <PageAlert kind={message.kind}>{message.text}</PageAlert>}
          {!confirmed && form.reuse_scope === "unknown" && (
            <PageAlert kind="danger">재사용 범위가 ‘미확인’입니다. 이대로 확정하면 추천 목록에 나오지 않습니다. 위의 ‘재사용 범위’를 먼저 선택해 주세요.</PageAlert>
          )}
          <div className="run-buttons image-actions">
            {confirmed
              ? <button type="button" className="krds-btn large secondary" onClick={unconfirm} disabled={!!busy || readOnly}>{busy === "unconfirm" ? "취소하는 중" : "확정 취소"}</button>
              : <>
                  <button type="button" className="krds-btn large secondary" onClick={save} disabled={!!busy || readOnly || !dirty}>{busy === "save" ? "저장하는 중" : "저장"}</button>
                  <button type="button" className="krds-btn large primary" onClick={confirm} disabled={!!busy || readOnly}>{busy === "confirm" ? "확정하는 중" : dirty ? "저장하고 기관 확정" : "기관 확정"}</button>
                </>}
          </div>
        </div>
      </div>

      <h3 className="sub-title">증빙 {data.evidence.length}건</h3>
      {data.evidence.length === 0 ? <p className="empty">등록된 증빙이 없습니다.</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data image-evidence-table">
            <caption>이 그림에 이어진 권리 증빙</caption>
            <thead><tr><th scope="col">종류</th><th scope="col">서류(파일 이름 또는 보관 위치)</th><th scope="col">제출일</th><th scope="col">비고</th><th scope="col">삭제</th></tr></thead>
            <tbody>{data.evidence.map((item) => (
              <tr key={item.id}>
                <td>{terms?.evidence_kind?.[item.kind] || item.kind}</td>
                <td>{item.file_ref || "-"}</td>
                <td>{item.submitted_on || "-"}</td>
                <td>{item.note || "-"}</td>
                <td className="center"><button type="button" className="krds-btn small text" disabled={!!busy || readOnly} onClick={() => removeEvidence(item)}>삭제<span className="sr-only">: {terms?.evidence_kind?.[item.kind] || item.kind}</span></button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {/* 칸이 넷이라 구획 제목 없이 3열 격자만: 종류, 서류, 제출일을 한 줄에, 비고는 다음 줄에 폭 전체 */}
      <div className="fieldset review-form is-sectioned image-evidence-form">
        <div className="form-section-grid">
        {field("evidence-kind", "증빙 종류", <KrdsSelect id="evidence-kind" value={evidence.kind} options={evidenceOptions} onChange={(value) => setEvidence((prev) => ({ ...prev, kind: value }))} title="증빙 종류 선택" />)}
        {field("evidence-file", "서류", <input id="evidence-file" type="text" className="krds-input" maxLength={200} value={evidence.fileRef} placeholder="예: 원고집필계약서_붙임3.hwp"
                                              onChange={(e) => setEvidence((prev) => ({ ...prev, fileRef: e.target.value }))} />,
               "파일 이름이나 보관 위치를 적습니다. 서류 파일 자체는 올리지 않습니다.")}
        <KrdsDateField id="evidence-date" label="제출일" value={evidence.submittedOn} onChange={(value) => setEvidence((prev) => ({ ...prev, submittedOn: value }))} disabled={!!busy} />
        <div className="form-group form-group-wide is-full">
          <div className="form-tit"><label htmlFor="evidence-note">비고</label></div>
          <div className="form-conts">
            <input id="evidence-note" type="text" className="krds-input" maxLength={500} value={evidence.note}
                   onChange={(e) => setEvidence((prev) => ({ ...prev, note: e.target.value }))} />
          </div>
        </div>
        </div>
        <div className="form-actions">
          {message && message.at === "evidence" && <PageAlert kind={message.kind}>{message.text}</PageAlert>}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn large secondary" onClick={addEvidence} disabled={!!busy || readOnly || !evidence.kind}>{busy === "evidence" ? "처리하는 중" : "증빙 등록"}</button>
          </div>
        </div>
      </div>

      <h3 className="sub-title">그림 설명 {descriptions.length}벌<span className="meta"> 그림을 본 모델이 쓴 글입니다. 그림과 견주어 읽고, 틀린 곳을 고쳐 확인해 주세요</span></h3>
      {descriptions.length === 0
        ? <p className="empty">이 그림에는 설명이 없습니다. 설명은 관리자가 그림 설명 만들기를 돌려야 생깁니다.</p>
        : descriptions.map((item, index) => (
          <DescriptionCard key={item.engine} item={item} index={index} readOnly={readOnly} busy={busy} onCheck={checkDescription} onUncheck={uncheckDescription} />
        ))}
      {message && message.at === "description" && <PageAlert kind={message.kind}>{message.text}</PageAlert>}

      <h3 className="sub-title">변경 이력</h3>
      <ul className="image-history">
        {data.history.map((entry, index) => (
          <li key={index}>
            <span className="when">{formatDate(entry.changed_at)}</span>
            <strong>{terms?.history_action?.[entry.action] || entry.action}</strong>
            <span className="who">{entry.changed_by}</span>
            {entry.version ? <span className="meta">버전 {entry.version}</span> : null}
            <span className="what">{changeText(entry, terms)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
