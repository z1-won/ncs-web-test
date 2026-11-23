// 문장 추천(REQ-02-004) 화면의 순수 함수와 브라우저 보관 — 결정에서 채택 문장 꺼내기, 내려받기 표의 행, 바뀐 글자 찾기, 보관.
// 결정 하나: { choice: '채택'|'기각', rank: 고른 후보 순위|null, text: 집필자가 고쳐 쓴 문장|null, bulk: 일괄 채택인가, at: 로컬 시각 ISO }
//   rank만 있으면 AI 후보 그대로, rank와 text가 있으면 그 후보를 집필자가 고친 것, text만 있으면 집필자가 원문에서 직접 고쳐 쓴 것이다.
//   이 구분이 채택 기록의 '채택 출처'가 되어 집필자 서약서(F09) AI 고지에 쓰인다.

export const MAX_CANDIDATES = 5;                       // 서버 ncs_suggest.config.max_candidates
export const SOURCE_EDITED = "AI 생성 후 집필자 수정";  // 서버 ncs_suggest.pipeline.SOURCE_EDITED와 같은 글
export const SOURCE_OWN = "집필자 작성";               // 서버 ncs_suggest.pipeline.SOURCE_OWN과 같은 글
export const DIRECT = "직접 입력";                     // 문장 직접 입력 카드의 원고명

export const prefixOf = (card) => (card["앞 번호"] ? `${card["앞 번호"]} ` : "");

// 결정이 고른 문장과 그 출처. 채택이 아니면 null. 문장에는 앞 번호를 붙이지 않는다(붙이는 것은 쓰는 쪽).
export function chosenOf(card, decision) {
  if (decision?.choice !== "채택") return null;
  const item = decision.rank ? card.후보.find((c) => c.순위 === decision.rank) : null;
  if (decision.text != null) {
    return { 순위: item?.순위 ?? "", 문장: decision.text, 출처: item ? SOURCE_EDITED : SOURCE_OWN, 모델: item?.모델 ?? "", 고치기전: item?.문장 ?? "" };
  }
  return item ? { 순위: item.순위, 문장: item.문장, 출처: item.출처, 모델: item.모델 ?? "", 고치기전: "" } : null;
}

// 채택 기록 → 행 목록(카드마다 한 행). 채택이면 고른 문장의 순위·출처와 AI 고지(집필자 서약서 F09 '활용 AI')에 쓸
// 모델 이름·채택 일시를 적는다. 집필자가 직접 쓴 문장에는 활용 AI가 없다. 쪽 번호는 결과에 없어 구성·자리로 대신한다.
export function decisionRows(cards, decisions) {
  return cards.map((card) => {
    const decision = decisions[card.key];
    const chosen = chosenOf(card, decision);
    return {
      번호: card.key, 원고: card.원고명 || "", 구성: card.구성, 자리: card.자리, 종류: card.종류, 원문: card.원문,
      결정: decision?.choice || "미정", "채택 순위": chosen?.순위 ?? "", "채택 출처": chosen?.출처 ?? "",
      "채택 문장": chosen ? prefixOf(card) + chosen.문장 : "", "고치기 전 AI 후보": chosen?.고치기전 ? prefixOf(card) + chosen.고치기전 : "",
      "활용 AI": chosen?.모델 ?? "", "채택 일시": chosen ? decision.at : "", "일괄 채택": decision?.bulk ? "예" : "",
      "후보 수": card.후보.length,
    };
  });
}

// 근거 문장 한 칸 글(서버 ncs_suggest.pipeline.basis_text와 같은 꼴)
export function basisText(basis) {
  if (!basis) return "";
  const place = [basis.출처, basis.자리].filter(Boolean).join(", ");
  return `「${basis.문장}」 (${place ? `${place}, ` : ""}유사도 ${basis.유사도})`;
}

// 문장 정정 필요 후보문장표: 카드마다 한 행. 원본 문장 옆에 정정 후보 1~5순위와 후보별 근거 문장, 집필자의 결정을 둔다.
// 앞쪽 열은 서버 ncs_suggest.pipeline.table_columns와 같고, 화면에서 고른 결정 열을 뒤에 더한다.
export function candidateRows(cards, decisions) {
  return cards.map((card) => {
    const decision = decisions[card.key];
    const prefix = prefixOf(card);
    const row = {
      번호: card.key, 원고: card.원고명 || "", 구성: card.구성, 자리: card.자리, 종류: card.종류, "규정 꼴": card["규정 꼴"],
      "변경 필요 원본 문장": card.원문, "사유 유형": card.상태, 사유: card.사유.join(" / "),
    };
    for (let rank = 1; rank <= MAX_CANDIDATES; rank += 1) {
      const item = card.후보.find((c) => c.순위 === rank);
      row[`정정 후보 ${rank}순위`] = item ? prefix + item.문장 : "";
      row[`근거 문장 ${rank}순위`] = item ? basisText(item["근거 문장"]) : "";
    }
    const chosen = chosenOf(card, decision);
    row.비고 = card["추천 없음"] || "";
    row.결정 = decision?.choice || "미정";
    row["채택 순위"] = chosen?.순위 ?? "";
    row["채택 출처"] = chosen?.출처 ?? "";
    row["채택 문장"] = chosen ? prefix + chosen.문장 : "";
    return row;
  });
}

