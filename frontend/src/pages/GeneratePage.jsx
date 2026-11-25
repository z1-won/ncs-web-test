// 이미지 AI 생성(REQ-02-006 ① AI 생성) — 집필한 문단을 바탕으로 도표, 표, 그래프를 만든다.
// 생성형 AI(글)는 그림이 아니라 '명세'(칸과 글)를 쓰고, 그림은 서버의 코드가 그린다. 그래서 글자가 깨지지 않고 같은 명세는 같은 그림이 된다.
// 유의 안내(AI를 쓰기 전에 확인할 것)를 확인하고 [확인하고 시작하기]를 눌러야 문단 입력부터의 화면이 열린다 — 확인 전에는 안내만 보인다.
// 흐름: 유의 안내 확인 → 문단 입력 → 후보(검사 통과/탈락과 까닭) → 하나를 골라 칸을 고침 → 그림(PNG)과 표기 줄 받기.
// 화면 위의 단계 표시가 지금 어디인지 보이고, 지나온 단계(유의 안내, 문단, 후보)는 단계 표시 아래의 요약 묶음 한 곳에 한 줄씩 접힌다(단추로 다시 편다).
// 후보는 작은 그림의 카드로 나란히 놓아 견주고, 가로로 긴 그림(순서 도표 등)은 카드를 한 줄 전체로 편다.
// 수정과 내려받기는 두 열이다: 왼쪽에 문단과 입력 칸, 오른쪽에 그림과 그 아래의 표기, 받기, 이미지 저작권 DB. 주 단추는 구역(열)의 오른쪽 끝에 둔다.
// 검사는 둘이다. 근거(명세의 글이 문단에 있는 말인가): AI 후보는 지적이 있으면 쓰지 않는다. 사람이 고친 명세에는 알림만 보인다.
//                빠진 내용(문단의 금지·주의, 한 줄에서 빠진 말): 알림만 보인다. 칸의 자리가 맞는지는 규칙이 보지 못하므로 사람이 문단과 견주어 본다.
// 그래프의 값은 문단에 적힌 수여야 하고, 그 수가 같은 문장에서 그 범주 이름 뒤에 적혀 있어야 한다(뒤바뀐 값을 잡는다).
// 사진, 삽화는 서버에 올린 공개 이미지 모델이 만든다(components/PictureMaker.jsx) — 문단 입력까지는 이 페이지가, 장면 후보부터는 PictureMaker가 맡는다.
// 문단은 이미지 추천에서 넘겨받을 수 있다(라우터 state — 주소에 문단을 싣지 않는다).
// 올린 글과 만든 그림은 서버에 남기지 않는다 — 에디터·직능연이 [이미지 저작권 DB에 올리기]를 누른 그림만 남는다.
// 생성형 AI의 응답은 서버의 캐시에 보관 기한 동안 남는다(개인정보처리방침).
import React, { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { api, saveBlob } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { Spinner } from "../components/Badge.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import PictureMaker from "../components/PictureMaker.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { copyText } from "../lib/clipboard.js";
import { useAuth, useCanManage } from "../lib/auth.jsx";

const ANCHORS = [{ id: "generate-input", label: "문단" }, { id: "generate-candidates", label: "후보" }, { id: "generate-edit", label: "수정과 내려받기" }];
// 유형은 요구사항정의서 REQ-02-009의 태그(사진 / 삽화 / 도표 / 그래프)와 같은 말을 쓴다. 표는 도표와 따로 고른다
const TYPES = [
  { value: "diagram", label: "도표", hint: "순서, 순환, 구성, 비교 가운데 하나로 그립니다. 종류를 선택하지 않으면 문단에 맞는 종류를 생성형 AI가 선택합니다." },
  { value: "table", label: "표", hint: "여러 대상을 같은 기준으로 정리합니다. 한글 프로그램에 붙여 넣을 수 있는 표로도 받을 수 있습니다." },
  { value: "graph", label: "그래프", hint: "같은 기준의 수치가 두 개 이상 있는 문단을 막대, 꺾은선, 원 그래프로 그립니다." },
  { value: "photo", label: "사진", picture: true, hint: "장비, 작업 모습, 현장을 사진처럼 만듭니다. 서버의 이미지 모델이 만들며, 얼굴이 드러난 사람과 글자는 넣지 않습니다." },
  { value: "illustration", label: "삽화", picture: true, hint: "단순한 그림으로 만듭니다. 서버의 이미지 모델이 만들며, 얼굴이 드러난 사람과 글자는 넣지 않습니다." },
];
const KIND_LABEL = { sequence: "순서", cycle: "순환", structure: "구성", compare: "비교", table: "표", bar: "막대 그래프", line: "꺾은선 그래프", pie: "원 그래프" };
const FAMILY = { diagram: ["sequence", "cycle", "structure", "compare"], graph: ["bar", "line", "pie"] };
const GRAPH_KINDS = FAMILY.graph;
const isGraph = (kind) => GRAPH_KINDS.includes(kind);
const LONG = 3.5;      // 그림의 가로/세로 비가 이보다 크면(가로 한 줄 순서 도표 등) 작은 카드에서 글자를 읽을 수 없다 — 카드를 한 줄 전체로 편다
const METHOD_LABEL = { "같은 파일": "같은 파일", "지각 해시": "크기나 형식만 바뀐 그림", "임베딩": "내용이 비슷한 그림" };      // 서버가 알려 주는 찾은 방법을 화면의 말로
const ASSET_LABEL = { photo: "사진", illustration: "삽화", table: "도표", graph: "그래프", screenshot: "화면 캡처", other: "기타" };
const BLANK = {
  sequence: { kind: "sequence", title: "", items: [{ label: "", note: "" }, { label: "", note: "" }, { label: "", note: "" }] },
  cycle: { kind: "cycle", title: "", items: [{ label: "", note: "" }, { label: "", note: "" }, { label: "", note: "" }] },
  structure: { kind: "structure", title: "", root: "", items: [{ label: "", children: [] }, { label: "", children: [] }] },
  compare: { kind: "compare", title: "", items: [{ label: "", children: [""] }, { label: "", children: [""] }] },
  table: { kind: "table", title: "", header: ["구분", "내용"], rows: [["", ""], ["", ""]] },
  bar: { kind: "bar", title: "", unit: "", categories: ["", "", ""], series: [{ name: "", values: ["", "", ""] }] },
  line: { kind: "line", title: "", unit: "", categories: ["", "", ""], series: [{ name: "", values: ["", "", ""] }] },
  pie: { kind: "pie", title: "", unit: "%", categories: ["", "", ""], series: [{ name: "", values: ["", "", ""] }] },
};
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const clone = (value) => JSON.parse(JSON.stringify(value));

// 명세 하나를 그려 보여 준다. 명세나 폭이 바뀌면 다시 그린다. onDrawn(blob, summary): 내려받기에 쓸 수 있게 올려 준다
function Preview({ spec, width, alt, onDrawn, compact }) {
  const [state, setState] = useState({ status: "loading" });
  const key = JSON.stringify(spec) + width;
  useEffect(() => {
    const controller = new AbortController();
    let url = null;
    setState({ status: "loading" });
    api.generate.render(spec, width, controller.signal).then((result) => {
      if (result.aborted) return;
      if (!result.ok) { setState({ status: "error", error: result.error }); onDrawn?.(null, null); return; }
      url = URL.createObjectURL(result.blob);
      setState({ status: "ready", url, summary: result.summary });
      onDrawn?.(result.blob, result.summary);
    });
    return () => { controller.abort(); if (url) URL.revokeObjectURL(url); };
  }, [key]);                                                    // eslint-disable-line react-hooks/exhaustive-deps
  if (state.status === "loading") return <div className="gen-preview is-loading"><Spinner label="그리는 중" /></div>;
  if (state.status === "error") return <PageAlert kind="danger">{state.error}</PageAlert>;
  if (compact !== undefined) {
    return <figure className={`gen-preview is-thumb${compact ? "" : " is-open"}`}><img src={state.url} alt={alt} /></figure>;
  }
  return (
    <figure className="gen-preview">
      <img src={state.url} alt={alt} />
      <figcaption className="meta">{state.summary.width}×{state.summary.height}px, 가로 {state.summary.width_mm}mm 기준 {state.summary.dpi} DPI, 글꼴 {state.summary.font}</figcaption>
    </figure>
  );
}

// 근거 검사의 지적을 갈래로 묶는다 — 칸마다 한 줄씩 쌓지 않고 '문단에 없는 말 3개: 온라인, 전화, 방문'처럼 한 줄로
const PROBLEM_GROUPS = [
  ["상표", "상표·상품명"], ["글에 없는 수", "문단에 없는 수"], ["글에 없는 영문", "문단에 없는 영문"], ["글에 없는 말", "문단에 없는 표현"],
  ["글에서 '", "범주와 함께 적혀 있지 않은 값"],
];
function groupProblems(problems) {
  const groups = new Map();
  for (const problem of problems || []) {
    const [prefix, label] = PROBLEM_GROUPS.find(([start]) => problem.reason.startsWith(start)) || ["", "문단에 없는 표현"];
    const quoted = [...problem.reason.matchAll(/'([^']+)'/g)].map((match) => match[1]);
    const shown = prefix === "글에서 '" ? [`${quoted[0]} ${quoted[1]}`] : prefix === "글에 없는 말" ? quoted : [quoted[0] || problem.text];
    if (!groups.has(label)) groups.set(label, new Set());
    shown.forEach((value) => groups.get(label).add(value));
  }
  return [...groups].map(([label, values]) => ({ label, values: [...values] }));
}

// 알림 상자는 PageAlert와 같은 모양(.page-alert)을 쓴다. 후보마다 여러 개가 함께 뜨므로 role은 두지 않는다(목록이 aria-live 영역 안에 있다)
function Notes({ problems, omissions }) {
  if (!problems?.length && !omissions?.length) return null;
  return (
    <div className="gen-notes">
      {problems?.length > 0 && (
        <div className="page-alert danger">
          <i className="svg-icon" aria-hidden="true"></i>
          <div className="page-alert-body">
            {groupProblems(problems).map((group) => <p key={group.label}><strong>{group.label} {group.values.length}개</strong> {group.values.join(", ")}</p>)}
          </div>
        </div>
      )}
      {omissions?.length > 0 && (
        <div className="page-alert warning">
          <i className="svg-icon" aria-hidden="true"></i>
          <div className="page-alert-body">
            <p><strong>누락 의심 {omissions.length}건</strong></p>
            <ul>{omissions.map((missing, i) => <li key={i}>{missing.reason}<span className="meta"> 문단: {missing.sentence}</span></li>)}</ul>
          </div>
        </div>
      )}
    </div>
  );
}

// 칸을 고치는 입력. 종류마다 칸의 모양이 다르다. 줄 바꿈으로 여러 줄을 적는 칸(children)은 한 줄이 한 항목이다
// flags: 근거 검사가 지적한 칸({ 칸 이름: 까닭 }) — 그 입력 칸에 테두리와 까닭을 붙인다. 칸을 고치는 동안에는 비어 있다(자리가 달라질 수 있어서)
function SpecEditor({ spec, onChange, disabled, flags = {} }) {
  const set = (patch) => onChange({ ...spec, ...patch });
  const mark = (name) => (flags[name] ? { "aria-invalid": true, title: flags[name] } : {});
  const bad = (name) => (flags[name] ? "is-error" : undefined);
  const under = (prefix) => Object.keys(flags).find((name) => name.startsWith(prefix));
  const setItem = (index, patch) => set({ items: spec.items.map((item, i) => (i === index ? { ...item, ...patch } : item)) });
  const field = (id, label, value, change, { name, ...props } = {}) => (
    <div className={`gen-field${flags[name] ? " is-error" : ""}`}>
      <label htmlFor={id}>{label}</label>
      <input id={id} type="text" className="krds-input" value={value} disabled={disabled} onChange={(e) => change(e.target.value)} {...props} {...mark(name)}
             aria-describedby={flags[name] ? `${id}-flag` : undefined} />
      {flags[name] && <p className="form-hint-invalid" id={`${id}-flag`}>{flags[name]}</p>}
    </div>
  );
  if (spec.kind === "table") {
    const setCell = (r, c, value) => set({ rows: spec.rows.map((row, i) => (i === r ? row.map((cell, j) => (j === c ? value : cell)) : row)) });
    return (
      <div className="gen-editor">
        {field("gen-title", "제목(그림에는 넣지 않고 그림 제목 줄에 사용합니다)", spec.title, (title) => set({ title }), { maxLength: 40, name: "title" })}
        <div className="krds-table-wrap">
          <table className="tbl col data gen-table">
            <caption>표의 열 이름과 칸</caption>
            <thead><tr>{spec.header.map((cell, c) => (
              <th key={c} scope="col" className={bad(`header[${c}]`)}><input type="text" className="krds-input" aria-label={`${c + 1}열 이름`} maxLength={24} value={cell} disabled={disabled}
                                 onChange={(e) => set({ header: spec.header.map((old, j) => (j === c ? e.target.value : old)) })} {...mark(`header[${c}]`)} /></th>))}</tr></thead>
            <tbody>{spec.rows.map((row, r) => (
              <tr key={r}>{row.map((cell, c) => (
                <td key={c} className={bad(`rows[${r}][${c}]`)}><input type="text" className="krds-input" aria-label={`${r + 1}행 ${spec.header[c] || `${c + 1}열`}`} maxLength={60} value={cell} disabled={disabled}
                                   onChange={(e) => setCell(r, c, e.target.value)} {...mark(`rows[${r}][${c}]`)} /></td>))}</tr>))}</tbody>
          </table>
        </div>
        <div className="gen-editor-actions">
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.rows.length >= 10} onClick={() => set({ rows: [...spec.rows, spec.header.map(() => "")] })}>행 추가</button>
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.rows.length <= 1} onClick={() => set({ rows: spec.rows.slice(0, -1) })}>마지막 행 삭제</button>
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.header.length >= 6}
                  onClick={() => set({ header: [...spec.header, ""], rows: spec.rows.map((row) => [...row, ""]) })}>열 추가</button>
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.header.length <= 2}
                  onClick={() => set({ header: spec.header.slice(0, -1), rows: spec.rows.map((row) => row.slice(0, -1)) })}>마지막 열 삭제</button>
        </div>
      </div>
    );
  }
  if (isGraph(spec.kind)) {
    const pie = spec.kind === "pie";
    const maxRows = pie ? 8 : 12;
    const setCategory = (r, value) => set({ categories: spec.categories.map((old, i) => (i === r ? value : old)) });
    const setSeries = (c, patch) => set({ series: spec.series.map((old, i) => (i === c ? { ...old, ...patch } : old)) });
    const setValue = (c, r, value) => setSeries(c, { values: spec.series[c].values.map((old, i) => (i === r ? value : old)) });
    return (
      <div className="gen-editor">
        {field("gen-title", "제목(그림에는 넣지 않고 그림 제목 줄에 사용합니다)", spec.title, (title) => set({ title }), { maxLength: 40, name: "title" })}
        {field("gen-unit", "단위(선택, 예: 건, %, 명)", spec.unit || "", (unit) => set({ unit }), { maxLength: 12, name: "unit" })}
        <div className="krds-table-wrap">
          <table className="tbl col data gen-table">
            <caption>그래프의 범주와 값</caption>
            <thead><tr>
              <th scope="col">범주</th>
              {spec.series.map((one, c) => (
                <th key={c} scope="col" className={bad(`series[${c}].name`)}><input type="text" className="krds-input" aria-label={`${c + 1}번 계열 이름`} maxLength={24} value={one.name} disabled={disabled}
                                               placeholder={spec.series.length > 1 ? "계열 이름" : "값(계열 이름은 선택)"} onChange={(e) => setSeries(c, { name: e.target.value })} {...mark(`series[${c}].name`)} /></th>))}
            </tr></thead>
            <tbody>{spec.categories.map((category, r) => (
              <tr key={r}>
                <td className={bad(`categories[${r}]`)}><input type="text" className="krds-input" aria-label={`${r + 1}번 범주`} maxLength={24} value={category} disabled={disabled} onChange={(e) => setCategory(r, e.target.value)} {...mark(`categories[${r}]`)} /></td>
                {spec.series.map((one, c) => (
                  <td key={c} className={bad(`series[${c}].values[${r}]`)}><input type="text" inputMode="decimal" className="krds-input" aria-label={`${category || `${r + 1}번 범주`}의 ${one.name || "값"}`} value={one.values[r] ?? ""} disabled={disabled}
                                     onChange={(e) => setValue(c, r, e.target.value)} {...mark(`series[${c}].values[${r}]`)} /></td>))}
              </tr>))}</tbody>
          </table>
        </div>
        <p className="form-hint">값은 문단에 있는 수를 그대로 입력해 주세요(0 이상). 합계나 평균처럼 계산한 값은 문단에 있을 때만 입력할 수 있습니다.</p>
        <div className="gen-editor-actions">
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.categories.length >= maxRows}
                  onClick={() => set({ categories: [...spec.categories, ""], series: spec.series.map((one) => ({ ...one, values: [...one.values, ""] })) })}>범주 추가</button>
          <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.categories.length <= 2}
                  onClick={() => set({ categories: spec.categories.slice(0, -1), series: spec.series.map((one) => ({ ...one, values: one.values.slice(0, -1) })) })}>마지막 범주 삭제</button>
          {!pie && (<>
            <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.series.length >= 4}
                    onClick={() => set({ series: [...spec.series, { name: "", values: spec.categories.map(() => "") }] })}>계열 추가</button>
            <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.series.length <= 1} onClick={() => set({ series: spec.series.slice(0, -1) })}>마지막 계열 삭제</button>
          </>)}
        </div>
      </div>
    );
  }
  const withChildren = spec.kind === "structure" || spec.kind === "compare";
  const limits = { sequence: [2, 8], cycle: [3, 6], structure: [2, 6], compare: [2, 4] }[spec.kind];
  return (
    <div className="gen-editor">
      {field("gen-title", "제목(그림에는 넣지 않고 그림 제목 줄에 사용합니다)", spec.title, (title) => set({ title }), { maxLength: 40, name: "title" })}
      {spec.kind === "structure" && field("gen-root", "최상위 항목", spec.root, (root) => set({ root }), { maxLength: 24, name: "root" })}
      <ol className="gen-items">
        {spec.items.map((item, i) => (
          <li key={i}>
            {field(`gen-label-${i}`, `항목 ${i + 1}`, item.label, (label) => setItem(i, { label }), { maxLength: 24, name: `items[${i}].label` })}
            {withChildren ? (
              <div className={`gen-field${under(`items[${i}].children`) ? " is-error" : ""}`}>
                <label htmlFor={`gen-children-${i}`}>하위 내용(한 줄에 하나씩, 6줄까지)</label>
                <textarea id={`gen-children-${i}`} className="krds-input" rows={3} disabled={disabled} value={(item.children || []).join("\n")}
                          onChange={(e) => setItem(i, { children: e.target.value.split("\n") })} {...mark(under(`items[${i}].children`))} />
                {under(`items[${i}].children`) && <p className="form-hint-invalid">{Object.entries(flags).filter(([name]) => name.startsWith(`items[${i}].children`)).map(([, why]) => why).join(" / ")}</p>}
              </div>
            ) : field(`gen-note-${i}`, "설명(선택)", item.note || "", (note) => setItem(i, { note }), { maxLength: 40, name: `items[${i}].note` })}
          </li>
        ))}
      </ol>
      <div className="gen-editor-actions">
        <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.items.length >= limits[1]}
                onClick={() => set({ items: [...spec.items, withChildren ? { label: "", children: [] } : { label: "", note: "" }] })}>항목 추가</button>
        <button type="button" className="krds-btn small tertiary" disabled={disabled || spec.items.length <= limits[0]} onClick={() => set({ items: spec.items.slice(0, -1) })}>마지막 항목 삭제</button>
      </div>
    </div>
  );
}

