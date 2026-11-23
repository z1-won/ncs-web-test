// NCS 분류 고르기 — NCS 누리집 'NCS 및 학습모듈검색'과 같은 차례로 세분류를 찾는다(개발계획서 작성 화면이 쓴다).
//   분야별 검색: 대분류를 고르면 중분류 › 소분류 › 세분류 › 능력단위 네 칸이 나란히 나오고, 세분류를 누르면 고른 것이 된다
//   키워드 검색: 세분류·분류 이름이나 코드에 낱말이 든 세분류
//   코드 검색:   대분류·중분류·소분류·세분류·능력단위 코드(두 자리씩). 긴 코드(2001010401, LM2001010401_19v4)를 붙여 넣으면 칸에 나눠 담는다
// subclasses: /api/plan/subclasses의 목록 [{ duty(세분류 코드 8자리 = 대2+중2+소2+세2), name, classes: {대분류, 중분류, 소분류}, ready, units }]
// duty: 지금 고른 세분류 코드. onPick(duty, unitNo): 세분류를 고름(unitNo는 코드 검색에서 능력단위 번호까지 적었을 때 그 두 자리).
// detail: 고른 세분류의 상세(/api/plan/subclasses/{duty}) — 능력단위 칸에 쓴다. loading: 그 상세를 읽거나 NCS에서 받아 오는 중.
import React, { useEffect, useMemo, useState } from "react";

const TABS = [["field", "분야별 검색"], ["keyword", "키워드 검색"], ["code", "코드 검색"]];
const CODE_FIELDS = [["major", "대분류"], ["mid", "중분류"], ["small", "소분류"], ["sub", "세분류"], ["unit", "능력단위"]];
const EMPTY_CODE = { major: "", mid: "", small: "", sub: "", unit: "" };
const MAX_ROWS = 100;

// 목록 → 대분류 › 중분류 › 소분류 › 세분류 나무. 코드 순서로 둔다
function buildTree(subclasses) {
  const majors = new Map();
  [...subclasses].filter((s) => /^\d{8}$/.test(s.duty) && s.classes?.대분류).sort((a, b) => a.duty.localeCompare(b.duty)).forEach((s) => {
    const [a, b, c] = [s.duty.slice(0, 2), s.duty.slice(0, 4), s.duty.slice(0, 6)];
    if (!majors.has(a)) majors.set(a, { code: a, name: s.classes.대분류, mids: new Map(), count: 0 });
    const major = majors.get(a);
    if (!major.mids.has(b)) major.mids.set(b, { code: b, name: s.classes.중분류, smalls: new Map() });
    const mid = major.mids.get(b);
    if (!mid.smalls.has(c)) mid.smalls.set(c, { code: c, name: s.classes.소분류, subs: [] });
    mid.smalls.get(c).subs.push(s);
    major.count += 1;
  });
  return majors;
}

const no = (code) => code.slice(-2);
const pathOf = (s) => `${s.classes?.대분류 || ""} › ${s.classes?.중분류 || ""} › ${s.classes?.소분류 || ""}`;

function Column({ title, items, selected, onSelect, empty, renderExtra }) {
  return (
    <div className="ncs-col">
      <div className="ncs-col-head">{title}</div>
      <ul className="ncs-col-list" aria-label={title}>
        {items.map((item) => (
          <li key={item.code}>
            {onSelect ? (
              <button type="button" className={`ncs-item${selected === item.code ? " is-selected" : ""}`} aria-pressed={selected === item.code} onClick={() => onSelect(item.code)}>
                <span className="ncs-no">{no(item.code)}.</span> {item.name}{renderExtra?.(item)}
              </button>
            ) : <span className="ncs-item is-text"><span className="ncs-no">{no(item.code)}.</span> {item.name}</span>}
          </li>
        ))}
        {items.length === 0 && <li className="ncs-empty">{empty}</li>}
      </ul>
    </div>
  );
}

