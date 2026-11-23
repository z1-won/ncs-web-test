import React, { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import { plainReason } from "../lib/plain.js";
import { Spinner } from "./Badge.jsx";
import { PageAlert } from "./PageAlert.jsx";
import { Thumb, placeText } from "./FiguresPanel.jsx";
import { KrdsSelect } from "./KrdsSelect.jsx";

// 그림 판독(Claude): 유형·설명·글자·키워드·맥락 요약 + ③ 캡션 일치. 누를 때만 실행.
const LIMITS = [{ value: "0", label: "전부 (그림당 약 $0.017)" },
  ...[3, 5, 10, 20].map((n) => ({ value: String(n), label: `앞에서 ${n}장 (약 $${(n * 0.017).toFixed(2)})` }))];
const VERDICT = { match: ["일치", "bg-light-success"], mismatch: ["다를 수 있음", "bg-light-warning"], uncertain: ["판단 근거 부족", "bg-light-gray"] };

// 버튼 줄 — 이전 판독 결과도 불러와 onResult로 넘긴다
export function FigureReadBar({ uploadToken, onResult, onDone }) {
  const [status, setStatus] = useState(null);
  const [limit, setLimit] = useState("0");
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.figures.visionStatus().then(({ ok, data, error: message }) => (ok ? setStatus(data) : setError(message)));
  }, []);

  useEffect(() => {
    onResult(null);
    setDone(false);
    if (!uploadToken) return;
    api.figures.previousRead(uploadToken).then(({ ok, data }) => { if (ok) { onResult(data); setDone(true); } });
  }, [uploadToken]); // eslint-disable-line react-hooks/exhaustive-deps

  async function run() {
    setRunning(true);
    setError(null);
    const { ok, data, error: message } = await api.figures.read(uploadToken, { limit });
    if (ok) {
      onResult(data);
      setDone(true);
      if (onDone) onDone();     // 그림 검수표가 ③ 판정을 넣어 위험도를 다시 정한다
    } else setError(message);
    setRunning(false);
  }

  const disabledWhy = !uploadToken ? "원고를 올리고 검수를 먼저 실행하세요" : status && !status.available ? plainReason(status.problem) : null;
  const blocked = status && status.transfer_others !== "허용";

  return (
    <div className="fig-read-bar">
      <b>그림 판독(Claude · 비용 발생)</b>
      <div className="fig-limit"><KrdsSelect id="fig-read-limit" value={limit} options={LIMITS} onChange={setLimit} title="판독할 그림 수" /></div>
      <button type="button" className="krds-btn primary small" onClick={run} disabled={running || Boolean(disabledWhy)}>
        {running ? "그림 판독 중…" : done ? "다시 판독" : "그림 판독"}
      </button>
      {running && <Spinner label="그림 1장에 5~10초" />}
      {disabledWhy && !running && <span className="form-hint">{disabledWhy}</span>}
      {blocked && <span className="form-hint">남이 만든 그림은 외부로 보내지 않도록 설정되어 있어 판독하지 않습니다</span>}
      {error && <PageAlert kind="danger">{error}</PageAlert>}
    </div>
  );
}

// 판독 결과 표 — 그림 검수 칸의 '그림 판독' 탭
export function FigureReadResults({ uploadToken, result }) {
  if (!result) return <p className="empty">그림 판독 전</p>;
  return (
    <div className="llm-result">
      <p className="meta">
        본문 그림 {result["본문 그림"]}장 중 {result["판독한 그림"]}장 · 보냄 {result.합계.보냄} · 보내지 않음 {result.합계["보내지 않음"]}
        {" "}· 새 호출 {result.합계["새 호출"]}{result.합계["새 호출"] ? ` · 약 $${result.합계.비용}` : " · 새 비용 없음"}
        {result.합계.실패 ? ` · 실패 ${result.합계.실패}` : ""} · {result.model} · {result.seconds}초
      </p>
      <div className="krds-table-wrap">
        <table className="tbl col data fig-table">
          <caption className="sr-only">그림 판독 결과</caption>
          <thead>
            <tr><th scope="col">그림</th><th scope="col">캡션·위치</th><th scope="col">판독</th><th scope="col">③ 캡션 일치</th></tr>
          </thead>
          <tbody>
            {result.figures.map((f, i) => {
              const r = f.판독;
              const c = f["캡션 판정"];
              const [label, badge] = VERDICT[c.판정] || [];
              return (
                <tr key={`${f.image_id}-${i}`}>
                  <td className="thumb-cell"><Thumb token={uploadToken} id={f.image_id} alt={f.캡션} /></td>
                  <td>{f.캡션 || <span className="sub">캡션 없음</span>}<div className="sub">{placeText(f.위치)}</div></td>
                  <td>
                    {r.status === "완료" ? (
                      <>
                        <b>{r.유형}</b> — {r.설명}
                        <div className="sub">그림 속 글자: {(r["그림 속 글자"] || []).join(", ") || "없음"}</div>
                        <div className="sub">키워드: {(r.키워드 || []).join(", ")}</div>
                        <div className="sub">맥락 요약: {r["맥락 요약"] || "주어진 글에 근거 없음"}</div>
                        {r.problems?.length > 0 && <div className="sub">확인: {r.problems.join(", ")}</div>}
                      </>
                    ) : (
                      <span className="sub">{r.status === "미실행" ? "보내지 않음" : r.status} — {plainReason(r.reason || f.전송?.이유)}</span>
                    )}
                  </td>
                  <td>
                    {c.status === "완료" ? (
                      <>
                        <span className={`krds-badge ${badge}`}>{label}</span>
                        <div>{c.근거}</div>
                        {c.검증 !== "통과" && <div className="sub">검증: {c.검증}</div>}
                      </>
                    ) : <span className="sub">{plainReason(c.reason) || c.status}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
