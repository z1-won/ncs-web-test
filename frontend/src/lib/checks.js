// 검수 구성요소(검수 종류) 목록과 판정 집계 — 서버 /api/health의 engines가 유일한 출처이고 CHECKS는 로딩 전 자리표시자다.

// 순서 = F02 검수 확인서의 구성요소 순서(위치 → 차례 → 개요 → 필요 지식 → 수행 내용 → 교수·학습 방법 → 평가 → …)
// 선택 목록의 기본값. 글(구성요소·항목 번호)은 서버 /api/health의 engines(실제 등록된 엔진·구현 항목)로 덮어쓴다.
// 순서 = F02 검수 확인서의 구성요소 순서(위치 → 차례 → 개요 → 필요 지식 → 수행 내용 → 교수·학습 방법 → 평가 → 참고 자료 → 판권 → 기타)
export const FILE_HINTS = {
  position: "원고 + 개발계획서 (2개 필수)",
  toc: "원고 (+ 개발계획서 선택, + 출력본 PDF 선택: ⑦ 쪽수)",
  overview: "원고 (+ 개발계획서 선택)",
  knowledge: "원고 (+ 개발계획서: ⑤에만 필요)",
  perform: "원고 (hwpx 권장)",
  teaching: "원고 (hwpx 권장)",
  evaluation: "원고 + 개발계획서 (없으면 ② 판단불가)",
  references: "원고",
  colophon: "원고 (hwpx 권장)",
  misc: "원고 (hwpx 권장)",
};

export const CHECKS = [
  { value: "position", label: "NCS-학습모듈의 위치 ①~⑤" },
  { value: "toc", label: "차례 ①~⑦" },
  { value: "overview", label: "학습모듈의 개요 ①·②·⑤~⑧" },
  { value: "knowledge", label: "필요 지식 ①~⑧" },
  { value: "perform", label: "수행 내용 ①·④" },
  { value: "teaching", label: "교수·학습 방법 ①~④" },
  { value: "evaluation", label: "평가 ①~③·⑤" },
  { value: "references", label: "참고 자료 ①~③" },
  { value: "colophon", label: "개발 이력 및 판권 ①" },
  { value: "misc", label: "기타 ①·②·⑥·⑦" },
].map((c) => ({ ...c, files: FILE_HINTS[c.value] || "원고", required: c.value === "position" ? ["manuscript", "plan"] : ["manuscript"],
                optional: c.value === "toc" ? ["print"] : [] }));

export const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫";

// 구현된 항목 번호 목록 → "①~③·⑤" (연속 3개 이상은 범위로)
export function formatItems(items) {
  const idx = items.map((n) => CIRCLED.indexOf(n)).filter((i) => i >= 0).sort((a, b) => a - b);
  const parts = [];
  for (let i = 0; i < idx.length;) {
    let j = i;
    while (j + 1 < idx.length && idx[j + 1] === idx[j] + 1) j += 1;
    parts.push(j - i >= 2 ? `${CIRCLED[idx[i]]}~${CIRCLED[idx[j]]}` : idx.slice(i, j + 1).map((k) => CIRCLED[k]).join("·"));
    i = j + 1;
  }
  return parts.join("·");
}

// 서버가 알려 준 엔진 목록으로 선택 목록을 만든다. 구성요소 이름의 띄어쓰기는 확인서 원문(예: "개발 이력 및판권")을 읽기 좋게 고른다.
export function checksFromEngines(engines) {
  if (!Array.isArray(engines) || !engines.length) return CHECKS;
  return engines.map((e) => ({
    value: e.check,
    label: `${String(e.component).replace("및판권", "및 판권")} ${formatItems(e.items || [])}`,
    files: FILE_HINTS[e.check] || (e.required?.includes("plan") ? "원고 + 개발계획서" : "원고"),
    items: e.items,
    total: e.total,
    required: e.required || ["manuscript"],
    optional: e.optional || [],   // 선택 입력 역할(예: print = 출력본 PDF). 없을 때 화면이 안내만 한다
  }));
}

// ───────────────────────── 전체 실행(구성요소 10개를 차례로) ─────────────────────────
// 선택 목록의 첫 항목(기본값). 서버의 check 값이 아니라 화면이 처리한다: 파일을 /api/uploads에 한 번 올려 토큰을 받고,
// 엔진 순서대로 /api/review를 upload=토큰으로 부른다. 결과는 구성요소별 아코디언(KRDS krds-accordion)에 하나씩 채워진다.
export const ALL_CHECK = "all";

export const ALL_OPTION = {
  value: ALL_CHECK,
  label: "전체 — 구성요소 10개를 차례로 검수",
  files: "원고 + 개발계획서 (+ 출력본 PDF 선택) — 개발계획서가 없으면 '위치'만 건너뛰고 나머지를 실행",
  all: true,
  optional: ["print"],
  dividerAfter: true, // 선택 목록 맨 위에 두고, 아래 개별 구성요소와 구분선으로 나눈다
};

// 확인서 행의 검수결과 집계 → { 적합, 부적합, 판단불가, 미검사 }
export function countVerdicts(sheet) {
  const counts = { 적합: 0, 부적합: 0, 판단불가: 0, 미검사: 0 };
  (sheet || []).forEach((row) => { if (row.검수결과 in counts) counts[row.검수결과] += 1; });
  return counts;
}

// 묶음 판정: 부적합 하나라도 있으면 부적합 → 판단불가 → 적합 (서버 group_verdict와 같은 규칙)
export function overallVerdict(verdicts) {
  for (const candidate of ["부적합", "판단불가", "적합"]) if (verdicts.includes(candidate)) return candidate;
  return null;
}