function ResultTable({ rows, total, duty, onPick, caption, unitNo }) {
  if (!rows.length) return <p className="empty">찾은 세분류가 없습니다.</p>;
  return (
    <>
      <div className="krds-table-wrap">
        <table className="tbl col data ncs-result">
          <caption>{caption}</caption>
          <thead><tr><th scope="col">세분류 코드</th><th scope="col">분류</th><th scope="col">세분류</th><th scope="col">능력단위</th><th scope="col"><span className="sr-only">선택</span></th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.duty} className={s.duty === duty ? "is-open" : undefined}>
                <td><span className="code">{s.duty}</span></td>
                <td>{pathOf(s)}</td>
                <th scope="row">{s.name}{!s.ready && <span className="meta">NCS에서 받아 와야 함</span>}</th>
                <td>{s.units}개</td>
                <td>
                  <button type="button" className={`krds-btn small ${s.duty === duty ? "primary" : "secondary"}`} aria-pressed={s.duty === duty} onClick={() => onPick(s.duty, unitNo || "")}>
                    {s.duty === duty ? "선택됨" : "선택"}<span className="sr-only"> — {s.name}</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {total > rows.length && <p className="form-hint">찾은 세분류 {total}개 가운데 {rows.length}개만 보입니다. 조건을 더 적어 주세요.</p>}
    </>
  );
}