// 메모 원고(POST /api/suggest/memo)에 보낼 채택 기록 — 원고에서 나온 카드 가운데 채택한 것만(직접 입력한 문장은 원고에 자리가 없다).
export function memoRecords(cards, decisions) {
  return cards.filter((card) => card.원고명 !== DIRECT).flatMap((card) => {
    const decision = decisions[card.key];
    const chosen = chosenOf(card, decision);
    if (!chosen) return [];
    return [{
      원문: card.원문, 본문: card.본문, 구성: card.구성, 자리: card.자리, "사유 유형": card.상태, 사유: card.사유.join(" / "),
      "채택 문장": prefixOf(card) + chosen.문장, "채택 순위": chosen.순위, "채택 출처": chosen.출처, "활용 AI": chosen.모델, "채택 일시": decision.at,
    }];
  });
}

export function toCsv(rows) {
  if (!rows.length) return "";
  const head = Object.keys(rows[0]);
  const cell = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  return "﻿" + [head.map(cell).join(","), ...rows.map((row) => head.map((key) => cell(row[key])).join(","))].join("\r\n");
}

// 지금 시각을 로컬 시각 ISO 문자열로('2026-11-23T14:05:09+09:00').
export function localIso(date = new Date()) {
  const pad = (n) => String(Math.trunc(Math.abs(n))).padStart(2, "0");
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
    + `${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
}

const DIFF_LIMIT = 250000;   // 글자 수의 곱이 이보다 크면 견주지 않는다(문장 하나는 보통 수백 자 이하)

// 원문(from)을 후보(to)로 바꿀 때 바뀐 글자 — [{ type: 'same'|'add'|'del', text }] (가장 긴 공통 부분열, 글자 단위).
// 'same'과 'add'를 이으면 후보, 'same'과 'del'을 이으면 원문이다. 너무 길면 후보 전체를 'same' 하나로 돌려준다(강조 없음).
export function diffChars(from, to) {
  const a = Array.from(from || ""), b = Array.from(to || "");
  const n = a.length, m = b.length;
  if (n * m > DIFF_LIMIT) return [{ type: "same", text: to }];
  if (!n || !m) return [...(n ? [{ type: "del", text: from }] : []), ...(m ? [{ type: "add", text: to }] : [])];
  const width = m + 1;
  const table = new Uint16Array((n + 1) * width);   // table[i*width+j] = a[i:]와 b[j:]의 공통 부분열 길이
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      table[i * width + j] = a[i] === b[j] ? table[(i + 1) * width + j + 1] + 1 : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
    }
  }
  const parts = [];
  const push = (type, ch) => {
    const last = parts[parts.length - 1];
    if (last && last.type === type) last.text += ch; else parts.push({ type, text: ch });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { push("same", a[i]); i += 1; j += 1; }
    else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) { push("del", a[i]); i += 1; }
    else { push("add", b[j]); j += 1; }
  }
  while (i < n) { push("del", a[i]); i += 1; }
  while (j < m) { push("add", b[j]); j += 1; }
  return parts;
}

// ───────── 브라우저 보관 ─────────
// 결과(카드)와 결정, 직접 입력 카드, 유용성 응답을 이 브라우저(localStorage)에만 둔다 — 새로 고치거나 창을 닫아도 이어서 고를 수 있게.
// 원고 문장이 들어 있으므로 KEEP_DAYS가 지나면 읽을 때 지우고, 화면의 [기록 지우기]로 바로 없앨 수 있다. 서버에는 보내지 않는다.
const STORAGE_KEY = "ncs-suggest:v1";
export const KEEP_DAYS = 30;   // 서버의 생성형 AI 응답 캐시 보관 기한(LLM_CACHE_TTL_DAYS 기본값)과 같게

export function loadSaved() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved || typeof saved !== "object") return null;
    const age = Date.now() - new Date(saved.savedAt).getTime();
    if (!(age >= 0 && age < KEEP_DAYS * 86400000)) { window.localStorage.removeItem(STORAGE_KEY); return null; }
    return saved;
  } catch { return null; }
}

// 저장했으면 true. 브라우저가 저장을 막았거나 자리가 모자라면 false(화면은 그대로 쓰되 보관되지 않는다고 알린다).
export function saveState(state) {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); return true; } catch { return false; }
}

export function clearSaved() {
  try { window.localStorage.removeItem(STORAGE_KEY); } catch { /* 저장소를 못 쓰는 환경 — 지울 것도 없다 */ }
}
