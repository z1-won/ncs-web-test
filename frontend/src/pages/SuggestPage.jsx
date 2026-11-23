// 원고 문장 추천(REQ-02-004) — 원고를 올리면 AI가 작성 규칙(종결형·표현)에 어긋난 문장을 구성별로 찾아 정정 후보를 순위와 함께 최대 5개 보여 준다.
// 집필자가 후보 하나를 '채택'하거나 '기각'하고, 채택률과 채택 결과(JSON·CSV)를 내려받는다. 원고 본문은 고치지 않는다. 계산은 서버(ncs_suggest)가 한다.
// AI에는 문장의 자리와 앞뒤 문장(문맥)을 함께 보내고, 서버에 참고 문장 묶음(기존 학습모듈, 공공저작물)이 있으면 후보마다 근거 문장이 붙는다.
// '정정 후보 문장표(CSV)'는 요구사항 산출물인 원본 문장과 정정 후보 1~5순위(근거 문장 포함)의 표다.
// AI는 서버에 LLM 설정이 있으면 자동으로 부른다(체크박스 없음). 없으면 'AI 미설정 — 이유'만 보인다. 후보 출처는 모두 'AI 생성'이다 — 집필자 서약서 고지 대상일 수 있다.
// AI(Claude, ncs_llmreview.claude)는 서버에 ANTHROPIC_API_KEY·반출 승인이 있으면 자동으로 부른다(체크박스 없음). 없으면 'AI 미설정 — 이유'만 보인다. 후보 출처는 모두 'AI 생성'이다 — 집필자 서약서 고지 대상일 수 있다.
import React, { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { Spinner } from "../components/Badge.jsx";
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

function saveFile(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// 채택 기록 → 행 목록(카드마다 한 행). 채택이면 고른 후보의 순위·출처·문장과 AI 고지(집필자 서약서 F09 '활용 AI')에 쓸
// 모델 이름·채택 일시를 적는다. 쪽 번호는 결과에 없어 구성·자리로 대신한다.
function decisionRows(cards, decisions) {
  return cards.map((card) => {
    const decision = decisions[card.key];
    const chosen = decision?.rank ? card.후보.find((c) => c.순위 === decision.rank) : null;
    return {
      번호: card.key, 원고: card.원고명 || "", 구성: card.구성, 자리: card.자리, 종류: card.종류, 원문: card.원문,
      결정: decision?.choice || "미정", "채택 순위": chosen?.순위 ?? "", "채택 출처": chosen?.출처 ?? "", "채택 문장": chosen?.문장 ?? "",
      "활용 AI": chosen?.모델 ?? "", "채택 일시": chosen ? decision.at : "",
      "후보 수": card.후보.length,
    };
  });
}

const MAX_CANDIDATES = 5; // 서버 ncs_suggest.config.max_candidates

// 근거 문장 한 칸 글(서버 ncs_suggest.pipeline.basis_text와 같은 꼴)
function basisText(basis) {
  if (!basis) return "";
  const place = [basis.출처, basis.자리].filter(Boolean).join(", ");
  return `「${basis.문장}」 (${place ? `${place}, ` : ""}유사도 ${basis.유사도})`;
}

// 문장 정정 필요 후보문장표: 카드마다 한 행. 원본 문장 옆에 정정 후보 1~5순위와 후보별 근거 문장, 집필자의 결정을 둔다.
// 앞쪽 열은 서버 ncs_suggest.pipeline.table_columns와 같고, 화면에서 고른 결정 열을 뒤에 더한다.
function candidateRows(cards, decisions) {
  return cards.map((card) => {
    const decision = decisions[card.key];
    const prefix = card["앞 번호"] ? `${card["앞 번호"]} ` : "";
    const row = {
      번호: card.key, 원고: card.원고명 || "", 구성: card.구성, 자리: card.자리, 종류: card.종류, "규정 꼴": card["규정 꼴"],
      "변경 필요 원본 문장": card.원문, "사유 유형": card.상태, 사유: card.사유.join(" / "),
    };
    for (let rank = 1; rank <= MAX_CANDIDATES; rank += 1) {
      const item = card.후보.find((c) => c.순위 === rank);
      row[`정정 후보 ${rank}순위`] = item ? prefix + item.문장 : "";
      row[`근거 문장 ${rank}순위`] = item ? basisText(item["근거 문장"]) : "";
    }
    const chosen = decision?.rank ? card.후보.find((c) => c.순위 === decision.rank) : null;
    row.비고 = card["추천 없음"] || "";
    row.결정 = decision?.choice || "미정";
    row["채택 순위"] = chosen?.순위 ?? "";
    row["채택 문장"] = chosen ? prefix + chosen.문장 : "";
    return row;
  });
}

// 지금 시각을 로컬 시각 ISO 문자열로('2026-11-23T14:05:09+09:00').
function localIso(date = new Date()) {
  const pad = (n) => String(Math.trunc(Math.abs(n))).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    + `${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
}

function toCsv(rows) {
  if (!rows.length) return "";
  const head = Object.keys(rows[0]);
  const cell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return "﻿" + [head.map(cell).join(","), ...rows.map((row) => head.map((key) => cell(row[key])).join(","))].join("\r\n");
}

export default function SuggestPage() {
  usePageTitle("문장 추천");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [kinds, setKinds] = useState([]);
  const [kind, setKind] = useState("교수 방법");
  const [text, setText] = useState("");
  const [typed, setTyped] = useState([]);          // 직접 입력해 받은 카드들(최근 것이 위)
  const [typing, setTyping] = useState(false);
  const [typedError, setTypedError] = useState(null);
  const [decisions, setDecisions] = useState({}); // 카드 key → { choice: '채택'|'기각', rank }
  const aborter = useRef(null);

  useEffect(() => {
    api.suggest.kinds().then(({ ok, data }) => { if (ok) setKinds(data.종류); });
  }, []);

  async function submit(e) {
    e.preventDefault();
    if (!file) return;
    aborter.current = new AbortController();
    setBusy(true);
    setError(null);
    const { ok, data, error: message, aborted } = await api.suggest.manuscript({ file, signal: aborter.current.signal });
    setBusy(false);
    if (aborted) return;
    if (!ok) { setError(message); setResult(null); return; }
    setResult(data);
    setDecisions((old) => Object.fromEntries(Object.entries(old).filter(([key]) => key.startsWith("입력"))));
  }

  async function submitSentence(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setTyping(true);
    setTypedError(null);
    const { ok, data, error: message } = await api.suggest.sentence({ text, kind });
    setTyping(false);
    if (!ok) { setTypedError(message); return; }
    setTyped((old) => [{ ...data, key: `입력-${old.length + 1}`, 원고명: "직접 입력" }, ...old]);
  }

  const manuscriptCards = useMemo(
    () => (result ? result.구성.flatMap((part) => part.문장.map((card) => ({ ...card, key: card.번호, 원고명: result.원고 }))) : []),
    [result],
  );
  const allCards = [...manuscriptCards, ...typed.filter((card) => card.후보.length)];
  const grounded = allCards.reduce((sum, card) => sum + card.후보.filter((item) => item["근거 문장"]).length, 0);
  const decided = allCards.filter((card) => decisions[card.key]);
  const adopted = decided.filter((card) => decisions[card.key].choice === "채택");
  const rate = decided.length ? Math.round((adopted.length / decided.length) * 1000) / 10 : null;

  function decide(card, choice, rank = null) {
    setDecisions((old) => {
      const same = old[card.key]?.choice === choice && old[card.key]?.rank === rank;
      const next = { ...old };
      if (same) delete next[card.key]; else next[card.key] = { choice, rank, at: localIso() };
      return next;
    });
  }

  function download(kindOfFile) {
    const rows = decisionRows(allCards, decisions);
    const stamp = new Date().toISOString().slice(0, 19).replaceAll(":", "");
    const base = `문장추천_채택기록_${stamp}`;
    if (kindOfFile === "table") saveFile(toCsv(candidateRows(allCards, decisions)), `문장추천_정정후보문장표_${stamp}.csv`, "text/csv;charset=utf-8");
    else if (kindOfFile === "csv") saveFile(toCsv(rows), `${base}.csv`, "text/csv;charset=utf-8");
    else saveFile(JSON.stringify({ 원고: result?.원고 ?? null, 채택률: rate, 채택: adopted.length, 결정: decided.length, 카드: allCards.length, 기록: rows }, null, 2),
      `${base}.json`, "application/json");
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page suggest-page">
      <h1 className="page-title">문장 추천</h1>
      {/* 설명은 다른 화면처럼 '무엇을 올리면 무엇이 나오는지 → 무엇을 보는지 → 할 일 → 하지 않는 일 → 파일 처리' 순서로 짧게 쓴다.
          후보를 거르는 방법, 근거 문장, 버린 후보 같은 세부는 결과 화면에서 그 자리에 보인다 */}
      <p className="page-desc">
        원고(hwp, hwpx)를 올리면 생성형 AI가 학습모듈 작성 규칙(문장의 끝맺음)과 표현(군더더기 주어, 어색한 낱말, 중복, 문장부호)에 어긋난 문장을 찾아,
        문장마다 정정 후보를 최대 5개 보여 줍니다. 후보 중 하나를 채택하거나 기각하세요.
        문장만 다듬으며 내용이 적절한지는 판단하지 않고, 원고 파일도 고치지 않습니다. 올린 파일은 계산 뒤 바로 지웁니다.
      </p>

      {/* 칸이 하나라 구획 제목 없이 3열 격자와 실행 줄만 쓴다(다른 화면의 입력 묶음과 같은 열·폭) */}
      <form className="fieldset review-form is-sectioned" onSubmit={submit}>
        <div className="form-section-grid">
        <FileSlot id="suggest-file" label="원고" required accept=".hwp,.hwpx" file={file} onChange={setFile} disabled={busy}
                  hint="hwp, hwpx. hwpx면 수행 순서 번호를 더 정확히 찾습니다." />
        </div>
        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !file}>{busy ? "찾는 중" : "문장 추천"}</button>
            {busy && <button className="krds-btn tertiary large" type="button" onClick={() => aborter.current?.abort()}>취소</button>}
          </div>
          <PageAlert kind="danger">{error}</PageAlert>
        </div>
      </form>

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
        <div className="form-group form-actions">
          <div className="form-tit form-tit-spacer" aria-hidden="true"><label>&nbsp;</label></div>
          <div className="run-buttons">
            <button className="krds-btn secondary large" type="submit" disabled={typing || !text.trim()}>{typing ? "찾는 중" : "이 문장 추천받기"}</button>
          </div>
          <PageAlert kind="danger">{typedError}</PageAlert>
        </div>
      </form>
      {typed.map((card) => <SuggestCard key={card.key} card={card} decision={decisions[card.key]} onDecide={decide} />)}

      {busy && <ResultHead status={<Spinner label="생성형 AI가 문장을 살피는 중" />} />}
      {result && !busy && (
        <SuggestResult result={result} cards={manuscriptCards} decisions={decisions} onDecide={decide} />
      )}

      {allCards.length > 0 && (
        <section className="suggest-tally" aria-live="polite">
          <h2 className="section-title">채택 기록</h2>
          <dl className="upscale-summary">
            <div><dt>후보가 있는 문장</dt><dd>{allCards.length}개</dd></div>
            <div><dt>결정</dt><dd>{decided.length}개 (채택 {adopted.length}, 기각 {decided.length - adopted.length})</dd></div>
            <div><dt>채택률</dt><dd><strong>{rate == null ? "-" : `${rate}%`}</strong></dd></div>
            <div><dt>근거 문장이 있는 후보</dt><dd>{grounded}개</dd></div>
          </dl>
          <div className="run-buttons">
            <button className="krds-btn secondary medium" type="button" onClick={() => download("table")}>정정 후보 문장표(CSV)</button>
            <button className="krds-btn tertiary medium" type="button" onClick={() => download("json")}>채택 기록 내려받기(JSON)</button>
            <button className="krds-btn tertiary medium" type="button" onClick={() => download("csv")}>채택 기록 표(CSV)</button>
          </div>
        </section>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function SuggestResult({ result, cards, decisions, onDecide }) {
  const summary = result.요약;
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
      {result.구성.map((part) => (
        <div key={part.구성}>
          <h2 className="section-title">{part.구성} <span className="meta">({part.문장.length})</span></h2>
          {part.문장.map((card) => {
            const keyed = cards.find((c) => c.번호 === card.번호);
            return <SuggestCard key={card.번호} card={keyed} decision={decisions[keyed.key]} onDecide={onDecide} />;
          })}
        </div>
      ))}
      <h2 className="section-title">가정</h2>
      <ul className="krds-info-list dash">
        {Object.entries(result.가정).map(([key, value]) => <li key={key}>{key}: {value}</li>)}
      </ul>
      <RawJson data={result} title="원본 데이터 보기(개발자용)" />
    </section>
  );
}

function SuggestCard({ card, decision, onDecide }) {
  return (
    <article className="suggest-card">
      <header className="suggest-card-head">
        <span className={`krds-badge ${STATUS_BADGE[card.상태] || "bg-light-gray"}`}>{card.상태}</span>
        <strong>{card.자리}</strong>
        <span className="meta">{card.종류}, 규정 꼴 {card["규정 꼴"]}</span>
      </header>
      <p className="suggest-original"><span className="meta">원문</span> {card.원문}</p>
      {card.사유.length > 0 && <p className="meta">사유: {card.사유.join(" / ")}</p>}
      {card.후보.length > 0 ? (
        <fieldset className="suggest-candidates">
          <legend className="sr-only">{card.자리} 정정 후보</legend>
          <ol>
            {card.후보.map((item) => {
              const chosen = decision?.choice === "채택" && decision.rank === item.순위;
              return (
                <li key={item.순위} className={chosen ? "chosen" : ""}>
                  <span className="rank">{item.순위}</span>
                  <div className="candidate-body">
                    <p className="candidate-text">{card["앞 번호"] ? `${card["앞 번호"]} ` : ""}{item.문장}</p>
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
                  <button type="button" className={`krds-btn small ${chosen ? "primary" : "secondary"}`} aria-pressed={chosen}
                          onClick={() => onDecide(card, "채택", item.순위)}>{chosen ? "채택함" : "채택"}</button>
                </li>
              );
            })}
          </ol>
          <button type="button" className={`krds-btn small ${decision?.choice === "기각" ? "primary" : "tertiary"}`} aria-pressed={decision?.choice === "기각"}
                  onClick={() => onDecide(card, "기각")}>{decision?.choice === "기각" ? "모두 기각함" : "모두 기각"}</button>
        </fieldset>
      ) : (
        <p className="suggest-none">{card["추천 없음"] || (card.상태 === "지적 없음" ? "생성형 AI가 고칠 곳을 찾지 못했습니다." : card.상태 === "판단불가" ? "생성형 AI를 쓸 수 없어 고칠 곳을 찾지 못했습니다(판단불가)." : "추천 없음")}</p>
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
