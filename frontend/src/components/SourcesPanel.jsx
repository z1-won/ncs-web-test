import React, { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";

// 표 출처 검토(REQ-02-008) — 체크리스트(F02 검수 확인서)에 없는 것만 보인다. 형식 검수 결과가 나오면 바로(API 비용 없음).
//   그림 출처            → 그림 검수 표
//   표 출처 있음·F14 형식·옛 기관명 → 검수 결과 › 필요 지식 ⑧ (같은 규칙이라 여기선 빼고 계약서 제4조 요건·AI 표기만)
//   참고 자료            → 검수 결과 › 참고 자료 ①~④ (같은 엔진이라 여기선 뺌)
// 출처 목록 CSV에는 전부(그림·표·본문, 모든 점검) 들어 있다.

const OX = { O: "O", X: "X", "△": "확인 필요" };
// 그림 출처는 그림 검수 표에서 본다(같은 함수로 같은 출처 줄을 읽음 — 두 번 보이지 않게). CSV에는 그림 출처도 들어 있다.
const GROUPS = [["표", "표 출처"], ["본문", "본문 출처 줄(어문 자료)"]];
// 필요 지식 ⑧이 이미 보는 점검 — 표에서는 보이지 않는다(본문 출처 줄은 ⑧이 형식을 안 보므로 그대로)
const IN_CHECKLIST = { 표: new Set(["출처 있음", "출처 형식(F14)", "기관 명칭"]), 본문: new Set(["출처 있음"]) };  // 본문 출처 줄은 줄이 있어야 잡히므로 '출처 있음'은 늘 O
const shownChecks = (r) => Object.entries(r.체크).filter(([name]) => !IN_CHECKLIST[r.구분]?.has(name));
// 제안 중 F14 형식 고치기는 필요 지식 ⑧ 확인서에 이미 있음 — 표에서는 뺀다
const shownFix = (r) => (r["수정 제안"] || "").split(" / ").filter((f) => f && !(r.구분 === "표" && f.includes("F14"))).join(" / ");

function Line({ label, value, note }) {
  const bad = value === "X" || value === "△";
  if (value === "-" && !note) return null;
  return (
    <div className={`v-line${bad ? " bad" : ""}`}>
      {bad ? <b>{label}: {OX[value]}</b> : <>{label}: {value === "-" ? "해당 없음" : OX[value] || value}</>}
      {(bad || value === "-") && note && <div className="v-note">{note}</div>}
    </div>
  );
}

function SourceInfo({ s }) {
  if (!s) return <span className="sub">—</span>;
  const parts = [
    ["종류", s.종류], ["저작자", s.저작자], ["연도", s.연도], ["URL", s.URL], ["확인 일자", s["확인 일자"]],
    ["쪽", s.쪽 != null ? `p.${s.쪽}` : null], ["공공누리", s.공공누리 ? `제${s.공공누리}유형` : null], ["인용 모듈", s["인용 모듈"]],
  ].filter(([, v]) => v);
  return <div className="src-info">{parts.map(([k, v]) => <div key={k}><span className="k">{k}</span> {v}</div>)}</div>;
}

export function SourcesPanel({ uploadToken, moduleCode }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [onlyIssues, setOnlyIssues] = useState(true);

  useEffect(() => {
    setData(null);
    setError(null);
    if (!uploadToken) return;
    const controller = new AbortController();
    setLoading(true);
    api.sources.review(uploadToken, { moduleCode, signal: controller.signal }).then(({ ok, data: body, error: message, aborted }) => {
      if (aborted) return;
      if (ok) setData(body);
      else setError(message);
      setLoading(false);
    });
    return () => controller.abort();
  }, [uploadToken, moduleCode]);

  const s = data?.summary;
  const issue = (r) => shownChecks(r).some(([, v]) => v === "X" || v === "△");
  const relevant = (r) => shownChecks(r).some(([, v]) => v && v !== "-");      // 남은 점검이 모두 해당 없음이면 줄을 만들지 않음

  return (
    <section id="sources" className="figures-panel sources-panel nav-anchor">
      <div className="section-head">
        <h2 className="section-title">표 출처 검토 <span className="fig-tag free">규칙으로만 검토, 비용 없음</span></h2>
      </div>

      {loading && <Spinner label="표 출처 검토 중" />}
      {error && <PageAlert kind="danger">{error}</PageAlert>}

      {data && (
        <>
          <div className="fig-toolbar">
            <div className="krds-form-check">
              <input type="checkbox" id="src-only-issues" checked={onlyIssues} onChange={(e) => setOnlyIssues(e.target.checked)} />
              <label htmlFor="src-only-issues">확인할 것만 보기</label>
            </div>
            <div className="fig-downloads">
              <a className="krds-btn small tertiary" href={api.sources.csvUrl(uploadToken)}>출처 목록(CSV)</a>
            </div>
          </div>

          <p className="fig-sources">
            체크리스트(F02 검수 확인서)에 없는 출처 점검만 보입니다 — 계약서 제4조 필수 요소, 생성형 AI 표기, 본문 출처 줄, 인용 문장.
            그림 출처 {s["그림 출처"]}개는 <a href="#figures">그림 검수</a>, 표 출처가 있는지·F14 형식·옛 기관명은 검수 결과의 필요 지식 ⑧,
            참고 자료는 검수 결과의 참고 자료 ①~④에서 봅니다. 출처 목록 CSV에는 모두 들어 있습니다.
          </p>

          {GROUPS.map(([kind, title]) => {
            const all = data.rows.filter((r) => r.구분 === kind).filter(relevant);
            const rows = onlyIssues ? all.filter(issue) : all;
            if (!all.length) return null;
            return (
              <div key={kind} className="src-group">
                <h3 className="llm-group-title">{title} <span className="count">{rows.length}/{all.length}개</span></h3>
                {!rows.length ? <p className="empty">확인할 것이 없습니다 — {all.length}개 모두 문제없음.</p> : (
                  <div className="krds-table-wrap">
                    <table className="tbl col data fig-table">
                      <caption className="sr-only">{title}</caption>
                      <thead>
                        <tr><th scope="col">위치</th><th scope="col">{kind === "본문" ? "앞 문장" : "표"}</th><th scope="col">출처(원문 그대로)</th><th scope="col">출처에서 읽은 것</th><th scope="col">판정과 근거</th></tr>
                      </thead>
                      <tbody>
                        {rows.map((r, i) => (
                          <tr key={`${r.item_id}-${i}`}>
                            <td>{r.region_path}</td>
                            <td>{kind === "본문" ? <span className="sub">{r["앞 문장"] || "—"}</span> : r["그림·표"]}</td>
                            <td>{r.출처 ? `「${r.원고}」` : <b className="fig-nosrc">출처 줄 없음</b>}
                              {r["AI 표기"] && <div className="sub">AI 활용 줄: 「{r["AI 표기"].원문}」</div>}</td>
                            <td><SourceInfo s={r.출처} /></td>
                            <td className="verdict">
                              <div className="fig-verdict">
                                {shownChecks(r).map(([name, value]) => <Line key={name} label={name} value={value} note={r.비고?.[name]} />)}
                                {shownFix(r) && <div className="v-fix"><b>고칠 것:</b> {shownFix(r)}</div>}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}

          {data.quotes.length > 0 && (
            <div className="src-group">
              <h3 className="llm-group-title">출처 표시 없는 인용 문장 <span className="count">{data.quotes.length}개</span></h3>
              <ul className="quote-list">{data.quotes.map((q) => <li key={q.para}><b>{(q.para + 1).toLocaleString()}번째 문단</b> — {q.text.length > 200 ? `${q.text.slice(0, 200)}…` : q.text}</li>)}</ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
