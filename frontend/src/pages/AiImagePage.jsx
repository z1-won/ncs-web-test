// 이미지 AI 보완(REQ-02-006) — AI로 만들거나 고친 그림의 표기와 현황을 맡는다.
//   ⑤ 유의 안내를 확인하고 → 원고의 그림을 읽어 → ③ AI를 쓴 그림에 활용 줄('OO를 활용하여 생성함/수정 보완함. 일자')을 넣은 원고 사본을 받고
//   → ④ 서약서에 붙일 생성형 AI 결과물 현황(xlsx)을 받는다. 화질 보정(②)은 업스케일링 화면에서 하고, 제안본을 만들 때 표기를 함께 넣는다.
// 그림을 AI로 새로 만드는 일(①)은 이 화면에 없다. 서버는 올린 파일을 읽는 동안만 두고 지운다(ncs_web.routes.aiimage).
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { Spinner } from "../components/Badge.jsx";
import { FileSlot } from "../components/FileSlot.jsx";
import { KrdsDateField } from "../components/KrdsDateField.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { ResultHead } from "../components/ResultHead.jsx";
import { usePageTitle } from "../lib/hooks.js";

const MODE_OPTIONS = [
  { value: "modified", label: "수정 보완함 (있던 그림을 고치거나 보정)" },
  { value: "generated", label: "생성함 (AI로 새로 만듦)" },
];
const MODE_WORD = { modified: "수정 보완함", generated: "생성함" };
const stem = (name) => (name || "원고").replace(/\.[^.]+$/, "");

