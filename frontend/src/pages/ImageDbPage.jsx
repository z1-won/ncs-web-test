// 이미지 저작권 DB(REQ-02-010) — 적재(레코드 JSON + 그림 파일) → 목록·상세에서 권리 정보 입력과 기관 확정 → 추천용 조회 확인.
// 서버가 PostgreSQL일 때만 쓸 수 있다(/api/health의 image_db). 허용값의 이름은 서버(/api/images/terms)에서 받는다.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { Spinner } from "../components/Badge.jsx";
import { ImageDetail } from "../components/ImageDetail.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { PageAlert } from "../components/PageAlert.jsx";
import { Pagination } from "../components/Pagination.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { conditionsLabel, licenseLabel, loadName, saveName, statusBadge, termOptions } from "../lib/imageTerms.js";

const ANCHORS = [
  { id: "image-load", label: "자료 적재" },
  { id: "image-list", label: "이미지 목록·확정" },
  { id: "image-recommend", label: "추천용 조회" },
];
const PAGE_SIZE = 10;
const STATUS_OPTIONS = [
  { value: "", label: "전체" }, { value: "none", label: "권리 정보 없음" }, { value: "auto", label: "자동 태깅" }, { value: "confirmed", label: "기관 확정" },
];

function Thumb({ src, alt }) {
  return src ? <img className="image-thumb" src={src} alt={alt} loading="lazy" /> : <span className="image-thumb none" aria-label="그림 파일 없음">파일 없음</span>;
}

// 목록 한 줄의 이름: 첫 수록 위치의 그림 번호·그림명 → 자료 제목 → 파일 이름
function rowName(row) {
  const caption = [row.label, row.caption].filter(Boolean).join(" ");
  return caption || row.title || row.filename || "이름 없는 그림";
}

