// 이미지 저작권 DB — 그림 1건 상세: 그림 보기, 수록 위치·수행준거, 권리 정보 입력, 기관 확정/확정 취소, 증빙 등록·삭제, 변경 이력.
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
    return Array.isArray(value) ? `${name}: ${named(value[0])} → ${named(value[1])}` : `${name} ${show(value)}`;
  });
  return parts.join(", ");
}

export function ImageDetail({ imageId, terms, by, onChanged, onClose }) {
  const [state, setState] = useState({ status: "loading" });   // { status: loading|ready|error, data, error }
  const [form, setForm] = useState(() => toForm(null));
  const [busy, setBusy] = useState(null);     // "save" | "confirm" | "unconfirm" | "evidence"
  const [evidence, setEvidence] = useState(NEW_EVIDENCE);   // 새로 등록할 증빙의 입력칸
  const [message, setMessage] = useState(null);   // { kind, text, at } — at: 알림을 보일 자리("rights" | "evidence")
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
  const needName = !by.trim();

  // 요청 하나를 보내고 결과를 반영한다. 성공하면 받은 상세를 돌려준다(이어서 확정할 때 그 버전을 쓴다)
  async function send(kind, call, done) {
    setBusy(kind);
    setMessage(null);
    const { ok, data: next, error, status } = await call();
    const at = kind === "evidence" ? "evidence" : "rights";
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

  const save = () => send("save", () => api.images.updateRights(imageId, { by, version: rights?.version, rights: toRequest(form) }), "저장했습니다.");

  async function confirm() {
    let version = rights?.version;
    if (dirty || !rights) {   // 고친 내용이 있으면 먼저 저장하고 그 버전으로 확정한다
      const saved = await save();
      if (!saved) return;
      version = saved.rights?.version;
    }
    await send("confirm", () => api.images.confirm(imageId, { by, version }), "기관 확정했습니다.");
  }

  const unconfirm = () => send("unconfirm", () => api.images.unconfirm(imageId, { by, version: rights?.version }), "확정을 취소했습니다. 이제 수정할 수 있습니다.");

  const evidenceOptions = termOptions(terms?.evidence_kind, "종류 선택");
  async function addEvidence() {
    const added = await send("evidence", () => api.images.addEvidence(imageId, { by, ...evidence }), "증빙을 등록했습니다.");
    if (added) setEvidence(NEW_EVIDENCE);
  }
  const removeEvidence = (item) => send("evidence", () => api.images.removeEvidence(imageId, item.id, { by }), "증빙을 삭제했습니다.");

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
          <div><dt>제목</dt><dd>{data.title || "—"}</dd></div>
          <div><dt>파일</dt><dd>{data.filename || "—"}{data.format ? ` · ${data.format}` : ""}{data.width_px ? ` · ${data.width_px}×${data.height_px}px` : ""}</dd></div>
          {data.has_upscaled && <div><dt>업스케일본</dt><dd>{data.upscaled_width_px}×{data.upscaled_height_px}px{data.upscale_engine ? ` · ${data.upscale_engine}` : ""}</dd></div>}
          <div><dt>유형</dt><dd>{terms?.kind?.[data.kind] || "—"}</dd></div>
          <div><dt>주요 키워드</dt><dd>{data.keywords.length ? data.keywords.join(", ") : "—"}</dd></div>
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
                <td>{p.label || "—"}</td>
                <td className="num">{p.page ?? "—"}</td>
                <td>{p.caption || "—"}</td>
                <td>{p.source_line || "—"}</td>
                <td>{p.context_text || "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {data.links.length > 0 && (
        <p className="image-links">수행준거 연결: {data.links.map((l) => [l.unit_code, l.element_code && `요소 ${l.element_code.split(".").pop()}`, l.criterion_no && `수행준거 ${l.criterion_no}`].filter(Boolean).join(" · ")).join(" / ")}</p>
      )}

      <h3 className="sub-title">권리 정보{rights ? <span className="meta"> 버전 {rights.version}{confirmed ? ` · ${rights.confirmed_by} 확정(${formatDate(rights.confirmed_at)})` : ""}</span> : null}</h3>
      {confirmed && rights.reuse_scope === "unknown" && (
        <PageAlert kind="danger">확정됐지만 재사용 범위가 ‘미확인’이라 추천에 나오지 않습니다. 아래 ‘확정 취소’를 누르고 재사용 범위를 고른 뒤 다시 확정하세요.</PageAlert>
      )}
      {confirmed && <PageAlert kind="info">기관 확정된 권리 정보라 고칠 수 없습니다. 고치려면 확정을 취소한 뒤 수정하고 다시 확정하세요.</PageAlert>}
      <div className="fieldset review-form image-rights-form">
        {select("category", "분류 체계", termOptions(terms?.category, "선택 안 함"), "확정하려면 필요합니다.")}
        {select("ownership", "권리 귀속", termOptions(terms?.ownership, "선택 안 함"), "확정하려면 필요합니다.")}
        {select("reuse_scope", "재사용 범위", termOptions(terms?.reuse_scope), "‘미확인’이면 확정해도 추천 목록에 나오지 않습니다.")}
        {select("release_class", "산출물 분류", termOptions(terms?.release_class, "선택 안 함"), "‘비공개’는 추천 목록에 나오지 않습니다.")}
        {select("license", "라이선스 유형", licenseChoices)}
        <div className="form-group">
          <div className="form-tit"><span>이용조건</span></div>
          <div className="form-conts">
            <p className="derived">{form.license ? (derived ? conditionsLabel(derived) : "유형에서 정해지지 않음(메모에 적습니다)") : "—"}</p>
            {form.license.startsWith("kogl-") && form.license !== "kogl-0" && check("kogl_ai", "AI유형 함께 표시")}
          </div>
          <p className="form-hint">공공누리·CC는 유형을 고르면 자동으로 정해집니다. AI유형이 붙어도 조건은 그대로입니다.</p>
        </div>
        {input("license_note", "라이선스 메모", { placeholder: "예: 공유마당 보호기간 만료 저작물" })}
        {input("author", "저작자")}
        {input("source_org", "원 출처 기관")}
        {input("source_url", "출처 URL")}
        {input("retrieved_on", "확인 일자", { type: "date" })}
        {input("credit_line", "출처 문구")}
        <div className="form-group form-group-wide">
          <div className="form-tit"><span>생성형 AI 활용</span></div>
          <div className="form-conts">{check("ai_used", "AI로 생성하거나 수정 보완한 그림입니다")}</div>
        </div>
        {form.ai_used && <>
          {select("ai_usage", "AI 활용 유형", usageOptions, "AI 도구 사용 표기 예 1~5. 고르면 ‘생성함/수정 보완함’이 정해집니다.")}
          {input("ai_tool", "활용 도구")}
          {input("ai_date", "활용 일자", { type: "date" })}
          {input("ai_original_source", "원본 출처", { hint: "수정 보완한 경우 원본의 출처" })}
          {input("ai_tos_scope", "약관상 이용 범위")}
          <div className="form-group">
            <div className="form-tit"><span>서약서</span></div>
            <div className="form-conts">{check("ai_pledge_submitted", "생성형 AI 결과물 집필자 서약서 제출됨")}</div>
          </div>
        </>}
        <div className="form-group form-group-wide form-actions">
          {needName && <PageAlert kind="info">저장·확정하려면 화면 위쪽의 ‘변경한 사람’에 이름을 적어 주세요. 변경 이력에 남습니다.</PageAlert>}
          {message && message.at !== "evidence" && <PageAlert kind={message.kind}>{message.text}</PageAlert>}
          {!confirmed && form.reuse_scope === "unknown" && (
            <PageAlert kind="danger">재사용 범위가 ‘미확인’입니다. 이대로 확정하면 추천에 나오지 않습니다 — 위의 ‘재사용 범위’를 먼저 골라 주세요.</PageAlert>
          )}
          <div className="run-buttons image-actions">
            {confirmed
              ? <button type="button" className="krds-btn large secondary" onClick={unconfirm} disabled={!!busy || needName}>{busy === "unconfirm" ? "취소하는 중" : "확정 취소"}</button>
              : <>
                  <button type="button" className="krds-btn large secondary" onClick={save} disabled={!!busy || needName || !dirty}>{busy === "save" ? "저장하는 중" : "저장"}</button>
                  <button type="button" className="krds-btn large primary" onClick={confirm} disabled={!!busy || needName}>{busy === "confirm" ? "확정하는 중" : dirty ? "저장하고 기관 확정" : "기관 확정"}</button>
                </>}
          </div>
        </div>
      </div>

      <h3 className="sub-title">증빙 {data.evidence.length}건</h3>
      {data.evidence.length === 0 ? <p className="empty">등록된 증빙이 없습니다.</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data image-evidence-table">
            <caption>이 그림에 이어진 권리 증빙</caption>
            <thead><tr><th scope="col">종류</th><th scope="col">서류(파일 이름·보관 위치)</th><th scope="col">제출일</th><th scope="col">비고</th><th scope="col">삭제</th></tr></thead>
            <tbody>{data.evidence.map((item) => (
              <tr key={item.id}>
                <td>{terms?.evidence_kind?.[item.kind] || item.kind}</td>
                <td>{item.file_ref || "—"}</td>
                <td>{item.submitted_on || "—"}</td>
                <td>{item.note || "—"}</td>
                <td className="center"><button type="button" className="krds-btn small text" disabled={!!busy || needName} onClick={() => removeEvidence(item)}>삭제<span className="sr-only"> — {terms?.evidence_kind?.[item.kind] || item.kind}</span></button></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <div className="fieldset review-form image-evidence-form">
        {field("evidence-kind", "증빙 종류", <KrdsSelect id="evidence-kind" value={evidence.kind} options={evidenceOptions} onChange={(value) => setEvidence((prev) => ({ ...prev, kind: value }))} title="증빙 종류 선택" />)}
        {field("evidence-file", "서류", <input id="evidence-file" type="text" className="krds-input" maxLength={200} value={evidence.fileRef} placeholder="예: 원고집필계약서_붙임3.hwp"
                                              onChange={(e) => setEvidence((prev) => ({ ...prev, fileRef: e.target.value }))} />,
               "파일 이름이나 보관 위치를 적습니다. 서류 파일 자체는 올리지 않습니다.")}
        <KrdsDateField id="evidence-date" label="제출일" value={evidence.submittedOn} onChange={(value) => setEvidence((prev) => ({ ...prev, submittedOn: value }))} disabled={!!busy} />
        {field("evidence-note", "비고", <input id="evidence-note" type="text" className="krds-input" maxLength={500} value={evidence.note}
                                              onChange={(e) => setEvidence((prev) => ({ ...prev, note: e.target.value }))} />)}
        <div className="form-group form-group-wide form-actions">
          {message && message.at === "evidence" && <PageAlert kind={message.kind}>{message.text}</PageAlert>}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn large secondary" onClick={addEvidence} disabled={!!busy || needName || !evidence.kind}>{busy === "evidence" ? "처리하는 중" : "증빙 등록"}</button>
          </div>
        </div>
      </div>

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