export default function AiImagePage() {
  usePageTitle("이미지 AI 보완");
  const [notice, setNotice] = useState(null);          // { 근거, 항목: [{제목, 내용}] }
  const [agreed, setAgreed] = useState(false);
  const [manuscript, setManuscript] = useState(null);
  const [printCopy, setPrintCopy] = useState(null);
  const [busy, setBusy] = useState(null);              // "read" | "preview" | "marked" | "results"
  const [error, setError] = useState(null);
  const [done, setDone] = useState(null);              // 내려받기 뒤의 안내
  const [data, setData] = useState(null);              // 그림 목록(서버 inspect)
  const [picked, setPicked] = useState(() => new Set());
  const [tool, setTool] = useState("");
  const [mode, setMode] = useState("modified");
  const [day, setDay] = useState("");
  const [shown, setShown] = useState(null);            // 미리 보기(서버 preview)

  useEffect(() => { api.aiImage.notice().then(({ ok, data: body }) => { if (ok) setNotice(body); }); }, []);
  // 파일을 바꾸면 앞 결과는 그 파일의 것이 아니다
  useEffect(() => { setData(null); setShown(null); setPicked(new Set()); setError(null); setDone(null); }, [manuscript, printCopy]);
  useEffect(() => { setShown(null); setDone(null); }, [picked, tool, mode, day]);

  const marks = useMemo(() => (data ? data.그림.filter((row) => picked.has(row.key)).map((row) => ({ key: row.key, tool: tool.trim(), mode, date: day })) : []),
    [data, picked, tool, mode, day]);
  const open = data ? data.그림.filter((row) => !row["AI 표기"]) : [];
  const marksReady = marks.length > 0 && tool.trim() && day;
  const hasResults = data && (data.요약["AI 표기 있음"] > 0 || marksReady);

  async function read(e) {
    e.preventDefault();
    if (!manuscript) return;
    setBusy("read");
    setError(null);
    const { ok, data: body, error: message } = await api.aiImage.figures(manuscript, printCopy);
    setBusy(null);
    if (!ok) { setError(message); setData(null); return; }
    setData(body);
    setDay((current) => current || body.오늘);
  }

  async function act(kind) {
    setBusy(kind);
    setError(null);
    setDone(null);
    const sending = marksReady ? marks : [];
    if (kind === "preview") {
      const { ok, data: body, error: message } = await api.aiImage.preview(manuscript, printCopy, sending);
      setBusy(null);
      if (!ok) { setError(message); return; }
      setShown(body);
      return;
    }
    const { ok, error: message, summary } = kind === "marked"
      ? await api.aiImage.marked(manuscript, sending, `${stem(manuscript.name)}_AI표기.hwpx`)
      : await api.aiImage.results(manuscript, printCopy, sending, `${stem(manuscript.name)}_생성형AI결과물현황.xlsx`);
    setBusy(null);
    if (!ok) { setError(message); return; }
    if (kind === "marked") {
      setDone(`그림 ${summary?.넣음 ?? marks.length}개에 AI 활용 줄을 넣은 원고 사본을 내려받았습니다. 넣은 줄 ${summary?.["다시 읽기"] ?? 0}개를 다시 읽어 같은 값인지 확인했습니다. 한글에서 열어 글자 모양을 확인해 주세요.`);
    } else {
      setDone(`결과물 ${summary?.현황 ?? ""}건을 적은 현황표를 내려받았습니다. 서약서의 생성형 AI 결과물 현황에 옮겨 적어 주세요.`);
    }
  }

  function toggle(key) {
    setPicked((prev) => { const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  }

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page ai-image-page">
      <h1 className="page-title">이미지 AI 보완</h1>
      <p className="page-desc">
        생성형 AI로 만들거나 고친 그림에 <strong>AI 활용 표기</strong>를 넣고, 서약서에 붙일 <strong>생성형 AI 결과물 현황</strong>을 만듭니다.
        원고를 올리면 그림마다 출처 줄과 AI 활용 줄이 있는지 보여 줍니다. 표기를 넣은 원고는 사본으로 내려받고, 올린 원고는 바뀌지 않습니다.
        올린 파일은 읽은 뒤 바로 지웁니다.
      </p>
      <p className="page-desc">
        그림의 화질을 높이는 보정은 <Link to="/upscale">업스케일링</Link>에서 합니다. 거기서 제안본을 만들 때 보정한 그림에 표기를 함께 넣을 수 있습니다.
        문단을 바탕으로 도표와 표를 새로 만드는 일은 <Link to="/ai-generate">이미지 AI 생성</Link>에서 합니다.
      </p>

      <section className="ai-notice" aria-labelledby="ai-notice-title">
        <h2 className="section-title" id="ai-notice-title">AI를 쓰기 전에 확인할 것</h2>
        {notice ? (
          <>
            <ol className="ai-notice-list">
              {notice.항목.map((item) => <li key={item.제목}><strong>{item.제목}</strong><span>{item.내용}</span></li>)}
            </ol>
            <p className="meta">근거: {notice.근거}</p>
          </>
        ) : <p className="meta">안내를 불러오는 중입니다.</p>}
        <div className="krds-form-check">
          <input type="checkbox" id="ai-agreed" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <label htmlFor="ai-agreed">위 내용을 확인했습니다</label>
        </div>
      </section>

      <form className="fieldset review-form is-sectioned" onSubmit={read}>
        <div className="form-section" role="group" aria-labelledby="ai-files-title">
        <h2 className="form-section-title" id="ai-files-title">원고</h2>
        <div className="form-section-grid">
        <FileSlot id="ai-manuscript" label="원고" required accept=".hwp,.hwpx" file={manuscript} onChange={setManuscript} disabled={!!busy}
                  hint="hwp, hwpx. 표기를 넣은 사본은 hwpx 원고에서만 만듭니다." />
        <FileSlot id="ai-print" label="출력본 PDF" accept=".pdf" file={printCopy} onChange={setPrintCopy} disabled={!!busy}
                  hint="pdf. 올리면 현황표에 그림이 실린 쪽을 적습니다." />
        </div>
        </div>
        <div className="form-actions">
          <div className="run-buttons">
            <button className="krds-btn primary large" type="submit" disabled={!!busy || !manuscript}>{busy === "read" ? "읽는 중" : "그림 읽기"}</button>
          </div>
          {!data && <PageAlert kind="danger">{error}</PageAlert>}
        </div>
      </form>

      {busy === "read" && <ResultHead status={<Spinner label="원고의 그림과 표기를 읽는 중" />} />}
      {data && busy !== "read" && (
        <section className="ai-result">
          <ResultHead status={<span className="krds-badge large bg-light-gray">그림 {data.요약.그림}개</span>}
                      meta={`${data.원고}${data.출력본 ? ` / 출력본 ${data.출력본}` : ""}`} />
          <dl className="upscale-summary">
            <div><dt>AI 활용 표기가 있는 그림</dt><dd><strong>{data.요약["AI 표기 있음"]}</strong>개</dd></div>
            <div><dt>표기가 없는 그림</dt><dd><strong>{open.length}</strong>개</dd><dd className="meta">AI를 쓴 그림만 골라 표기를 넣습니다</dd></div>
            <div><dt>출처 줄이 없는 그림</dt><dd><strong>{data.요약["출처 줄 없음"]}</strong>개</dd><dd className="meta">출처 줄은 넣어 드리지 않습니다. 원고에 직접 적어 주세요</dd></div>
          </dl>
          {data.알림.length > 0 && <PageAlert kind="info">{data.알림.map((text) => <p key={text}>{text}</p>)}</PageAlert>}

          <h2 className="section-title">넣을 표기</h2>
          <p className="meta section-desc">아래 표에서 고른 그림 모두에 같은 도구, 방식, 일자를 적습니다. 도구가 다르면 한 번 받은 사본을 다시 올려 나눠 넣어 주세요.</p>
          <div className="fieldset review-form ai-mark-form">
            <div className="form-section-grid">
              <div className="form-group">
                <div className="form-tit"><label htmlFor="ai-tool">활용한 AI 도구</label></div>
                <div className="form-conts">
                  <input id="ai-tool" type="text" className="krds-input" maxLength={40} value={tool} placeholder="예: ChatGPT" onChange={(e) => setTool(e.target.value)} />
                </div>
                <p className="form-hint">서비스 이름을 적습니다. 판 번호(예: 6.0)는 붙여도 됩니다.</p>
              </div>
              <div className="form-group">
                <div className="form-tit"><label htmlFor="ai-mode">활용 방식</label></div>
                <div className="form-conts">
                  <KrdsSelect id="ai-mode" value={mode} options={MODE_OPTIONS} onChange={setMode} title="활용 방식 선택" />
                </div>
              </div>
              <KrdsDateField id="ai-day" label="활용 일자" value={day} onChange={setDay} hint="AI를 쓴 날짜입니다." />
            </div>
          </div>

          <div className="krds-table-wrap">
            <table className="tbl col data ai-figure-table">
              <caption>원고의 그림과 AI 활용 표기</caption>
              <thead>
                <tr><th scope="col">선택</th><th scope="col">그림</th><th scope="col">출처 줄</th><th scope="col">AI 활용 표기</th>{data.출력본 && <th scope="col">쪽</th>}</tr>
              </thead>
              <tbody>
                {data.그림.map((row) => (
                  <tr key={row.key} className={picked.has(row.key) ? "is-open" : undefined}>
                    <td>
                      <div className="krds-form-check">
                        <input type="checkbox" id={`ai-pick-${row.key}`} checked={picked.has(row.key)} disabled={!!row["AI 표기"] || !data["표기 넣기"] || !!row.공공누리?.변경금지}
                               onChange={() => toggle(row.key)} />
                        <label htmlFor={`ai-pick-${row.key}`}><span className="sr-only">{row["그림 번호"]} {row.그림명} 고르기</span></label>
                      </div>
                    </td>
                    <th scope="row">[{row["그림 번호"]}]<span className="meta">{row.그림명}</span></th>
                    <td>
                      {row["출처 줄"] || <span className="krds-badge bg-light-warning">출처 줄 없음</span>}
                      {/* 변경금지 원본은 AI 수정 보완·생성의 재료가 아니다(REQ-02-006 ⑥) — 고를 수 없게 하고 이유를 보인다 */}
                      {row.공공누리?.변경금지 && <><br /><span className="krds-badge bg-light-danger">변경금지 원본</span> <span className="meta">AI 활용 표기 대상에서 제외</span></>}
                      {row.공공누리 && !row.공공누리.변경금지 && row.공공누리.비상업 && <><br /><span className="krds-badge bg-light-warning">비상업 원본</span> <span className="meta">결과물에 비상업 조건 표시</span></>}
                    </td>
                    <td>
                      {row["AI 표기"]
                        ? <><span className="krds-badge bg-light-success">표기 있음</span> <span className="ai-line">{row["AI 표기"].글}</span></>
                        : picked.has(row.key) && tool.trim() && day
                          ? <><span className="krds-badge bg-light-information">넣을 표기</span> <span className="ai-line">{tool.trim()}, {MODE_WORD[mode]}, {day.replaceAll("-", ". ")}.</span></>
                          : <span className="meta">없음</span>}
                    </td>
                    {data.출력본 && <td>{row.쪽.length ? row.쪽.map((p) => `p.${p}`).join(", ") : "-"}</td>}
                  </tr>
                ))}
                {data.그림.length === 0 && <tr><td colSpan={data.출력본 ? 5 : 4} className="empty">원고에서 그림 캡션([그림 1-1] 그림명)을 찾지 못했습니다.</td></tr>}
              </tbody>
            </table>
          </div>

          <div className="upscale-bar">
            {error && <PageAlert kind="danger">{error}</PageAlert>}
            {done && !error && <PageAlert kind="success">{done}</PageAlert>}
            {!agreed && <PageAlert kind="warning">위의 ‘AI를 쓰기 전에 확인할 것’을 확인해 주세요. 확인해야 내려받을 수 있습니다.</PageAlert>}
            <div className="bar-row">
              <span className="meta" role="status">고른 그림 <strong>{picked.size}</strong>개{marks.length > 0 && !marksReady ? ". 도구와 일자를 적어 주세요" : ""}</span>
              <div className="bar-actions">
                <button type="button" className="krds-btn medium tertiary" disabled={!!busy || !hasResults} onClick={() => act("preview")}>
                  {busy === "preview" ? "만드는 중" : "미리 보기"}
                </button>
                <button type="button" className="krds-btn medium secondary" disabled={!!busy || !agreed || !hasResults} onClick={() => act("results")}
                        title="서약서 붙임 양식의 칸(순번, 결과물 명, 학습모듈 해당 쪽수, 활용 AI, 비고)으로 만든 엑셀 파일">
                  {busy === "results" ? "만드는 중" : "결과물 현황 내려받기"}
                </button>
                <button type="button" className="krds-btn medium primary" disabled={!!busy || !agreed || !marksReady || !data["표기 넣기"]} onClick={() => act("marked")}
                        title="고른 그림의 캡션 위에 AI 활용 줄을 넣은 원고 사본(hwpx). 다른 글은 그대로입니다">
                  {busy === "marked" ? "만드는 중" : `표기 넣은 원고 내려받기(그림 ${marksReady ? marks.length : 0}개)`}
                </button>
              </div>
            </div>
          </div>

          {shown && <Preview shown={shown} />}
        </section>
      )}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}

function Preview({ shown }) {
  return (
    <section className="ai-preview" aria-labelledby="ai-preview-title">
      <h2 className="section-title" id="ai-preview-title">미리 보기</h2>
      {shown.알림.length > 0 && <PageAlert kind="info">{shown.알림.map((text) => <p key={text}>{text}</p>)}</PageAlert>}
      {(shown["변경금지 원본 제외"] || []).length > 0 && (
        <PageAlert kind="warning">{shown["변경금지 원본 제외"].map((item) => <p key={item.그림}>[{item.그림}] {item.이유}</p>)}</PageAlert>
      )}
      {shown.표기.length > 0 && (
        <>
          <h3 className="ai-sub-title">그림 아래에 놓일 표기</h3>
          <ul className="ai-lines">
            {shown.표기.map((item) => (
              <li key={item.key}>
                {item.줄.map((line, i) => <code key={i} className={i === item.줄.length - 2 ? "is-new" : undefined}>{line}</code>)}
                {item["출처 줄 없음"] && <span className="krds-badge bg-light-warning">출처 줄 없음</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      <h3 className="ai-sub-title">생성형 AI 결과물 현황</h3>
      {shown.현황.length === 0 ? <p className="empty">AI 활용 표기가 있는 그림이 없습니다.</p> : (
        <div className="krds-table-wrap">
          <table className="tbl col data ai-results-table">
            <caption>서약서 붙임 양식의 칸으로 만든 생성형 AI 결과물 현황</caption>
            <thead><tr>{shown["현황 머리"].map((name) => <th scope="col" key={name}>{name}</th>)}</tr></thead>
            <tbody>
              {shown.현황.map((row) => (
                <tr key={row.key}>{shown["현황 머리"].map((name) => <td key={name}>{row[name] === "" ? "-" : row[name]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!shown.쪽수 && shown.현황.length > 0 && <p className="form-hint">쪽수는 비어 있습니다. 출력본 PDF를 함께 올리면 채워집니다.</p>}
    </section>
  );
}
