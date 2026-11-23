// 원고 문장 추천(REQ-02-004) — 원고를 올리면 AI가 작성 규칙(종결형·표현)에 어긋난 문장을 구성별로 찾아 정정 후보를 순위와 함께 최대 5개 보여 준다.
// 집필자가 후보 하나를 '채택'하거나(그대로, 고쳐서, 또는 직접 써서) '기각'하고, 채택률과 채택 결과(JSON·CSV)를 내려받는다. 계산은 서버(ncs_suggest)가 한다.
// 원고 본문은 고치지 않는다 — 채택한 문장은 '채택 문장 메모 원고(hwpx)'로 그 문장 자리에 한글 메모로 달아 돌려준다(POST /api/suggest/memo).
// AI에는 문장의 자리와 앞뒤 문장, 수행 내용 문장이면 같은 학습 내용의 학습 목표(문맥)를 함께 보내고, 서버에 참고 문장 묶음(기존 학습모듈, 공공저작물)이 있으면 후보마다 근거 문장이 붙는다.
// '정정 후보 문장표(CSV)'는 요구사항 산출물인 원본 문장과 정정 후보 1~5순위(근거 문장 포함)의 표다.
// AI(Claude, ncs_llmreview.claude)는 서버에 ANTHROPIC_API_KEY·반출 승인이 있으면 자동으로 부른다(체크박스 없음). 없으면 'AI 미설정 — 이유'만 보인다.
// 후보 출처는 모두 'AI 생성'이고, 집필자가 고치면 'AI 생성 후 집필자 수정', 직접 쓰면 '집필자 작성'으로 기록한다 — 집필자 서약서 고지에 쓰는 구분이다.
// 결과와 결정은 이 브라우저(localStorage)에만 30일 보관한다(lib/suggest.js). 유용성(5점 척도) 응답은 채택 기록 JSON에 함께 내려간다(검증방법: 집필자 Likert).
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { copyText } from "../lib/clipboard.js";
import { plainReason } from "../lib/plain.js";
import {
  DIRECT, KEEP_DAYS, candidateRows, chosenOf, clearSaved, decisionRows, diffChars, loadSaved, localIso, memoRecords, prefixOf, saveState, toCsv,
} from "../lib/suggest.js";
import { Spinner } from "../components/Badge.jsx";
import { ConfirmDialog } from "../components/ConfirmDialog.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { RawJson } from "../components/RawJson.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { usePageTitle } from "../lib/hooks.js";

// 카드 상태 = AI가 준 사유 유형(서버 ncs_suggest.config.REASONS) · 문장 직접 입력의 판단불가·지적 없음
const STATUS_BADGE = {
  "종결형 위반": "bg-light-danger", "주어 군더더기": "bg-light-warning", "어색한 낱말": "bg-light-secondary", "중복 표현": "bg-light-warning",
  "문장부호": "bg-light-warning", "기타 표현": "bg-light-warning", "판단불가": "bg-light-gray", "지적 없음": "bg-light-success",
};
const SOURCE_BADGE = { "AI 생성": "bg-light-secondary" };
const NO_REWRITE = ["판단불가", "지적 없음"];   // 직접 입력 카드 가운데 고칠 곳이 없는 것 — 직접 고쳐 쓰기를 권하지 않는다
const DECISION_FILTERS = [{ value: "", label: "결정 전체" }, { value: "미정", label: "아직 정하지 않음" }, { value: "채택", label: "채택" }, { value: "기각", label: "기각" }];
// 유용성 문항(요구사항정의서 REQ-02-004 검증방법 '집필자 Likert 3.5점 이상') — 5점 척도
const SURVEY_QUESTION = "추천이 문장을 다듬는 데 도움이 되었습니까?";
const SURVEY_SCALE = [[1, "전혀 아니다"], [2, "아니다"], [3, "보통이다"], [4, "그렇다"], [5, "매우 그렇다"]];
const NO_SURVEY = { score: null, comment: "" };