export function NcsPicker({ subclasses, duty, onPick, detail, loading }) {
  const [tab, setTab] = useState("field");
  const tree = useMemo(() => buildTree(subclasses), [subclasses]);
  const [major, setMajor] = useState("");
  const [mid, setMid] = useState("");
  const [small, setSmall] = useState("");
  const [query, setQuery] = useState("");
  const [code, setCode] = useState(EMPTY_CODE);
  const [searched, setSearched] = useState(null);     // 코드 검색을 누른 때의 조건

  // 밖에서 고른 세분류가 바뀌면(처음 열 때의 기본값, 다른 탭에서 고름) 분야별 칸도 그 자리로 옮긴다
  useEffect(() => {
    if (!/^\d{8}$/.test(duty || "") || !tree.has(duty.slice(0, 2))) return;
    setMajor(duty.slice(0, 2)); setMid(duty.slice(0, 4)); setSmall(duty.slice(0, 6));
  }, [duty, tree]);

  const majorNode = tree.get(major);
  const midNode = majorNode?.mids.get(mid);
  const smallNode = midNode?.smalls.get(small);
  const picked = smallNode?.subs.some((s) => s.duty === duty) ? duty : "";
  const units = detail && detail.duty === picked ? (detail.units?.length ? detail.units : detail.listed || []) : [];

  const keywordHits = useMemo(() => {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    return subclasses.filter((s) => { const text = `${s.name} ${s.duty} ${Object.values(s.classes || {}).join(" ")}`.toLowerCase(); return words.every((w) => text.includes(w)); })
      .sort((a, b) => (a.ready === b.ready ? a.duty.localeCompare(b.duty) : a.ready ? -1 : 1));
  }, [subclasses, query]);

  // 코드 칸: 숫자만 두 자리. 긴 코드를 붙여 넣으면(LM·판 번호가 붙어 있어도) 앞에서부터 두 자리씩 다음 칸으로 넘긴다
  function typeCode(key, value) {
    const digits = value.replace(/_.*$/, "").replace(/\D/g, "");
    const keys = CODE_FIELDS.map(([name]) => name);
    const next = { ...code };
    if (digits.length <= 2) next[key] = digits;
    else keys.slice(keys.indexOf(key)).forEach((name, i) => { next[name] = digits.slice(i * 2, i * 2 + 2); });
    setCode(next);
  }
  const prefix = (c) => {
    const parts = [c.major, c.mid, c.small, c.sub];
    const filled = parts.findIndex((part) => part.length < 2);
    return parts.slice(0, filled === -1 ? 4 : filled).join("");
  };
  const gap = (c) => [c.major, c.mid, c.small, c.sub, c.unit].some((part, i, all) => part.length < 2 && all.slice(i + 1).some((later) => later));
  const codeHits = useMemo(() => {
    if (!searched) return [];
    const head = prefix(searched);
    return subclasses.filter((s) => s.duty.startsWith(head)).sort((a, b) => a.duty.localeCompare(b.duty));
  }, [subclasses, searched]);

  return (
    <div className="ncs-picker">
      <div className="krds-tab-area">
        <div className="tab line full">
          <ul role="tablist" aria-label="세분류 찾는 방법">
            {TABS.map(([key, label]) => (
              <li key={key} role="none" className={tab === key ? "active" : undefined}>
                <button type="button" role="tab" id={`ncs-tab-${key}`} className="btn-tab" aria-selected={tab === key} aria-controls={`ncs-panel-${key}`} onClick={() => setTab(key)}>
                  {label}{tab === key && <span className="sr-only"> 선택됨</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {tab === "field" && (
        <div id="ncs-panel-field" role="tabpanel" aria-labelledby="ncs-tab-field" className="ncs-panel">
          {!majorNode ? (
            <>
              <p className="ncs-step-title">대분류</p>
              <ul className="ncs-majors">
                {[...tree.values()].map((node) => (
                  <li key={node.code}>
                    <button type="button" className="ncs-major" onClick={() => { setMajor(node.code); setMid(""); setSmall(""); }}>
                      <span className="ncs-no">{node.code}.</span> {node.name}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <>
              <div className="ncs-crumb">
                <button type="button" className="krds-btn small text" onClick={() => { setMajor(""); setMid(""); setSmall(""); }}>
                  <span aria-hidden="true">‹</span> 이전화면<span className="sr-only">(대분류 고르기)</span>
                </button>
                <p className="ncs-step-title">{majorNode.code}. {majorNode.name}</p>
              </div>
              <div className="ncs-cols">
                <Column title="중분류" items={[...majorNode.mids.values()]} selected={mid} onSelect={(value) => { setMid(value); setSmall(""); }} empty="" />
                <Column title="소분류" items={midNode ? [...midNode.smalls.values()] : []} selected={small} onSelect={setSmall} empty="중분류를 골라 주세요" />
                <Column title="세분류" items={smallNode ? smallNode.subs.map((s) => ({ code: s.duty, name: s.name })) : []} selected={picked}
                        onSelect={(value) => onPick(value, "")} empty="소분류를 골라 주세요" />
                <Column title="능력단위" items={units.map((unit) => ({ code: unit.code.replace(/_.*$/, ""), name: unit.name }))}
                        empty={!picked ? "세분류를 골라 주세요" : loading ? "능력단위를 읽는 중입니다" : "능력단위 목록이 없습니다"} />
              </div>
            </>
          )}
        </div>
      )}

      {tab === "keyword" && (
        <div id="ncs-panel-keyword" role="tabpanel" aria-labelledby="ncs-tab-keyword" className="ncs-panel">
          <div className="ncs-search">
            <label htmlFor="ncs-keyword">검색어</label>
            <input id="ncs-keyword" type="search" className="krds-input" value={query} placeholder="예: 숙박, 객실관리, SW제품기획" onChange={(e) => setQuery(e.target.value)} />
          </div>
          {query.trim()
            ? <ResultTable rows={keywordHits.slice(0, MAX_ROWS)} total={keywordHits.length} duty={duty} onPick={onPick} caption="검색어가 든 세분류" />
            : <p className="form-hint">세분류 이름, 대분류·중분류·소분류 이름, 세분류 코드로 찾습니다. 낱말을 띄어 여러 개 적으면 모두 든 것만 나옵니다.</p>}
        </div>
      )}

      {tab === "code" && (
        <div id="ncs-panel-code" role="tabpanel" aria-labelledby="ncs-tab-code" className="ncs-panel">
          <div className="ncs-code-form" role="group" aria-label="코드로 찾기">
            {CODE_FIELDS.map(([key, label]) => (
              <div key={key} className="ncs-code-field">
                <label htmlFor={`ncs-code-${key}`}>{label} 코드</label>
                <input id={`ncs-code-${key}`} type="text" inputMode="numeric" className="krds-input" maxLength={20} placeholder="00" value={code[key]}
                       onChange={(e) => typeCode(key, e.target.value)}
                       onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (code.major.length === 2 && !gap(code)) setSearched(code); } }} />
              </div>
            ))}
            <div className="ncs-code-actions">
              <button type="button" className="krds-btn medium tertiary" onClick={() => { setCode(EMPTY_CODE); setSearched(null); }}>초기화</button>
              <button type="button" className="krds-btn medium primary" disabled={code.major.length !== 2 || gap(code)} onClick={() => setSearched(code)}>검색</button>
            </div>
          </div>
          <p className="form-hint">
            {gap(code) ? "앞 칸부터 차례로 두 자리씩 적어 주세요." : "대분류부터 두 자리씩 적습니다. 2001010401이나 LM2001010401_19v4 같은 긴 코드는 첫 칸에 붙여 넣으면 나눠 담깁니다."}
          </p>
          {searched && (
            <ResultTable rows={codeHits.slice(0, MAX_ROWS)} total={codeHits.length} duty={duty} onPick={onPick} unitNo={searched.unit.length === 2 ? searched.unit : ""}
                         caption={`코드가 ${prefix(searched)}(으)로 시작하는 세분류`} />
          )}
          {searched?.unit.length === 2 && codeHits.length > 0 && (
            <p className="form-hint">능력단위 {searched.unit}번까지 적었습니다. 세분류를 선택하면 아래 능력단위 표에서 그 능력단위만 고른 상태가 됩니다.</p>
          )}
        </div>
      )}
    </div>
  );
}
