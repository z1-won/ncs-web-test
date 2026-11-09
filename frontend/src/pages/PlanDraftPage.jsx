// 개발계획서 작성(REQ-02-001) — 세분류를 고르고 능력단위를 체크하면 T01 양식에 NCS 정보를 채운 초안 hwpx를 내려받는다.
// 초안은 서버가 바로 ①~⑩ 점검(ncs_plan)을 돌려 요약을 함께 준다(X-Plan-Check). 요소·수행준거 표(ncs_elements.tsv)에 있는 세분류만 고를 수 있다.
import React, { useEffect, useMemo, useState } from "react";

import { api } from "../lib/api.js";
import { Badge, Spinner } from "../components/Badge.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";

const ANCHORS = [
  { id: "plan-form", label: "초안 만들기" },
  { id: "plan-check", label: "초안 점검" },
];

export default function PlanDraftPage() {
  const [catalog, setCatalog] = useState(null);     // /api/plan/subclasses 응답
  const [loadError, setLoadError] = useState(null);
  const [duty, setDuty] = useState("");
  const [picked, setPicked] = useState({});          // 능력단위 코드 → true
  const [agency, setAgency] = useState("");
  const [english, setEnglish] = useState("");
  const [people, setPeople] = useState({});          // 코드 → { writer, reviewer }
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [check, setCheck] = useState(null);          // 초안 점검 요약 [{번호, 검수결과, 비고}]
  const [made, setMade] = useState(null);            // 마지막으로 만든 세분류·개수

  useEffect(() => {
    api.plan.subclasses().then(({ ok, data, error: message }) => {
      if (!ok) { setLoadError(message); return; }
      setCatalog(data);
      if (data.subclasses?.length) setDuty(data.subclasses[0].duty);
    });
  }, []);

  const subclass = useMemo(() => catalog?.subclasses?.find((s) => s.duty === duty) || null, [catalog, duty]);
  useEffect(() => {   // 세분류를 바꾸면 능력단위는 전부 선택
    if (!subclass) return;
    setPicked(Object.fromEntries(subclass.units.map((u) => [u.code, true])));
    setCheck(null);
  }, [subclass]);

  const options = (catalog?.subclasses || []).map((s) => ({ value: s.duty, label: `${s.name} (${s.duty}) — 능력단위 ${s.units.length}개` }));
  const chosen = subclass ? subclass.units.filter((u) => picked[u.code]) : [];

  async function submit(e) {
    e.preventDefault();
    if (!subclass || !chosen.length) return;
    setBusy(true); setError(null); setCheck(null);
    const writers = {}, reviewers = {};
    chosen.forEach((u) => {
      if (people[u.code]?.writer) writers[u.code] = people[u.code].writer;
      if (people[u.code]?.reviewer) reviewers[u.code] = people[u.code].reviewer;
    });
    const { ok, error: message, check: summary } = await api.plan.draft({
      duty: subclass.duty, units: chosen.map((u) => u.code), agency, english, writers, reviewers,
    });
    setBusy(false);
    if (!ok) { setError(message); return; }
    setCheck(summary);
    setMade({ name: subclass.name, duty: subclass.duty, units: chosen.length, elements: chosen.reduce((n, u) => n + u.elements, 0) });
    setTimeout(() => document.getElementById("plan-check")?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  function setPerson(code, key, value) {
    setPeople((prev) => ({ ...prev, [code]: { ...(prev[code] || {}), [key]: value } }));
  }

  return (
    <>
    <Header anchors={ANCHORS} hasHistory={false} hasResult={!!check} />
    <main id="container" className="inner page">
      <h1 className="page-title">NCS 학습모듈 개발계획서 작성 지원</h1>
      <p className="page-desc">
        세분류를 고르면 NCS 능력단위·요소·수행준거를 개발계획서 양식(T01)에 자동으로 채운 초안(.hwpx)을 내려받습니다.
        학습 내용명·선수학습 등 집필자가 정할 칸은 비워 두며, 초안은 바로 개발계획서 점검 ①~⑩을 거칩니다.
      </p>

      {loadError && <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{loadError}</p>}
      {catalog && !catalog.subclasses?.length && (
        <p className="empty">초안을 만들 수 있는 세분류가 없습니다. 운용 전에 <code>{catalog.build}</code>로 요소·수행준거 표를 받아 두세요.</p>
      )}

      <form id="plan-form" className="fieldset review-form nav-anchor" onSubmit={submit}>
        <div className="form-group">
          <div className="form-tit"><label htmlFor="duty">세분류</label></div>
          <div className="form-conts">
            <KrdsSelect id="duty" value={duty} options={options} onChange={setDuty} title="세분류 선택" describedBy="duty-hint" />
          </div>
          <p className="form-hint" id="duty-hint">
            {subclass ? `${subclass.classes?.대분류 || ""} › ${subclass.classes?.중분류 || ""} › ${subclass.classes?.소분류 || ""} › ${subclass.name}` : "요소·수행준거 표에 받아 둔 세분류만 보입니다"}
          </p>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="agency">개발기관명</label></div>
          <div className="form-conts">
            <input id="agency" type="text" className="krds-input" placeholder="예: (사)한국호텔전문경영인협회" value={agency} onChange={(e) => setAgency(e.target.value)} />
          </div>
        </div>

        <div className="form-group">
          <div className="form-tit"><label htmlFor="english">영문 세분류명</label></div>
          <div className="form-conts">
            <input id="english" type="text" className="krds-input" placeholder="예: Rooms Operation" value={english} onChange={(e) => setEnglish(e.target.value)} />
          </div>
          <p className="form-hint">비우면 ⑧ 필수 기재에서 부적합으로 표시됩니다(NCS 누리집 ‘환경 분석’의 영문명)</p>
        </div>

        {subclass && (
          <div className="form-group form-group-wide">
            <div className="form-tit"><span>능력단위 ({chosen.length}/{subclass.units.length})</span></div>
            <div className="form-conts">
              <table className="krds-table plan-units">
                <thead>
                  <tr><th scope="col">선택</th><th scope="col">능력단위</th><th scope="col">수준</th><th scope="col">요소 / 수행준거</th><th scope="col">담당 집필진</th><th scope="col">담당 검토진</th></tr>
                </thead>
                <tbody>
                  {subclass.units.map((u) => (
                    <tr key={u.code}>
                      <td>
                        <div className="krds-form-check">
                          <input type="checkbox" id={`unit-${u.code}`} checked={!!picked[u.code]} onChange={(e) => setPicked({ ...picked, [u.code]: e.target.checked })} />
                          <label htmlFor={`unit-${u.code}`}><span className="sr-only">{u.name} 선택</span></label>
                        </div>
                      </td>
                      <td><strong>{u.name}</strong><br /><span className="code">{u.code}</span></td>
                      <td>{u.level ?? "-"}</td>
                      <td>{u.elements} / {u.criteria}</td>
                      <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 집필진`} value={people[u.code]?.writer || ""} onChange={(e) => setPerson(u.code, "writer", e.target.value)} /></td>
                      <td><input type="text" className="krds-input small" aria-label={`${u.name} 담당 검토진`} value={people[u.code]?.reviewer || ""} onChange={(e) => setPerson(u.code, "reviewer", e.target.value)} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <div className="form-group form-actions">
          <div className="form-tit form-tit-spacer" aria-hidden="true"><label>&nbsp;</label></div>
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={busy || !chosen.length}>
              {busy ? "만드는 중…" : "초안 만들기 (hwpx 내려받기)"}
            </button>
          </div>
          {error && <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{error}</p>}
        </div>
      </form>

      <div id="plan-check" className="results-anchor nav-anchor" />
      {busy && <p className="empty"><Spinner label="초안을 만들고 점검하는 중" /></p>}
      {!busy && !check && <p className="empty result-placeholder">초안을 만들면 함께 돌린 점검 ①~⑩ 결과가 여기에 표시됩니다.</p>}
      {check && made && (
        <section>
          <h2 className="section-title">초안 점검 — {made.name} ({made.duty}) · 능력단위 {made.units}개 · 요소 {made.elements}개</h2>
          <p className="page-desc">⑦(학습 내용명)은 집필자가 채울 칸이라 판단불가, ⑧은 영문명·집필진·검토진을 비우면 부적합으로 나옵니다. 내려받은 hwpx를 한글에서 열어 이어서 작성하세요.</p>
          <table className="krds-table">
            <thead><tr><th scope="col">번호</th><th scope="col">판정</th><th scope="col">비고</th></tr></thead>
            <tbody>
              {check.map((row) => (
                <tr key={row.번호}>
                  <td>{row.번호}</td>
                  <td><Badge value={row.검수결과} /></td>
                  <td style={{ whiteSpace: "pre-wrap" }}>{row.비고}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