function saveFile(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function SuggestPage() {
  usePageTitle("문장 추천");
  const [saved] = useState(loadSaved);              // 이 브라우저에 보관해 둔 지난 결과(없으면 null)
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(saved?.result ?? null);
  const [kinds, setKinds] = useState([]);
  const [kind, setKind] = useState("교수 방법");
  const [text, setText] = useState("");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [typed, setTyped] = useState(saved?.typed ?? []);          // 직접 입력해 받은 카드들(최근 것이 위)
  const [typing, setTyping] = useState(false);
  const [typedError, setTypedError] = useState(null);
  const [decisions, setDecisions] = useState(saved?.decisions ?? {}); // 카드 key → 결정(lib/suggest.js 머리 주석)
  const [survey, setSurvey] = useState(saved?.survey ?? NO_SURVEY);
  const [reasonFilter, setReasonFilter] = useState("");
  const [decisionFilter, setDecisionFilter] = useState("");
  const [showDiff, setShowDiff] = useState(true);
  const [kept, setKept] = useState(saved ? { ok: true, at: saved.savedAt } : null);   // 보관 상태(안내 줄)
  const [asking, setAsking] = useState(false);      // 기록 지우기 확인 창
  const [memo, setMemo] = useState(null);           // 메모 원고 내려받기 결과 { busy } | { error } | { summary }
  const aborter = useRef(null);

  useEffect(() => {
    api.suggest.kinds().then(({ ok, data }) => { if (ok) setKinds(data.종류); });
  }, []);

  // 결과·결정·유용성 응답이 바뀔 때마다 이 브라우저에 보관한다. 보관할 것이 없으면 지운다.
  useEffect(() => {
    // 보관해 둔 것을 막 불러온 그대로면 다시 쓰지 않는다 — 열어 보기만 해서는 보관 기한이 늘지 않게
    if (saved && result === (saved.result ?? null) && typed === saved.typed && decisions === saved.decisions && survey === saved.survey) return;
    if (!result && !typed.length) { clearSaved(); setKept(null); return; }
    const at = localIso();
    setKept({ ok: saveState({ result, typed, decisions, survey, savedAt: at }), at });
  }, [saved, result, typed, decisions, survey]);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    aborter.current = new AbortController();
    setBusy(true);
    setError(null);
    const { ok, data, error: message, aborted } = await api.suggest.manuscript({ file, signal: aborter.current.signal });
    setBusy(false);
    if (aborted) return;
    if (!ok) { setError(message); return; }      // 실패해도 보관해 둔 지난 결과는 그대로 둔다
    setResult(data);
    setMemo(null);
    setReasonFilter("");
    setDecisionFilter("");
    setDecisions((old) => Object.fromEntries(Object.entries(old).filter(([key]) => key.startsWith("입력"))));
  }

  async function submitSentence(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setTyping(true);
    setTypedError(null);
    const { ok, data, error: message } = await api.suggest.sentence({ text, kind, before, after });
    setTyping(false);
    if (!ok) { setTypedError(message); return; }
    setTyped((old) => [{ ...data, key: `입력-${old.length + 1}`, 원고명: DIRECT }, ...old]);
  }

  const manuscriptCards = useMemo(
    () => (result ? result.구성.flatMap((part) => part.문장.map((card) => ({ ...card, key: card.번호, 원고명: result.원고 }))) : []),
    [result],
  );
  // 기록에 드는 카드: 원고의 고칠 문장 전부 + 직접 입력 가운데 고칠 곳이 있던 것(후보가 없어도 집필자가 직접 고쳐 쓸 수 있다)
  const allCards = [...manuscriptCards, ...typed.filter((card) => !NO_REWRITE.includes(card.상태))];
  const grounded = allCards.reduce((sum, card) => sum + card.후보.filter((item) => item["근거 문장"]).length, 0);
  const decided = allCards.filter((card) => decisions[card.key]);
  const adopted = decided.filter((card) => decisions[card.key].choice === "채택");
  const rewritten = adopted.filter((card) => decisions[card.key].text != null);
  const bulked = allCards.filter((card) => decisions[card.key]?.bulk);
  const pending = allCards.filter((card) => !decisions[card.key] && card.후보.length);
  const rate = decided.length ? Math.round((adopted.length / decided.length) * 1000) / 10 : null;
  const memoRows = memoRecords(manuscriptCards, decisions);
  const visibleCards = manuscriptCards.filter((card) => (!reasonFilter || card.상태 === reasonFilter)
    && (!decisionFilter || (decisions[card.key]?.choice || "미정") === decisionFilter));

  // 같은 결정을 다시 누르면 결정을 지운다(채택 취소·기각 취소)
  const decide = useCallback((card, choice, rank = null, edited = null) => {
    setDecisions((old) => {
      const was = old[card.key];
      const same = was?.choice === choice && was?.rank === rank && (was?.text ?? null) === edited;
      const next = { ...old };
      if (same) delete next[card.key]; else next[card.key] = { choice, rank, text: edited, bulk: false, at: localIso() };
      return next;
    });
  }, []);

  // 아직 정하지 않은 문장에 1순위 후보를 한꺼번에 채택한다. 기록에 '일괄 채택'으로 남고 되돌릴 수 있다.
  function adoptFirst() {
    const at = localIso();
    setDecisions((old) => ({ ...old, ...Object.fromEntries(pending.map((card) => [card.key, { choice: "채택", rank: 1, text: null, bulk: true, at }])) }));
  }

  function undoBulk() {
    setDecisions((old) => Object.fromEntries(Object.entries(old).filter(([, decision]) => !decision.bulk)));
  }

  function forget() {
    setResult(null);
    setTyped([]);
    setDecisions({});
    setSurvey(NO_SURVEY);
    setMemo(null);
    setAsking(false);
  }

  function download(kindOfFile) {
    const rows = decisionRows(allCards, decisions);
    const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "");
    const base = `문장추천_채택기록_${stamp}`;
    if (kindOfFile === "table") saveFile(toCsv(candidateRows(allCards, decisions)), `문장추천_정정후보문장표_${stamp}.csv`, "text/csv;charset=utf-8");
    else if (kindOfFile === "csv") saveFile(toCsv(rows), `${base}.csv`, "text/csv;charset=utf-8");
    else saveFile(JSON.stringify({
      원고: result?.원고 ?? null, 채택률: rate, 채택: adopted.length, "고쳐 쓴 채택": rewritten.length, "일괄 채택": bulked.length,
      결정: decided.length, 카드: allCards.length,
      유용성: { 문항: SURVEY_QUESTION, 척도: SURVEY_SCALE.map(([score, label]) => `${score} ${label}`).join(", "), 점수: survey.score, 의견: survey.comment },
      기록: rows,
    }, null, 2), `${base}.json`, "application/json");
  }

  const canMemo = file && /\.hwpx$/i.test(file.name) && memoRows.length > 0;
  async function downloadMemo() {
    if (!canMemo) return;
    setMemo({ busy: true });
    const { ok, error: message, summary } = await api.suggest.memo({ file, records: memoRows, filename: `${file.name.replace(/\.hwpx$/i, "")}_문장추천메모.hwpx` });
    setMemo(ok ? { summary } : { error: message });
  }
  // 메모 원고를 받을 수 없는 까닭(받을 수 있으면 null)
  const memoHint = !manuscriptCards.length ? null
    : !memoRows.length ? "원고 문장을 하나 이상 채택하면 받을 수 있습니다."
    : !file ? "위 원고 칸에서 같은 원고(hwpx)를 다시 고르면 받을 수 있습니다. 다시 검사할 필요는 없습니다."
    : !/\.hwpx$/i.test(file.name) ? "메모는 hwpx 원고에만 달 수 있습니다. 한글에서 hwpx로 저장한 원고를 고르세요."
    : null;

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page suggest-page">
      <h1 className="page-title">문장 추천</h1>
      {/* 설명은 다른 화면처럼 '무엇을 올리면 무엇이 나오는지 → 무엇을 보는지 → 할 일 → 하지 않는 일 → 파일 처리' 순서로 짧게 쓴다.
          후보를 거르는 방법, 근거 문장, 버린 후보 같은 세부는 결과 화면에서 그 자리에 보인다 */}
      <p className="page-desc">
        원고(hwp, hwpx)를 올리면 생성형 AI가 학습모듈 작성 규칙(문장의 끝맺음)과 표현(군더더기 주어, 어색한 낱말, 중복, 문장부호)에 어긋난 문장을 찾아,
        문장마다 정정 후보를 최대 5개 보여 줍니다. 후보를 그대로 또는 고쳐서 채택하거나 기각하세요.
        문장만 다듬으며 내용이 적절한지는 판단하지 않고, 원고 파일도 고치지 않습니다. 올린 파일은 계산 뒤 바로 지웁니다.
        결과와 채택 기록은 이 브라우저에만 {KEEP_DAYS}일 동안 보관합니다.
      </p>

      {/* 칸이 하나라 구획 제목 없이 3열 격자와 실행 줄만 쓴다(다른 화면의 입력 묶음과 같은 열·폭) */}
      <form className="fieldset review-form is-sectioned" onSubmit={submit}>
        <div className="form-section-grid">
        <FileSlot id="suggest-file" label="원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={busy}
                  hint="hwp, hwpx. hwpx면 수행 순서 번호를 더 정확히 찾고, 채택 문장을 메모로 단 원고도 받을 수 있습니다." />
        </div>
        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !file}>{busy ? "찾는 중" : "문장 추천"}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

      {busy && <ResultHead status={<Spinner label="생성형 AI가 문장을 살피는 중" />} />}
      {result && !busy && (
        <SuggestResult result={result} cards={manuscriptCards} visible={visibleCards} decisions={decisions} onDecide={decide} showDiff={showDiff}
          tools={(
            <div className="suggest-tools">
              <KrdsSelect id="suggest-filter-reason" value={reasonFilter} title="사유 유형으로 거르기" onChange={setReasonFilter}
                          options={[{ value: "", label: `사유 전체 (${manuscriptCards.length})` },
                                    ...Object.entries(result.요약["사유별"]).map(([name, n]) => ({ value: name, label: `${name} (${n})` }))]} />
              <KrdsSelect id="suggest-filter-decision" value={decisionFilter} title="결정 상태로 거르기" onChange={setDecisionFilter} options={DECISION_FILTERS} />
              <div className="krds-form-check">
                <input type="checkbox" id="suggest-diff" checked={showDiff} onChange={(e) => setShowDiff(e.target.checked)} />
                <label htmlFor="suggest-diff">바뀐 글자 표시</label>
              </div>
              <span className="suggest-tools-end">
                {bulked.length > 0 && <button type="button" className="krds-btn small text" onClick={undoBulk}>일괄 채택 {bulked.length}개 되돌리기</button>}
                <button type="button" className="krds-btn small secondary" onClick={adoptFirst} disabled={!pending.length}
                        title="일괄 채택한 문장은 기록에 '일괄 채택'으로 남습니다. 하나씩 읽고 확인하세요.">
                  정하지 않은 {pending.length}개에 1순위 채택
                </button>
              </span>
            </div>
          )} />
      )}

      <h2 className="section-title">문장 직접 입력</h2>
      <form className="fieldset review-form suggest-direct" onSubmit={submitSentence}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="suggest-kind">문장 종류</label></div>
          <div className="form-conts">
            <KrdsSelect id="suggest-kind" value={kind} title="문장 종류"
                        options={kinds.map((k) => ({ value: k.이름, label: `${k.이름} (${k["규정 꼴"]})` }))} onChange={setKind} />
          </div>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="suggest-text">문장</label></div>
          <div className="form-conts">
            <textarea id="suggest-text" className="krds-input" rows={2} value={text} onChange={(e) => setText(e.target.value)}
                      placeholder="예: 사례를 중심으로 요구사항 분석 절차를 설명함." />
          </div>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="suggest-before">앞 문장 <span className="meta">(선택)</span></label></div>
          <div className="form-conts">
            <input id="suggest-before" type="text" className="krds-input" value={before} maxLength={400} onChange={(e) => setBefore(e.target.value)}
                   aria-describedby="suggest-context-hint" />
          </div>
        </div>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="suggest-after">뒤 문장 <span className="meta">(선택)</span></label></div>
          <div className="form-conts">
            <input id="suggest-after" type="text" className="krds-input" value={after} maxLength={400} onChange={(e) => setAfter(e.target.value)}
                   aria-describedby="suggest-context-hint" />
            <p id="suggest-context-hint" className="form-hint">앞뒤 문장을 넣으면 생성형 AI가 흐름에 맞는 서술어와 낱말을 고릅니다. 앞뒤 문장은 고치지 않습니다.</p>
          </div>
        </div>
        <div className="form-group form-actions">
          <div className="form-tit form-tit-spacer" aria-hidden="true"><label>&nbsp;</label></div>
          <div className="run-buttons">
            <button className="krds-btn secondary large" type="submit" disabled={typing || !text.trim()}>{typing ? "찾는 중" : "이 문장 추천받기"}</button>
          </div>
          <PageAlert kind="danger">{typedError}</PageAlert>
        </div>
      </form>
      {typed.map((card) => <SuggestCard key={card.key} card={card} decision={decisions[card.key]} onDecide={decide} showDiff={showDiff} />)}

      {(allCards.length > 0 || kept) && (
        <section className="suggest-tally" aria-live="polite">
          <h2 className="section-title">채택 기록</h2>
          {allCards.length > 0 && <>
          <dl className="upscale-summary">
            <div><dt>고칠 문장</dt><dd>{allCards.length}개</dd></div>
            <div><dt>결정</dt><dd>{decided.length}개 (채택 {adopted.length}, 기각 {decided.length - adopted.length})</dd></div>
            <div><dt>채택률</dt><dd><strong>{rate == null ? "-" : `${rate}%`}</strong></dd></div>
            <div><dt>고쳐 쓴 채택</dt><dd>{rewritten.length}개</dd></div>
            <div><dt>근거 문장이 있는 후보</dt><dd>{grounded}개</dd></div>
          </dl>
          <fieldset className="suggest-survey">
            <legend>{SURVEY_QUESTION} <span className="meta">(선택, 채택 기록 JSON에 함께 저장됩니다)</span></legend>
            <div className="krds-check-area">
              {SURVEY_SCALE.map(([score, label]) => (
                <div className="krds-form-check" key={score}>
                  <input type="radio" id={`suggest-survey-${score}`} name="suggest-survey" checked={survey.score === score}
                         onChange={() => setSurvey((old) => ({ ...old, score }))} />
                  <label htmlFor={`suggest-survey-${score}`}>{score} {label}</label>
                </div>
              ))}
            </div>
            <label htmlFor="suggest-survey-comment" className="sr-only">의견</label>
            <textarea id="suggest-survey-comment" className="krds-input" rows={2} value={survey.comment} placeholder="의견(선택): 도움이 된 점, 불편한 점"
                      onChange={(e) => setSurvey((old) => ({ ...old, comment: e.target.value }))} />
          </fieldset>
          <div className="run-buttons">
            <button className="krds-btn secondary medium" type="button" onClick={() => download("table")}>정정 후보 문장표(CSV)</button>
            <button className="krds-btn tertiary medium" type="button" onClick={() => download("json")}>채택 기록 내려받기(JSON)</button>
            <button className="krds-btn tertiary medium" type="button" onClick={() => download("csv")}>채택 기록 표(CSV)</button>
            {manuscriptCards.length > 0 && (
              <button id="suggest-memo" className="krds-btn tertiary medium" type="button" onClick={downloadMemo} disabled={!canMemo || memo?.busy}
                      aria-describedby="suggest-memo-hint">{memo?.busy ? "메모 다는 중" : "채택 문장 메모 원고(hwpx)"}</button>
            )}
          </div>
          {manuscriptCards.length > 0 && (
            <p id="suggest-memo-hint" className="meta">
              메모 원고는 채택한 문장 {memoRows.length}개를 그 문장 자리에 한글 메모로 단 사본입니다. 본문은 고치지 않습니다.
              {memoHint && ` ${memoHint}`}
              {canMemo && result && file.name !== result.원고 && ` 고른 파일(${file.name})의 이름이 검사한 원고(${result.원고})와 다릅니다. 같은 원고인지 확인하세요.`}
            </p>
          )}
          <PageAlert kind="danger">{memo?.error}</PageAlert>
          {memo?.summary && (
            <PageAlert kind={memo.summary.unplaced.length ? "warning" : "success"}>
              <p>채택 문장 {memo.summary.placed}개를 메모 {memo.summary.memos}개(총괄 메모 포함)로 달았습니다.</p>
              {memo.summary.unplaced.length > 0 && <>
                <p>원고에서 자리를 찾지 못한 문장 {memo.summary.unplaced.length}개는 총괄 메모에 적었습니다.</p>
                <ul className="krds-info-list dash">{memo.summary.unplaced.map((line, i) => <li key={i}>{line}</li>)}</ul>
              </>}
            </PageAlert>
          )}
          </>}
          {kept && (
            <p className="meta suggest-kept">
              {kept.ok
                ? `결과와 채택 기록을 이 브라우저에 보관했습니다(${kept.at.slice(0, 16).replace("T", " ")}). ${KEEP_DAYS}일이 지나면 지워집니다.`
                : "이 브라우저에 보관하지 못했습니다. 창을 닫기 전에 채택 기록을 내려받으세요."}{" "}
              <button type="button" className="krds-btn small text" onClick={() => setAsking(true)}>기록 지우기</button>
            </p>
          )}
        </section>
      )}
      {asking && (
        <ConfirmDialog title="기록 지우기" confirmLabel="지우기" onConfirm={forget} onCancel={() => setAsking(false)}>
          <p>이 브라우저에 보관한 문장 추천 결과와 채택 기록, 유용성 응답을 모두 지웁니다. 되돌릴 수 없으니 필요한 기록은 먼저 내려받으세요.</p>
        </ConfirmDialog>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function SuggestResult({ result, cards, visible, decisions, onDecide, showDiff, tools }) {
  const summary = result.요약;
  // 거른 카드를 구성 순서대로 묶는다
  const parts = [];
  visible.forEach((card) => {
    if (!parts.length || parts[parts.length - 1].구성 !== card.구성) parts.push({ 구성: card.구성, 문장: [] });
    parts[parts.length - 1].문장.push(card);
  });
  return (
    <section className="suggest-result">
      <ResultHead
        status={<span className={`krds-badge large ${cards.length ? "bg-light-warning" : "bg-light-success"}`}>{cards.length ? `고칠 문장 ${cards.length}개` : "고칠 문장 없음"}</span>}
        meta={`${result.원고}, 확인한 문장 ${summary["검사한 문장"]}개, 생성형 AI에 보낸 문장 ${summary["AI에 보낸 문장"]}개, ${Object.entries(summary["사유별"]).map(([name, n]) => `${name} ${n}`).join(", ") || "지적 없음"}, 추천 없음 ${summary["추천 없음"]}, 제외한 생성형 AI 후보 ${summary["버린 AI 후보"]}`}
        badges={<>
          <span id="suggest-ai-state" className="krds-badge bg-light-gray">{plainReason(result.AI.상태)}</span>{" "}
          {result["참고 문장"] && (
            <span id="suggest-refs-state" className={`krds-badge ${result["참고 문장"]["문장 수"] ? "bg-light-success" : "bg-light-gray"}`}>
              {result["참고 문장"]["문장 수"] ? `참고 문장 ${result["참고 문장"]["문장 수"]}개` : "참고 문장 묶음 없음"}
            </span>
          )}
        </>}
      />
      {result.알림.length > 0 && <PageAlert kind="info">{result.알림.map((note) => <p key={note}>{note}</p>)}</PageAlert>}
      {cards.length > 0 && tools}
      {cards.length > 0 && visible.length < cards.length && (
        <p className="meta" role="status">{cards.length}개 가운데 {visible.length}개를 보이고 있습니다.{visible.length === 0 && " 조건에 맞는 문장이 없습니다."}</p>
      )}
      {parts.map((part) => (
        <div key={part.구성}>
          <h2 className="section-title">{part.구성} <span className="meta">({part.문장.length})</span></h2>
          {part.문장.map((card) => <SuggestCard key={card.key} card={card} decision={decisions[card.key]} onDecide={onDecide} showDiff={showDiff} />)}
        </div>
      ))}
      <details className="raw">
        <summary>이 결과를 만든 방법</summary>
        <ul className="krds-info-list dash">
          {Object.entries(result.가정).map(([key, value]) => <li key={key}>{key}: {value}</li>)}
        </ul>
      </details>
      <RawJson data={result} title="원본 데이터 보기(개발자용)" />
    </section>
  );
}

// 후보 문장에서 원문과 달라진 글자를 표시한다: 새로 들어간 글자는 <ins>, 빠진 글자는 <del>. 읽어 주는 글은 후보 문장 그대로(aria-label).
function Diffed({ from, to }) {
  const parts = useMemo(() => diffChars(from, to), [from, to]);
  return parts.map((part, i) => {
    if (part.type === "add") return <ins key={i} className="suggest-ins">{part.text}</ins>;
    if (part.type === "del") return <del key={i} className="suggest-del">{part.text}</del>;
    return <React.Fragment key={i}>{part.text}</React.Fragment>;
  });
}

function SuggestCard({ card, decision, onDecide, showDiff }) {
  const [draft, setDraft] = useState(null);     // 고쳐 쓰는 중인 문장 { rank: 바탕 후보 순위|null(원문에서 직접), text }
  const [copied, setCopied] = useState(null);   // 방금 복사한 것(후보 순위 또는 'own')
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);
  const prefix = prefixOf(card);
  const chosen = chosenOf(card, decision);
  const context = card.문맥 || {};
  const goals = context["학습 목표"] || [];
  const hasContext = Boolean(context.앞 || context.뒤 || goals.length);
  const canRewrite = !NO_REWRITE.includes(card.상태);
  const draftId = `suggest-draft-${card.key}`;

  async function copy(what, sentence) {
    if (!(await copyText(prefix + sentence))) return;
    setCopied(what);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(null), 1500);
  }

  function adoptDraft() {
    const written = draft.text.replace(/\s+/g, " ").trim();
    const base = draft.rank ? card.후보.find((c) => c.순위 === draft.rank) : null;
    // 후보를 한 글자도 고치지 않았으면 그 후보를 그대로 채택한 것으로 적는다(출처가 'AI 생성'으로 남아야 한다)
    if (base && written === base.문장) { if (!(decision?.choice === "채택" && decision.rank === base.순위 && decision.text == null)) onDecide(card, "채택", base.순위); }
    else onDecide(card, "채택", draft.rank, written);
    setDraft(null);
  }
  const draftText = draft ? draft.text.replace(/\s+/g, " ").trim() : "";
  const sameAsChosen = draft && decision?.choice === "채택" && decision.rank === draft.rank && decision.text === draftText;

  return (
    <article className="suggest-card">
      <header className="suggest-card-head">
        <span className={`krds-badge ${STATUS_BADGE[card.상태] || "bg-light-gray"}`}>{card.상태}</span>
        <strong>{card.자리}</strong>
        <span className="meta">{card.종류}, 규정 꼴 {card["규정 꼴"]}</span>
        {decision && <span className={`krds-badge ${decision.choice === "채택" ? "bg-light-success" : "bg-light-gray"}`}>{decision.choice}{decision.bulk ? "(일괄)" : ""}</span>}
      </header>
      <p className="suggest-original"><span className="meta">원문</span> {card.원문}</p>
      {card.사유.length > 0 && <p className="meta">사유: {card.사유.join(" / ")}</p>}
      {hasContext && (
        <details className="suggest-context">
          <summary>문맥 보기</summary>
          <dl>
            {context.앞 && <><dt>앞 문장</dt><dd>{context.앞}</dd></>}
            {context.뒤 && <><dt>뒤 문장</dt><dd>{context.뒤}</dd></>}
            {goals.length > 0 && <><dt>같은 학습 내용의 학습 목표</dt><dd>{goals.join(" / ")}</dd></>}
          </dl>
        </details>
      )}
      {card.후보.length > 0 ? (
        <fieldset className="suggest-candidates">
          <legend className="sr-only">{card.자리} 정정 후보</legend>
          <ol>
            {card.후보.map((item) => {
              const picked = decision?.choice === "채택" && decision.rank === item.순위 && decision.text == null;
              return (
                <li key={item.순위} className={picked ? "chosen" : ""}>
                  <span className="rank">{item.순위}</span>
                  <div className="candidate-body">
                    <p className="candidate-text" aria-label={prefix + item.문장}>
                      {prefix}{showDiff ? <Diffed from={card.본문} to={item.문장} /> : item.문장}
                    </p>
                    <p className="meta">
                      <span className={`krds-badge ${SOURCE_BADGE[item.출처] || "bg-light-gray"}`}>{item.출처}</span>{" "}
                      {item.근거.join(" / ")}
                    </p>
                    {item["근거 문장"] && (
                      <p className="meta candidate-basis">
                        근거 문장: {item["근거 문장"].문장}{" "}
                        ({[item["근거 문장"].출처, item["근거 문장"].자리].filter(Boolean).join(", ")}{item["근거 문장"].출처 || item["근거 문장"].자리 ? ", " : ""}유사도 {item["근거 문장"].유사도})
                      </p>
                    )}
                  </div>
                  <span className="candidate-actions">
                    <button type="button" className="krds-btn small text" onClick={() => copy(item.순위, item.문장)}>
                      {copied === item.순위 ? "복사됨" : "복사"}<span className="sr-only"> {item.순위}순위 후보</span>
                    </button>
                    <button type="button" className="krds-btn small tertiary" onClick={() => setDraft({ rank: item.순위, text: item.문장 })}>
                      고치기<span className="sr-only"> {item.순위}순위 후보</span>
                    </button>
                    <button type="button" className={`krds-btn small ${picked ? "primary" : "secondary"}`} aria-pressed={picked}
                            onClick={() => onDecide(card, "채택", item.순위)}>{picked ? "채택함" : "채택"}<span className="sr-only"> {item.순위}순위 후보</span></button>
                  </span>
                </li>
              );
            })}
          </ol>
        </fieldset>
      ) : (
        <p className="suggest-none">{card["추천 없음"] || (card.상태 === "지적 없음" ? "생성형 AI가 고칠 곳을 찾지 못했습니다." : card.상태 === "판단불가" ? "생성형 AI를 쓸 수 없어 고칠 곳을 찾지 못했습니다(판단불가)." : "추천 없음")}</p>
      )}
      {chosen && decision.text != null && (
        <p className="suggest-own">
          <span className="krds-badge bg-light-success">{chosen.출처}</span>{" "}
          <span className="candidate-text" aria-label={prefix + chosen.문장}>{prefix}{showDiff ? <Diffed from={card.본문} to={chosen.문장} /> : chosen.문장}</span>{" "}
          {chosen.순위 !== "" && <span className="meta">({chosen.순위}순위 후보를 고침)</span>}
          <span className="candidate-actions">
            <button type="button" className="krds-btn small text" onClick={() => copy("own", chosen.문장)}>{copied === "own" ? "복사됨" : "복사"}</button>
            <button type="button" className="krds-btn small text" onClick={() => onDecide(card, "채택", decision.rank, decision.text)}>채택 취소</button>
          </span>
        </p>
      )}
      {draft && (
        <div className="suggest-edit">
          <label htmlFor={draftId}>{draft.rank ? `${draft.rank}순위 후보 고쳐 쓰기` : "원문에서 직접 고쳐 쓰기"}</label>
          <textarea id={draftId} className="krds-input" rows={2} value={draft.text} autoFocus aria-describedby={`${draftId}-hint`}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
          <p id={`${draftId}-hint`} className="meta">
            고쳐 쓴 문장은 규정 꼴({card["규정 꼴"]})을 다시 검사하지 않습니다.{prefix && ` 앞 번호(${prefix.trim()})는 빼고 쓰세요. 자동으로 붙습니다.`}
            {" "}기록에는 {draft.rank ? "'AI 생성 후 집필자 수정'" : "'집필자 작성'"}으로 남습니다.
          </p>
          <div className="candidate-actions">
            <button type="button" className="krds-btn small primary" disabled={!draftText || draftText === card.본문 || sameAsChosen} onClick={adoptDraft}>이 문장으로 채택</button>
            <button type="button" className="krds-btn small tertiary" onClick={() => setDraft(null)}>취소</button>
          </div>
        </div>
      )}
      {(card.후보.length > 0 || canRewrite) && !draft && (
        <div className="suggest-card-foot">
          {canRewrite && <button type="button" className="krds-btn small tertiary" onClick={() => setDraft({ rank: null, text: card.본문 })}>직접 고쳐 쓰기</button>}
          {card.후보.length > 0 && (
            <button type="button" className={`krds-btn small ${decision?.choice === "기각" ? "primary" : "tertiary"}`} aria-pressed={decision?.choice === "기각"}
                    onClick={() => onDecide(card, "기각")}>{decision?.choice === "기각" ? "모두 기각함" : "모두 기각"}</button>
          )}
        </div>
      )}
      {card["참고 예문"].length > 0 && (
        <div className="suggest-examples">
          <p className="meta">참고 예문(같은 원고에서 규정을 지킨 비슷한 문장이며 후보가 아닙니다)</p>
          <ul className="krds-info-list dash">
            {card["참고 예문"].map((ex) => <li key={ex.자리}>{ex.문장} <span className="meta">({ex.자리}, 유사도 {ex.유사도})</span></li>)}
          </ul>
        </div>
      )}
      {card["버린 AI 후보"].length > 0 && (
        <details className="suggest-dropped">
          <summary>제외한 생성형 AI 후보 {card["버린 AI 후보"].length}개</summary>
          <ul>{card["버린 AI 후보"].map((d, i) => <li key={i}>{d.문장} (제외 이유: {d.이유})</li>)}</ul>
        </details>
      )}
    </article>
  );
}