// 입력 칸의 값을 서버에 보낼 명세로: 빈 설명과 빈 줄을 뺀다. 그래프의 값은 수로 바꾼다(수가 아닌 글은 그대로 보내 서버가 까닭을 알려 준다)
function tidy(spec) {
  if (spec.kind === "table") return spec;
  if (isGraph(spec.kind)) {
    const number = (value) => {
      const text = String(value ?? "").replace(/,/g, "").trim();
      return text !== "" && Number.isFinite(Number(text)) ? Number(text) : String(value ?? "");
    };
    return { ...spec, unit: (spec.unit || "").trim(), series: spec.series.map((one) => ({ name: one.name.trim(), values: one.values.map(number) })) };
  }
  return { ...spec, items: spec.items.map((item) => {
    const out = { label: item.label };
    if (item.note?.trim()) out.note = item.note;
    const children = (item.children || []).map((line) => line.trim()).filter(Boolean);
    if (children.length) out.children = children;
    return out;
  }) };
}

export default function GeneratePage() {
  usePageTitle("이미지 AI 생성");
  const handed = useLocation().state || {};                    // 이미지 추천이 넘긴 { text, criterion }
  const { status: authStatus } = useAuth();
  const canManage = useCanManage();
  const [notice, setNotice] = useState(null);
  const [agreed, setAgreed] = useState(false);
  const [status, setStatus] = useState(null);                 // 서버 상태 { 사용 가능, 이유, 도구, 글꼴, … } | "error"
  const [form, setForm] = useState({ type: "diagram", kind: "", text: String(handed.text || "").slice(0, 4000), criterion: String(handed.criterion || "").slice(0, 400), focus: "", width: 150 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);                 // 후보 응답 { method, note, candidates, … }
  const [asked, setAsked] = useState(null);                   // 후보를 만든 입력(문단, 수행준거) — 검사는 이 글로 한다
  const [draft, setDraft] = useState(null);                   // 고치는 중인 명세(입력 칸의 값)
  const [origin, setOrigin] = useState(null);                 // "ai"(생성형 AI 후보에서) | "manual"(직접 적음)
  const [shown, setShown] = useState(null);                   // 마지막으로 그린 명세 { spec, problems, omissions }
  const [drawing, setDrawing] = useState(false);
  const [drawError, setDrawError] = useState(null);
  const [mark, setMark] = useState({ tool: "", date: today(), number: "" });
  const [marking, setMarking] = useState(null);               // { lines, note } | { error }
  const [done, setDone] = useState(null);
  const [view, setView] = useState({ notice: true, input: true, candidates: true });      // 단계를 펴 두었는가(지나온 단계는 접는다)
  const [wide, setWide] = useState(null);                     // 넓게 편 후보의 순번
  const [aspects, setAspects] = useState({});                 // 후보 그림의 가로/세로 비 — 가로로 긴 그림은 카드를 한 줄 전체로 편다
  const [picked, setPicked] = useState(null);                 // 고른 후보의 순번(생성형 AI 후보에서 골랐을 때)
  const [more, setMore] = useState(!!handed.criterion);       // 문단 입력의 선택 항목(수행준거, 그림으로 나타낼 부분, 가로 크기)을 펴 두었는가
  const [picture, setPicture] = useState(null);               // 사진·삽화 요청 { key, kind, text, criterion, focus, width, manual } — PictureMaker에 넘긴다
  const [pictureStage, setPictureStage] = useState(3);        // PictureMaker가 알려 주는 단계(3 후보, 4 고치기, 5 받기)
  const [similar, setSimilar] = useState(null);               // 닮은 그림 대조 { 닮은 그림, … } | { error } | "loading"
  const [store, setStore] = useState({ module: "", by: "", busy: false, result: null, error: null });      // 이미지 저작권 DB에 올리기
  const drawn = useRef(null);                                 // { blob, summary } — 마지막으로 그린 그림
  const editRef = useRef(null);
  const set = (key) => (value) => setForm((old) => ({ ...old, [key]: value }));

  useEffect(() => {
    api.aiImage.notice().then(({ ok, data }) => { if (ok) setNotice(data); });
    api.generate.status().then(({ ok, data }) => {
      setStatus(ok ? data : "error");
      if (ok && data.도구) setMark((old) => ({ ...old, tool: old.tool || data.도구 }));
    });
  }, []);

  const type = TYPES.find((entry) => entry.value === form.type);
  const kind = form.type === "table" ? "table" : (form.kind || form.type);      // 종류를 고르지 않았으면 유형(diagram, graph)을 보낸다
  const blankKind = BLANK[kind] ? kind : FAMILY[form.type]?.[0] || "sequence";
  const ready = status && status !== "error";
  const canAsk = ready && !type.off && !busy && (type.picture ? (form.text.trim().length > 0 || form.focus.trim().length > 0) : form.text.trim().length > 0);

  function startPicture(manual) {
    setResult(null); setDraft(null); setShown(null); setError(null); setPictureStage(3);
    setPicture({ key: Date.now(), kind: form.type, text: form.text, criterion: form.criterion, focus: form.focus, width: form.width, manual });
    setView((old) => ({ ...old, input: false }));
  }

  async function ask(event) {
    event.preventDefault();
    if (type.picture) { startPicture(false); return; }
    setPicture(null);
    setBusy(true); setError(null); setResult(null); setDone(null);
    const body = { text: form.text, criterion: form.criterion, kind, focus: form.focus };
    const { ok, data, error: message } = await api.generate.spec(body);
    setBusy(false);
    if (!ok) { setError(message); return; }
    setAsked({ text: form.text, criterion: form.criterion });
    setResult(data); setWide(null); setPicked(null); setAspects({});
    setDraft(null); setShown(null);
    setView((old) => ({ ...old, input: false, candidates: true }));
    setTimeout(() => document.getElementById("generate-candidates")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  function open(spec, from, index = null) {
    setPicture(null);
    if (!asked || from === "manual") setAsked({ text: form.text, criterion: form.criterion });
    setPicked(index);
    setView((old) => ({ ...old, input: false, candidates: false }));
    const filled = spec.kind === "table" || isGraph(spec.kind) ? clone(spec) : { ...clone(spec), items: spec.items.map((item) => ({ note: "", children: [], ...clone(item) })) };
    setDraft(filled); setOrigin(from); setShown(null); setDrawError(null); setMarking(null); setDone(null); setSimilar(null);
    setStore((old) => ({ ...old, result: null, error: null }));
    drawn.current = null;
    if (from === "ai") draw(filled);
    setTimeout(() => editRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  }

  // 고친 명세를 검사하고(모양이 틀리면 까닭을 보인다) 다시 그린다
  async function draw(spec = draft) {
    setDrawing(true); setDrawError(null); setDone(null);
    const source = asked || { text: form.text, criterion: form.criterion };
    const { ok, data, error: message } = await api.generate.check(tidy(spec), source.text, source.criterion);
    setDrawing(false);
    if (!ok) { setDrawError(message); return; }
    setShown({ spec: data.spec, problems: data.problems, omissions: data.omissions });
    setSimilar(null); setStore((old) => ({ ...old, result: null, error: null }));
  }

  async function findSimilar() {
    setSimilar("loading");
    const { ok, data, error: message } = await api.generate.similar({ spec: shown.spec, width_mm: form.width });
    setSimilar(ok ? data : { error: message });
  }

  async function register() {
    setStore((old) => ({ ...old, busy: true, result: null, error: null }));
    const ai = origin === "ai";
    const { ok, data, error: message } = await api.generate.register({
      spec: shown.spec, width_mm: form.width, ai, tool: ai ? mark.tool : "", date: mark.date, module_code: store.module.trim(),
      number: store.module.trim() ? mark.number : "", by: store.by });
    setStore((old) => ({ ...old, busy: false, result: ok ? data : null, error: ok ? null : message }));
  }

  useEffect(() => {
    if (!shown || origin !== "ai" || !mark.tool.trim()) { setMarking(null); return undefined; }
    let alive = true;
    api.generate.marking({ title: shown.spec.title, tool: mark.tool, date: mark.date, kind: shown.spec.kind, number: mark.number }).then(({ ok, data, error: message }) => {
      if (alive) setMarking(ok ? data : { error: message });
    });
    return () => { alive = false; };
  }, [shown, origin, mark.tool, mark.date, mark.number]);

  const fileName = (shown?.spec.title || "도표").replace(/[\\/:*?"<>|]+/g, "_");
  function savePng() {
    if (!drawn.current?.blob) return;
    saveBlob(drawn.current.blob, `${fileName}.png`);
    setDone("그림을 내려받았습니다. 원고에 넣을 때 가로 크기를 위에 표시된 값(mm)으로 맞추면 300 DPI가 됩니다.");
  }
  async function copyTable() {
    const html = await api.generate.tableText(shown.spec, "html");
    const tsv = await api.generate.tableText(shown.spec, "tsv");
    if (!html.ok || !tsv.ok) { setDone(null); setDrawError(html.error || tsv.error); return; }
    try {
      await navigator.clipboard.write([new ClipboardItem({ "text/html": new Blob([html.text], { type: "text/html" }), "text/plain": new Blob([tsv.text], { type: "text/plain" }) })]);
      setDone("표를 복사했습니다. 한글 프로그램에 붙여 넣으면 표가 됩니다.");
    } catch {
      setDone((await copyText(tsv.text)) ? "표를 탭으로 구분한 텍스트로 복사했습니다." : "복사하지 못했습니다. 브라우저의 복사 권한을 확인해 주세요.");
    }
  }

  const candidates = result?.candidates || [];
  const dirty = draft && shown && JSON.stringify(tidy(draft)) !== JSON.stringify(shown.spec);
  const flags = shown && !dirty ? Object.fromEntries(shown.problems.map((problem) => [problem.field, problem.reason])) : {};
  const entered = agreed && !view.notice;                     // 유의 안내를 확인하고 들어왔는가 — 아니면 안내만 보인다
  const step = !entered ? 1 : picture ? pictureStage : shown ? 5 : draft ? 4 : result ? 3 : 2;
  const STEPS = ["확인", "문단", "후보", "수정", "내려받기"];
  return (
    <>
    <Header anchors={entered && (result || draft || picture) ? ANCHORS.filter((anchor) => picture ? true : anchor.id === "generate-input" ? view.input : anchor.id === "generate-candidates" ? result && view.candidates : draft) : []} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page image-db-page generate-page">
      <h1 className="page-title">이미지 AI 생성</h1>
      <p className="page-desc">
        집필한 문단으로 <strong>도표, 표, 그래프</strong>와 <strong>사진, 삽화</strong>를 만듭니다. 도표, 표, 그래프는 생성형 AI가 구성(항목과 글)만 작성하고 그림은 서버가 그립니다.
        그래서 글자가 깨지지 않고, 문단에 없는 내용이 들어간 후보는 제외됩니다. 사진과 삽화는 서버의 이미지 모델이 만듭니다. 그림은 외부로 전송하지 않습니다.
      </p>
      <p className="page-desc">
        사용할 수 있는 기존 그림은 <Link to="/recommend">이미지 추천</Link>에서 먼저 찾아볼 수 있습니다.
        다른 도구로 만든 그림의 표기와 결과물 현황은 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.
      </p>

      <ol className="krds-step-wrap gen-steps" aria-label="진행 단계">
        {STEPS.map((label, i) => (
          <li key={label} className={i + 1 === step ? "active" : i + 1 < step ? "done" : undefined} aria-current={i + 1 === step ? "step" : undefined}>
            <span><span className="step">{i + 1}단계{i + 1 < step && <span className="sr-only"> 마침</span>}</span><span className="step-tit">{label}</span></span>
          </li>
        ))}
      </ol>
      <p className="gen-step-now" aria-hidden="true">{step}/{STEPS.length}단계 <strong>{STEPS[step - 1]}</strong></p>

      {entered ? (
        <ul className="gen-trail" aria-label="완료한 단계">
          <li>
            <span><strong>확인</strong> ‘AI 사용 전 확인 사항’을 확인했습니다.</span>
            <button type="button" className="krds-btn small tertiary" onClick={() => setView((old) => ({ ...old, notice: true }))}>다시 보기</button>
          </li>
          {ready && !view.input && (
            <li>
              <span><strong>문단</strong> {type.label}{FAMILY[form.type] && form.kind ? `(${KIND_LABEL[form.kind]})` : ""}, {form.text.trim() ? `${form.text.trim().length}자: ${form.text.trim().slice(0, 60)}${form.text.trim().length > 60 ? "…" : ""}` : "문단 없이 직접 입력 중"}</span>
              <button type="button" className="krds-btn small tertiary" onClick={() => setView((old) => ({ ...old, input: true }))}>문단 수정</button>
            </li>
          )}
          {result && !view.candidates && (
            <li>
              <span><strong>후보</strong> {candidates.length}개 가운데 {result.usable}개 통과, {picked !== null ? `후보 ${picked + 1}을 선택했습니다.` : "후보를 선택하지 않고 직접 입력 중입니다."}</span>
              <button type="button" className="krds-btn small tertiary" onClick={() => setView((old) => ({ ...old, candidates: true }))}>후보 다시 보기</button>
            </li>
          )}
        </ul>
      ) : (
      <section className="ai-notice" aria-labelledby="gen-notice-title">
        <h2 className="section-title" id="gen-notice-title">AI 사용 전 확인 사항</h2>
        {notice ? (<>
          <ol className="ai-notice-list">{notice.항목.map((item) => <li key={item.제목}><strong>{item.제목}</strong><span>{item.내용}</span></li>)}</ol>
          <p className="meta">근거: {notice.근거}</p>
        </>) : <p className="meta">안내를 불러오는 중입니다.</p>}
        <div className="krds-form-check">
          <input type="checkbox" id="gen-agreed" checked={agreed} disabled={!notice} onChange={(e) => setAgreed(e.target.checked)} />
          <label htmlFor="gen-agreed">위 내용을 확인했습니다</label>
        </div>
        <div className="gen-enter">
          <button type="button" className="krds-btn large primary" disabled={!agreed} aria-describedby="gen-enter-hint"
                  onClick={() => { setView((old) => ({ ...old, notice: false })); window.scrollTo({ top: 0 }); }}>{result || draft || picture ? "계속하기" : "확인하고 시작하기"}</button>
          <p className="form-hint" id="gen-enter-hint">확인해야 다음 단계로 넘어갈 수 있습니다.{result || draft || picture ? " 작업하던 내용은 그대로 유지됩니다." : ""}</p>
        </div>
      </section>
      )}

      {status === null && <Spinner label="서버 상태를 확인하는 중" />}
      {status === "error" && <PageAlert kind="danger">서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 문의해 주세요.</PageAlert>}
      {ready && entered && !status["사용 가능"] && (
        <PageAlert kind="info">지금은 생성형 AI로 후보를 만들 수 없습니다. {plainReason(status.이유)}{"\n"}직접 입력해서 그릴 수는 있습니다.</PageAlert>
      )}
      {ready && entered && status["글꼴 안내"] && <PageAlert kind="warning">그림을 그릴 수 없습니다. {status["글꼴 안내"]}</PageAlert>}

      {ready && entered && view.input && (
      <section id="generate-input" className="nav-anchor image-section">
        <h2 className="section-title">문단</h2>
        <form className="fieldset review-form is-sectioned" onSubmit={ask}>
          <div className="form-section" role="radiogroup" aria-labelledby="gen-type-title">
            <h3 className="form-section-title" id="gen-type-title">제작 그림 유형</h3>
            <div className="krds-check-area gen-types">
              {TYPES.map((entry) => (
                <div className="krds-form-check" key={entry.value}>
                  <input type="radio" id={`gen-type-${entry.value}`} name="gen-type" checked={form.type === entry.value} aria-describedby="gen-type-hint"
                         onChange={() => setForm((old) => ({ ...old, type: entry.value, kind: "" }))} />
                  <label htmlFor={`gen-type-${entry.value}`}>{entry.label}</label>
                </div>
              ))}
            </div>
            {/* 고른 유형의 설명과, 종류가 여럿인 유형(도표, 그래프)의 종류 고르기를 한 줄에 둔다 — 유형을 고른 바로 아래에서 이어 읽힌다 */}
            <div className="gen-type-detail">
              {FAMILY[form.type] && (
                <div className="gen-kind">
                  <label htmlFor="gen-kind">{type.label}의 종류</label>
                  <select id="gen-kind" className="krds-form-select" value={form.kind} onChange={(e) => set("kind")(e.target.value)}>
                    <option value="">자동 선택(생성형 AI)</option>
                    {FAMILY[form.type].map((value) => <option key={value} value={value}>{KIND_LABEL[value]}</option>)}
                  </select>
                </div>
              )}
              <p className="form-hint" id="gen-type-hint">{type.hint}</p>
            </div>
          </div>
          <div className="form-section">
            <div className="form-group form-group-wide">
              <div className="form-tit"><label htmlFor="gen-text">집필한 문단</label></div>
              <div className="form-conts">
                <div className="textarea-wrap">
                  <textarea id="gen-text" className="krds-input recommend-text" rows={7} maxLength={4000} value={form.text} aria-describedby="gen-text-hint"
                            placeholder={type.picture ? `${type.label}${type.value === "photo" ? "으로" : "로"} 나타낼 문단을 붙여 넣어 주세요. 문단 없이 ‘그림으로 나타낼 부분’에 주제만 입력할 수도 있습니다.` : "도표, 표, 그래프로 나타낼 문단을 붙여 넣어 주세요."} onChange={(e) => set("text")(e.target.value)} />
                  <p className="textarea-count"><span className="sr-only">입력한 글자 수 </span><span className="count-now">{form.text.length}</span><span className="count-total">/4000</span></p>
                </div>
              </div>
              <p className="form-hint" id="gen-text-hint">{handed.text ? "이미지 추천에서 넘겨받은 문단입니다. " : ""}그림의 글과 수는 이 문단에 있는 내용만 사용합니다. 후보를 만들 때 이 문단이 외부 생성형 AI 서비스로 전송됩니다.</p>
            </div>
          </div>
          <details className="gen-more" open={more || !!type.picture} onToggle={(e) => setMore(e.currentTarget.open)}>
            <summary>추가 입력 <span className="meta">(선택) 수행준거{form.criterion.trim() ? " 입력함" : ""}, 그림으로 나타낼 부분{form.focus.trim() ? " 입력함" : ""}, 가로 크기 {form.width}mm</span></summary>
            <div className="gen-more-body">
              <div className="gen-field gen-more-wide">
                <label htmlFor="gen-criterion">수행준거</label>
                <input id="gen-criterion" type="text" className="krds-input" maxLength={400} value={form.criterion}
                       placeholder="예: 1.1 예약 접수 절차에 따라 예약을 접수할 수 있다." onChange={(e) => set("criterion")(e.target.value)} />
              </div>
              <div className="gen-field">
                <label htmlFor="gen-focus">그림으로 나타낼 부분</label>
                <input id="gen-focus" type="text" className="krds-input" maxLength={200} value={form.focus} aria-describedby="gen-focus-hint"
                       placeholder="예: 예약 접수의 순서" onChange={(e) => set("focus")(e.target.value)} />
                <p className="form-hint" id="gen-focus-hint">{type.picture ? "문단 없이 주제만 입력하면 AI 창작(표기 예 4)으로 표기합니다." : "문단이 길 때 입력해 주세요. 그림의 글로는 사용하지 않습니다."}</p>
              </div>
              <div className="gen-field">
                <label htmlFor="gen-width">원고에 넣을 가로 크기(mm)</label>
                <input id="gen-width" type="number" className="krds-input" min={40} max={170} step={5} value={form.width} aria-describedby="gen-width-hint"
                       onChange={(e) => set("width")(Math.min(170, Math.max(40, Number(e.target.value) || 150)))} />
                <p className="form-hint" id="gen-width-hint">이 크기에서 300 DPI가 되도록 그립니다.</p>
              </div>
            </div>
          </details>
          <div className="form-group form-group-wide form-actions">
            {error && <PageAlert kind="danger">{error}</PageAlert>}
            <div className="run-buttons image-actions">
              <button type="submit" className="krds-btn large primary" disabled={!canAsk || !status["사용 가능"]}>{busy ? "후보를 만드는 중" : type.picture ? "장면 만들기" : "후보 만들기"}</button>
              {type.picture
                ? <button type="button" className="krds-btn large secondary" onClick={() => startPicture(true)}>장면 직접 입력</button>
                : <button type="button" className="krds-btn large secondary" disabled={busy} onClick={() => open(BLANK[blankKind], "manual")}>직접 입력</button>}
            </div>
          </div>
        </form>
      </section>
      )}

      {entered && picture && (
        <PictureMaker key={picture.key} request={picture} engine={status["그림 엔진"]} hasDb={!!status.DB} canManage={canManage} needsName={authStatus === "open"} onStage={setPictureStage} />
      )}

      {entered && result && view.candidates && (
      <section id="generate-candidates" className="nav-anchor image-section" aria-live="polite">
        <h2 className="section-title">후보<span className="meta"> {candidates.length}개 가운데 {result.usable}개 통과</span></h2>
        <p className="recommend-method">
          <span className={`krds-badge ${result.method === "llm" ? "bg-light-information" : "bg-light-gray"}`}>{result.method === "llm" ? `생성형 AI${result.model ? `(${result.model})` : ""}` : "생성형 AI 사용 안 함"}</span>
          <span className="meta"> {plainReason(result.note)}{result.reason ? ` 생성형 AI의 설명: ${result.reason}` : ""}</span>
        </p>
        <ul className="gen-candidates">
          {candidates.map((entry, i) => (
            <li key={i} className={`gen-candidate${entry.ok ? "" : " is-rejected"}${wide === i || aspects[i] > LONG ? " is-wide" : ""}${picked === i ? " is-picked" : ""}`}>
              <h3><span className="gen-candidate-name">후보 {i + 1}{entry.spec && <span className="meta"> {KIND_LABEL[entry.spec.kind]}{entry.spec.title ? `, ${entry.spec.title}` : ""}</span>}</span>
                <span className="gen-candidate-badges">
                  <span className={`krds-badge ${entry.ok ? "bg-light-success" : "bg-light-danger"}`}>{entry.ok ? "검사 통과" : "제외"}</span>
                  {entry.ok && entry.omissions?.length > 0 && <span className="krds-badge bg-light-warning">누락 의심 {entry.omissions.length}건</span>}
                </span></h3>
              {entry.ok && <Preview spec={entry.spec} width={form.width} alt={`후보 ${i + 1} ${entry.spec.title || KIND_LABEL[entry.spec.kind]}`}
                                    compact={wide !== i && !(aspects[i] > LONG)}
                                    onDrawn={(blob, summary) => { if (summary) setAspects((old) => (old[i] ? old : { ...old, [i]: summary.width / summary.height })); }} />}
              {entry.error && <p className="form-hint-invalid">{entry.error}</p>}
              <Notes problems={entry.problems} omissions={entry.ok ? entry.omissions : []} />
              {entry.spec && (
                <div className="gen-candidate-actions">
                  <button type="button" className={`krds-btn small ${entry.ok ? "primary" : "tertiary"}`} onClick={() => open(entry.spec, "ai", i)}>
                    {entry.ok ? "이 후보 선택" : "수정해서 사용"}<span className="sr-only"> 후보 {i + 1}</span></button>
                  {entry.ok && !(aspects[i] > LONG) && (
                    <button type="button" className="krds-btn small tertiary" aria-expanded={wide === i} onClick={() => setWide(wide === i ? null : i)}>
                      {wide === i ? "작게 보기" : "크게 보기"}<span className="sr-only"> 후보 {i + 1}</span></button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
        {candidates.length === 0 && result.method === "llm" && <PageAlert kind="info">이 문단에서 {type.label}{type.value === "photo" ? "으로" : "로"} 나타낼 내용을 찾지 못했습니다. 유형이나 종류를 바꾸거나 직접 입력해서 그릴 수 있습니다.</PageAlert>}
      </section>
      )}

      {entered && draft && (
      <section id="generate-edit" className="nav-anchor image-section" ref={editRef}>
        <h2 className="section-title">수정과 내려받기<span className="meta"> {KIND_LABEL[draft.kind]}{origin === "manual" ? ", 직접 입력" : ", 생성형 AI 후보"}</span></h2>
        <PageAlert kind="warning">항목의 위치가 문단의 뜻과 맞는지는 자동으로 검사하지 못합니다. 문단과 그림을 비교해 확인하고, 잘못된 항목은 수정한 뒤 다시 그려 주세요.</PageAlert>
        <div className="gen-work">
          <div className="gen-work-left">
            {(asked?.text || form.text) && <blockquote className="gen-source"><strong>문단</strong>{asked?.text || form.text}</blockquote>}
            {origin === "manual" && (
              <div className="gen-field">
                <label htmlFor="gen-switch">종류</label>
                <select id="gen-switch" className="krds-form-select" value={draft.kind} onChange={(e) => { setDraft(clone(BLANK[e.target.value])); setShown(null); }}>
                  {Object.keys(BLANK).map((value) => <option key={value} value={value}>{KIND_LABEL[value]}</option>)}
                </select>
              </div>
            )}
            <SpecEditor spec={draft} onChange={setDraft} disabled={drawing} flags={flags} />
            {drawError && <PageAlert kind="danger">{drawError}</PageAlert>}
            <div className="run-buttons image-actions">
              <button type="button" className="krds-btn medium primary" disabled={drawing} onClick={() => draw()}>{drawing ? "그리는 중" : shown ? "다시 그리기" : "그리기"}</button>
            </div>
          </div>
          <div className="gen-work-right" aria-live="polite">
            {shown ? (<>
              {dirty && <PageAlert kind="info">내용을 수정했습니다. [다시 그리기]를 눌러야 그림에 반영됩니다.</PageAlert>}
              <Preview spec={shown.spec} width={form.width} alt={shown.spec.title || KIND_LABEL[shown.spec.kind]} onDrawn={(blob, summary) => { drawn.current = blob ? { blob, summary } : null; }} />
              <Notes problems={shown.problems} omissions={shown.omissions} />
              {isGraph(shown.spec.kind) && <p className="form-hint">그래프의 값이 문단의 수와 같은지, 범주와 값이 서로 맞는지 문단과 비교해 확인해 주세요.</p>}
              {shown.problems.length > 0 && <p className="form-hint">문단에 없는 표현이라도 집필자가 직접 수정해 넣은 것이면 그대로 사용할 수 있습니다. 생성형 AI가 넣은 표현이면 문단의 표현으로 바꿔 주세요.</p>}
            </>) : <p className="meta">내용을 입력하고 [그리기]를 누르면 여기에 그림이 표시됩니다.</p>}
        {shown && (<>
        <h3 className="form-section-title gen-mark-title">원고 표기 문구</h3>
        {origin === "manual" ? (
          <p className="form-hint">생성형 AI를 사용하지 않고 직접 입력해 그린 그림입니다. AI 활용 줄 없이 출처 줄(출처: 집필진 제작(연도))과 그림 번호, 제목만 표기합니다.</p>
        ) : (<>
          <div className="gen-mark-fields">
            <div className="gen-field"><label htmlFor="gen-tool">활용한 AI 도구</label>
              <input id="gen-tool" type="text" className="krds-input" maxLength={40} value={mark.tool} placeholder="예: Claude" onChange={(e) => setMark((old) => ({ ...old, tool: e.target.value }))} /></div>
            <div className="gen-field"><label htmlFor="gen-date">활용 일자</label>
              <input id="gen-date" type="date" className="krds-input" value={mark.date} onChange={(e) => setMark((old) => ({ ...old, date: e.target.value || today() }))} /></div>
            <div className="gen-field"><label htmlFor="gen-number">번호 <span className="meta">(선택)</span></label>
              <input id="gen-number" type="text" className="krds-input" maxLength={10} value={mark.number} placeholder="예: 1-2" onChange={(e) => setMark((old) => ({ ...old, number: e.target.value.trim() }))} /></div>
          </div>
          {marking?.error && <p className="form-hint-invalid" role="alert">{marking.error}</p>}
          {marking?.lines && (
            <div className="recommend-credit gen-mark-lines">
              <code>{marking.lines.map((line) => <span key={line}>{line}</span>)}</code>
              <button type="button" className="krds-btn small secondary" onClick={async () => setDone((await copyText(marking.lines.join("\n"))) ? "표기 문구를 복사했습니다." : "복사하지 못했습니다.")}>표기 문구 복사</button>
            </div>
          )}
          {marking?.note && <p className="form-hint">{marking.note}</p>}
          <p className="form-hint">AI 도구 사용 표기 예 1(집필진이 내용을 작성하고 AI로 이미지를 만든 경우)의 형식입니다. 서약서에 첨부할 결과물 현황은 그림을 원고에 넣은 뒤 <Link to="/ai-image">이미지 AI 보완</Link>에서 만듭니다.</p>
        </>)}
        {done && <PageAlert kind="success">{done}</PageAlert>}
        <div className="run-buttons image-actions">
          <button type="button" className="krds-btn medium primary" disabled={dirty} onClick={savePng}>그림(PNG) 내려받기</button>
          {shown.spec.kind === "table" && <button type="button" className="krds-btn medium secondary" disabled={dirty} onClick={copyTable}>표로 복사(한글 프로그램용)</button>}
        </div>

        {status.DB && (<>
        <h3 className="form-section-title gen-mark-title">이미지 저작권 DB</h3>
        <p className="form-hint">이 그림과 유사한 그림이 이미지 저작권 DB에 있는지 찾습니다. 같은 파일과, 크기를 줄이거나 다시 저장한 그림을 찾습니다. 그림 유사도 계산을 사용하는 서버에서는 내용이 비슷한 그림도 찾습니다.
          구성이 같은 도표는 내용이 달라도 유사한 그림으로 나올 수 있으니 직접 확인해 주세요.{canManage ? "" : " 기관이 확정한 그림과만 비교합니다."}</p>
        <div className="run-buttons image-actions">
          <button type="button" className="krds-btn medium secondary" disabled={dirty || similar === "loading"} onClick={findSimilar}>{similar === "loading" ? "찾는 중" : "유사한 그림 찾기"}</button>
        </div>
        <div aria-live="polite">
          {similar?.error && <PageAlert kind="danger">{similar.error}</PageAlert>}
          {similar && similar !== "loading" && !similar.error && (<>
            <p className="meta gen-similar-summary">{similar.범위} {similar["대조한 그림"]}장과 비교했습니다{similar["남은 그림"] > 0 ? `(아직 비교하지 못한 그림 ${similar["남은 그림"]}장은 다시 누르면 이어서 비교합니다)` : ""}.
              {similar.임베딩 ? "" : " 그림 유사도 계산은 사용하지 않았습니다."}</p>
            {similar["닮은 그림"].length === 0 ? <PageAlert kind="success">유사한 그림을 찾지 못했습니다.</PageAlert> : (
              <ul className="gen-similar">
                {similar["닮은 그림"].map((entry) => (
                  <li key={entry.id}>
                    <img src={canManage ? api.images.fileUrl(entry.id) : api.images.recommendableFileUrl(entry.id)} alt={entry.title || "제목 없는 그림"} loading="lazy" />
                    <div>
                      <strong>{entry.title || "제목 없음"}</strong>
                      <span className="meta">{ASSET_LABEL[entry.kind] || "종류 없음"}, {METHOD_LABEL[entry.방법] || entry.방법}, 유사도 {entry.점수}, {entry.확정 ? "기관 확정" : "확정 전"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </>)}
        </div>
        {canManage && (<>
          <p className="form-hint">이 그림을 이미지 저작권 DB에 등록합니다. 분류는 ‘집필진 제작’으로{origin === "ai" ? ", AI 활용 유형은 1(집필진 작성 내용 기반 AI 생성)로 도구, 일자와 함께" : ""} 기록합니다.
            권리 귀속과 재사용 범위는 정하지 않습니다. 이미지 저작권 DB에서 확정하기 전에는 추천 목록에 나오지 않습니다.</p>
          <div className="gen-mark-fields">
            <div className="gen-field"><label htmlFor="gen-module">모듈 코드 <span className="meta">(선택)</span></label>
              <input id="gen-module" type="text" className="krds-input" maxLength={30} value={store.module} placeholder="예: LM1203020201_24v3" onChange={(e) => setStore((old) => ({ ...old, module: e.target.value }))} /></div>
            {authStatus === "open" && (
              <div className="gen-field"><label htmlFor="gen-by">등록자</label>
                <input id="gen-by" type="text" className="krds-input" maxLength={80} value={store.by} onChange={(e) => setStore((old) => ({ ...old, by: e.target.value }))} /></div>
            )}
          </div>
          <p className="form-hint">모듈 코드를 입력하면 위의 번호와 함께 수록 위치로 기록합니다.</p>
          {store.error && <PageAlert kind="danger">{store.error}</PageAlert>}
          {store.result && <PageAlert kind="success">{store.result["새 그림"] ? "이미지 저작권 DB에 등록했습니다." : "같은 그림이 이미 있어 정보를 합쳤습니다."}
            {store.result["확정 유지"] ? " 기관이 확정한 권리 정보는 바꾸지 않았습니다." : ""} <Link to="/images">이미지 저작권 DB</Link>에서 권리 정보를 확인하고 확정해 주세요.</PageAlert>}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn medium secondary" onClick={register}
                    disabled={dirty || store.busy || (origin === "ai" && !mark.tool.trim()) || (authStatus === "open" && !store.by.trim())}>{store.busy ? "등록하는 중" : "이미지 저작권 DB에 등록"}</button>
          </div>
        </>)}
        </>)}
        </>)}
          </div>
        </div>

      </section>
      )}
    </main>
    <TopButton />
    <Footer />
    </>
  );
}