/* 자료 적재 — 레코드 JSON 1개와 그 레코드가 가리키는 그림 파일들을 함께 고른다. 먼저 형식만 검사해 볼 수 있다 */
function LoadSection({ by, onLoaded }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(null);     // "check" | "load"
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const input = useRef(null);
  const jsonCount = files.filter((f) => /\.json$/i.test(f.name)).length;

  async function run(checkOnly) {
    setBusy(checkOnly ? "check" : "load");
    setError(null);
    setReport(null);
    const { ok, data, error: message } = await api.images.load(files, { by, checkOnly });
    setBusy(null);
    if (!ok) { setError(message); return; }
    setReport(data);
    if (!checkOnly) onLoaded();
  }

  const rejected = report?.거부 || [];
  return (
    <section id="image-load" className="nav-anchor image-section">
      <h2 className="section-title">자료 적재</h2>
      <p className="section-desc">
        JSON 1개와 그 안에서 가리키는 그림 파일들을 함께 고릅니다. 그림은 파일 이름으로 짝짓습니다.
        JSON은 두 가지를 받습니다 — 이미지 레코드(<code>docs/IMAGE_RECORD.md</code>, 예시 <code>docs/examples/image_records/</code>)와
        공공누리 수집 JSON 0.1-PoC(<code>docs/KOGL_IMPORT.md</code>, 예시 <code>docs/examples/kogl_samples/</code>). 어느 쪽인지는 자동으로 알아봅니다.
        같은 자료를 다시 넣어도 중복되지 않고, 기관이 확정한 권리 정보는 덮어쓰지 않습니다.
      </p>
      <div className="fieldset review-form">
        <div className="form-group form-group-wide">
          <div className="form-tit"><label htmlFor="image-load-files">레코드 JSON과 그림 파일</label></div>
          <div className="form-conts">
            <input ref={input} id="image-load-files" type="file" multiple accept=".json,image/*" className="image-file-input"
                   onChange={(e) => { setFiles([...e.target.files]); setReport(null); setError(null); }} />
          </div>
          <p className="form-hint">{files.length
            ? `고른 파일 ${files.length}개 — JSON ${jsonCount}개, 그림 ${files.length - jsonCount}개${jsonCount === 1 ? "" : " (JSON은 1개여야 합니다)"}`
            : "JSON 1개와 그림 파일 여러 개를 한 번에 고릅니다(합계 50MB까지)."}</p>
        </div>
        <div className="form-group form-group-wide form-actions">
          {error && <PageAlert kind="danger">{error}</PageAlert>}
          <div className="run-buttons image-actions">
            <button type="button" className="krds-btn large secondary" disabled={!!busy || jsonCount !== 1} onClick={() => run(true)}>{busy === "check" ? "검사하는 중…" : "형식만 검사"}</button>
            <button type="button" className="krds-btn large primary" disabled={!!busy || jsonCount !== 1 || !by.trim()} onClick={() => run(false)}>{busy === "load" ? "적재하는 중…" : "적재"}</button>
          </div>
          {jsonCount === 1 && !by.trim() && <p className="form-hint">적재하려면 화면 위쪽의 ‘변경한 사람’에 이름을 적어 주세요.</p>}
        </div>
      </div>
      {report && (
        <div className="image-report" role="status">
          {report.형식 && <p className="form-hint">읽은 형식: {report.형식}</p>}
          <dl className="upscale-summary">
            <div><dt>전체</dt><dd><strong>{report.전체}</strong>건</dd></div>
            {report.check_only
              ? <div><dt>형식 검사 통과</dt><dd><strong>{report.통과}</strong>건</dd><dd className="meta">DB에는 넣지 않았습니다</dd></div>
              : <div><dt>적재</dt><dd><strong>{report.적재}</strong>건</dd><dd className="meta">새 그림 {report["새 그림"]} · 기존 그림에 합침 {report["기존 그림에 합침"]}</dd></div>}
            <div><dt>거부</dt><dd><strong>{rejected.length}</strong>건</dd>
              {!report.check_only && report["필수 항목 충족률"] !== null && <dd className="meta">필수 항목 충족률 {(report["필수 항목 충족률"] * 100).toFixed(1)}%</dd>}</div>
            {!report.check_only && (
              <div><dt>추가·변경</dt><dd className="meta">수록 위치 {report["추가된 수록 위치"]} · 수행준거 연결 {report["추가된 수행준거 연결"]} · 고친 권리 정보 {report["고친 권리 정보"]}</dd>
                <dd className="meta">확정이라 유지한 권리 정보 {report["확정 유지"].length}</dd></div>
            )}
          </dl>
          {rejected.length > 0 && (
            <ul className="image-rejected">
              {rejected.map((item) => (
                <li key={item.index}><strong>{item.index + 1}번째 {report.형식?.startsWith("공공누리") ? "항목" : "레코드"}</strong>
                  <ul>{item.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
                </li>
              ))}
            </ul>
          )}
          {(report.안내 || []).length > 0 && (
            <div className="image-notes">
              <p className="form-hint">안내 — 거부 사유는 아니지만 확인해 둘 점입니다.</p>
              <ul className="image-rejected is-note">
                {report.안내.map((item) => (
                  <li key={item.index}><strong>{item.index + 1}번째 항목{item.image_id ? ` (${item.image_id})` : ""}</strong>
                    <ul>{item.notes.map((note, i) => <li key={i}>{note}</li>)}</ul>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/* 추천용 조회 — 추천(REQ-02-011)과 생성형 AI가 보게 될 목록. 기관 확정 + 재사용 범위 확인 + 비공개 아님만 나온다 */
function RecommendSection({ terms, refreshKey }) {
  const [state, setState] = useState({ status: "loading" });
  const [page, setPage] = useState(1);
  useEffect(() => {
    let current = true;
    api.images.recommendable({ limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }).then(({ ok, data, error }) => {
      if (current) setState(ok ? { status: "ready", data } : { status: "error", error });
    });
    return () => { current = false; };
  }, [page, refreshKey]);

  return (
    <section id="image-recommend" className="nav-anchor image-section">
      <div className="section-head">
        <h2 className="section-title">추천용 조회{state.data ? <span className="meta"> {state.data.total}건</span> : null}</h2>
      </div>
      <p className="section-desc">
        이미지 추천과 생성형 AI가 받게 될 목록입니다. 기관이 확정했고 재사용 범위가 정해졌으며 ‘비공개’가 아닌 그림만 나옵니다.
        정부 귀속이고 전체 재사용이 가능한 자산이 먼저 나오고, 항목마다 출처와 이용조건이 함께 나갑니다.
      </p>
      {state.status === "error" && <PageAlert kind="danger">{state.error}</PageAlert>}
      {state.status === "ready" && (state.data.items.length === 0
        ? <p className="empty">추천 목록에 나오는 그림이 없습니다. 위 목록에서 그림을 열어 재사용 범위를 정하고 기관 확정을 하면 여기에 나타납니다.</p>
        : (
          <div className="krds-table-wrap">
            <table className="tbl col data image-table">
              <caption>추천 목록에 나오는 그림</caption>
              <colgroup><col className="col-thumb" /><col /><col className="col-license" /><col className="col-source" /><col className="col-scope" /></colgroup>
              <thead><tr><th scope="col">그림</th><th scope="col">제목·키워드</th><th scope="col">라이선스·이용조건</th><th scope="col">출처</th><th scope="col">재사용 범위</th></tr></thead>
              <tbody>{state.data.items.map((row) => (
                <tr key={row.id}>
                  <td><Thumb src={api.images.recommendableFileUrl(row.id)} alt={row.title || row.filename || "그림"} /></td>
                  <td><strong>{row.title || row.filename || "이름 없는 그림"}</strong>{row.keywords.length > 0 && <span className="sub">{row.keywords.join(", ")}</span>}</td>
                  <td>{licenseLabel(row, terms)}<span className="sub">{conditionsLabel(row)}</span></td>
                  <td>{row.source_org || row.author || "—"}<span className="sub">{terms?.ownership?.[row.ownership]}</span></td>
                  <td>{terms?.reuse_scope?.[row.reuse_scope]}{row.scope_check_needed && <span className="krds-badge bg-light-warning scope-badge">범위 확인 필요</span>}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ))}
      {state.data && <Pagination page={page} total={Math.ceil(state.data.total / PAGE_SIZE)} onChange={setPage} label="추천 목록 쪽" />}
    </section>
  );
}

export default function ImageDbPage() {
  usePageTitle("이미지 저작권 DB");
  const [ready, setReady] = useState(null);       // null 확인 중 | true | false(DB 없음) | "error"
  const [terms, setTerms] = useState(null);
  const [by, setBy] = useState(loadName);
  const [filters, setFilters] = useState({ status: "", category: "", q: "" });
  const [query, setQuery] = useState("");         // 검색칸에 적는 중인 글 — [검색]을 눌러야 filters.q가 된다
  const [page, setPage] = useState(1);
  const [list, setList] = useState({ status: "loading" });
  const [counts, setCounts] = useState(null);
  const [openId, setOpenId] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);   // 적재·수정·확정 뒤 목록·요약·추천을 다시 읽는다
  const detail = useRef(null);

  useEffect(() => {
    api.health().then(({ ok, data }) => {
      if (!ok) { setReady("error"); return; }
      setReady(!!data.image_db);
      if (data.image_db) api.images.terms().then((found) => { if (found.ok) setTerms(found.data); });
    });
  }, []);

  useEffect(() => {
    if (ready !== true) return undefined;
    let current = true;
    api.images.list({ ...filters, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }).then(({ ok, data, error }) => {
      if (current) setList(ok ? { status: "ready", data } : { status: "error", error });
    });
    return () => { current = false; };
  }, [ready, filters, page, refreshKey]);

  useEffect(() => {
    if (ready !== true) return undefined;
    let current = true;
    const total = (call) => call.then(({ ok, data }) => (ok ? data.total : null));
    Promise.all([
      total(api.images.list({ limit: 1 })), total(api.images.list({ status: "none", limit: 1 })), total(api.images.list({ status: "auto", limit: 1 })),
      total(api.images.list({ status: "confirmed", limit: 1 })), total(api.images.recommendable({ limit: 1 })),
    ]).then(([all, none, auto, confirmed, recommendable]) => { if (current) setCounts({ all, none, auto, confirmed, recommendable }); });
    return () => { current = false; };
  }, [ready, refreshKey]);

  const refresh = useCallback(() => setRefreshKey((n) => n + 1), []);
  const categoryOptions = useMemo(() => termOptions(terms?.category, "전체"), [terms]);

  function changeFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  }
  function open(id) {
    setOpenId(id);
    requestAnimationFrame(() => detail.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }));
  }

  const items = list.data?.items || [];
  return (
    <>
    <Header anchors={ready === true ? ANCHORS : []} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page image-db-page">
      <h1 className="page-title">이미지 저작권 DB</h1>
      <p className="page-desc">
        원고에서 뽑거나 수집한 이미지의 권리 정보를 모아 두고 기관이 확정하는 곳입니다. 자료를 적재하면 ‘자동 태깅’ 상태로 들어오고,
        그림을 열어 분류·귀속·라이선스를 확인한 뒤 ‘기관 확정’을 하면 추천 목록에 쓸 수 있게 됩니다.
      </p>

      {ready === null && <Spinner label="서버 상태를 확인하는 중" />}
      {ready === "error" && <PageAlert kind="danger">서버에 연결하지 못했습니다. 가상환경의 ncs-web 서버가 실행 중인지 확인하세요.</PageAlert>}
      {ready === false && (
        <PageAlert kind="info">
          이미지 저작권 DB는 데이터베이스(PostgreSQL)가 연결되어 있을 때만 쓸 수 있습니다.{"\n"}
          .env에 DATABASE_URL을 두고 서버를 다시 띄우세요(docs/WEB.md의 데이터베이스 안내).
        </PageAlert>
      )}

      {ready === true && <>
        <dl className="upscale-summary image-summary">
          <div><dt>등록된 그림</dt><dd><strong>{counts?.all ?? "…"}</strong>건</dd></div>
          <div><dt>확정 대기</dt><dd><strong>{counts ? counts.none + counts.auto : "…"}</strong>건</dd><dd className="meta">자동 태깅 {counts?.auto ?? "…"} · 권리 정보 없음 {counts?.none ?? "…"}</dd></div>
          <div><dt>기관 확정</dt><dd><strong>{counts?.confirmed ?? "…"}</strong>건</dd></div>
          <div><dt>추천 목록에 나옴</dt><dd><strong>{counts?.recommendable ?? "…"}</strong>건</dd><dd className="meta">확정 + 재사용 범위 확인 + 비공개 아님</dd></div>
        </dl>

        <div className="fieldset review-form image-by">
          <div className="form-group">
            <div className="form-tit"><label htmlFor="image-by">변경한 사람</label></div>
            <div className="form-conts">
              <input id="image-by" type="text" className="krds-input" maxLength={50} value={by} placeholder="예: 에디팅기관 홍길동"
                     onChange={(e) => { setBy(e.target.value); saveName(e.target.value); }} aria-describedby="image-by-hint" />
            </div>
            <p className="form-hint" id="image-by-hint">적재·수정·확정을 할 때마다 변경 이력에 이 이름이 남습니다. 로그인이 없어 직접 적습니다.</p>
          </div>
        </div>

        <LoadSection by={by} onLoaded={refresh} />

        <section id="image-list" className="nav-anchor image-section">
          <div className="section-head">
            <h2 className="section-title">이미지 목록·확정{list.data ? <span className="meta"> {list.data.total}건</span> : null}</h2>
          </div>
          <form className="image-filters" onSubmit={(e) => { e.preventDefault(); changeFilter("q", query.trim()); }}>
            <div className="filter"><label htmlFor="filter-status">확정 상태</label>
              <KrdsSelect id="filter-status" value={filters.status} options={STATUS_OPTIONS} onChange={(v) => changeFilter("status", v)} title="확정 상태 선택" /></div>
            <div className="filter"><label htmlFor="filter-category">분류 체계</label>
              <KrdsSelect id="filter-category" value={filters.category} options={categoryOptions} onChange={(v) => changeFilter("category", v)} title="분류 체계 선택" /></div>
            <div className="filter grow"><label htmlFor="filter-q">검색</label>
              <input id="filter-q" type="search" className="krds-input" maxLength={100} value={query} placeholder="제목·그림명·키워드·수집 번호·그림 사용 문장" onChange={(e) => setQuery(e.target.value)} /></div>
            <button type="submit" className="krds-btn medium secondary">검색</button>
          </form>

          {list.status === "loading" && <Spinner label="목록을 읽는 중" />}
          {list.status === "error" && <PageAlert kind="danger">{list.error}</PageAlert>}
          {list.status === "ready" && (items.length === 0
            ? <p className="empty">{counts?.all ? "조건에 맞는 그림이 없습니다." : "등록된 그림이 없습니다. 위 ‘자료 적재’에서 레코드를 넣어 주세요."}</p>
            : (
              <div className="krds-table-wrap">
                <table className="tbl col data image-table">
                  <caption>이미지 저작권 DB에 등록된 그림</caption>
                  <colgroup><col className="col-thumb" /><col /><col className="col-category" /><col className="col-license" /><col className="col-scope" /><col className="col-status" /><col className="col-open" /></colgroup>
                  <thead><tr><th scope="col">그림</th><th scope="col">그림명·수록 위치</th><th scope="col">분류 체계</th><th scope="col">라이선스</th><th scope="col">재사용 범위</th><th scope="col">상태</th><th scope="col">열기</th></tr></thead>
                  <tbody>{items.map((row) => {
                    const [statusText, tone] = statusBadge(row.status, terms);
                    return (
                      <tr key={row.id} className={row.id === openId ? "is-open" : undefined}>
                        <td><Thumb src={row.has_file ? api.images.fileUrl(row.id) : null} alt={rowName(row)} /></td>
                        <td><strong>{rowName(row)}</strong>
                          <span className="sub">{row.module_code ? `${row.module_code}${row.placement_count > 1 ? ` 외 ${row.placement_count - 1}곳(모듈 ${row.module_count}개)` : ""}` : `수록 위치 없음(수집 자료${row.source_id ? ` ${row.source_id}` : ""})`}</span></td>
                        <td>{terms?.category?.[row.category] || "—"}</td>
                        <td>{licenseLabel(row, terms)}{row.ai_used && <span className="sub">AI 활용</span>}</td>
                        <td>{row.status ? terms?.reuse_scope?.[row.reuse_scope] || row.reuse_scope : "—"}</td>
                        <td><span className={`krds-badge ${tone}`}>{statusText}</span></td>
                        <td><button type="button" className="krds-btn small tertiary" onClick={() => open(row.id)} aria-label={`${rowName(row)} 열기`}>열기</button></td>
                      </tr>
                    );
                  })}</tbody>
                </table>
              </div>
            ))}
          {list.data && <Pagination page={page} total={Math.ceil(list.data.total / PAGE_SIZE)} onChange={setPage} label="이미지 목록 쪽" />}

          <div ref={detail} className="nav-anchor">
            {openId && <ImageDetail key={openId} imageId={openId} terms={terms} by={by} onChanged={refresh} onClose={() => setOpenId(null)} />}
          </div>
        </section>

        <RecommendSection terms={terms} refreshKey={refreshKey} />
      </>}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
