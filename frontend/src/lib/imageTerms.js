// 이미지 저작권 DB 화면이 함께 쓰는 표시 도우미. 허용값의 이름은 서버(/api/images/terms)에서 받는다 — 화면에 값 목록을 다시 적지 않는다.

// 권리 정보 한 줄(목록 행·상세의 rights) → 라이선스 표시 글
export function licenseLabel(rights, terms) {
  if (!rights || !rights.license_scheme) return "-";
  if (rights.license_scheme === "kogl") return `공공누리 제${rights.kogl_type}유형${rights.kogl_ai ? " + AI유형" : ""}`;
  if (rights.license_scheme === "cc") return rights.cc_license === "cc0" ? "CC0" : `CC ${rights.cc_license.toUpperCase()}`;
  return terms?.license_scheme?.[rights.license_scheme] || rights.license_scheme;
}

// 이용조건 4개 → "출처표시 · 상업적 이용금지" 같은 글. 조건이 하나도 없으면 "조건 없음", 모르면 "—"
const CONDITION_NAMES = [["attribution", "출처표시"], ["non_commercial", "상업적 이용금지"], ["no_derivatives", "변경금지"], ["share_alike", "동일조건변경허락"]];
export function conditionsLabel(source) {
  if (!source || CONDITION_NAMES.every(([key]) => source[key] === null || source[key] === undefined)) return "-";
  const on = CONDITION_NAMES.filter(([key]) => source[key]).map(([, name]) => name);
  return on.length ? on.join(", ") : "조건 없음";
}

// 확정 상태 → [글, KRDS 배지 색]. 권리 정보가 아직 없는 그림은 status가 없다
export function statusBadge(status, terms) {
  if (status === "confirmed") return [terms?.status?.confirmed || "기관 확정", "bg-light-success"];
  if (status === "auto") return [terms?.status?.auto || "자동 태깅", "bg-light-warning"];
  return ["권리 정보 없음", "bg-light-gray"];
}

// {코드: 이름} → KrdsSelect 선택지. first는 맨 앞에 두는 빈 선택지 글("전체", "선택 안 함")
export function termOptions(map, first) {
  const options = Object.entries(map || {}).map(([value, label]) => ({ value, label }));
  return first ? [{ value: "", label: first }, ...options] : options;
}

// 라이선스 선택지 — 체계와 유형을 한 칸에서 고른다: "" 없음 / kogl-0~4 / cc-<유형> / expired · donated · other
export function licenseOptions(terms) {
  const kogl = Object.keys(terms?.kogl_type || {}).map((n) => ({ value: `kogl-${n}`, label: `공공누리 제${n}유형` }));
  const cc = Object.keys(terms?.cc_license || {}).map((code) => ({ value: `cc-${code}`, label: code === "cc0" ? "CC0" : `CC ${code.toUpperCase()}` }));
  const rest = ["expired", "donated", "other"].map((code) => ({ value: code, label: terms?.license_scheme?.[code] || code }));
  if (kogl.length) kogl[kogl.length - 1].dividerAfter = true;
  if (cc.length) cc[cc.length - 1].dividerAfter = true;
  return [{ value: "", label: "없음", dividerAfter: true }, ...kogl, ...cc, ...rest];
}

export function licenseChoice(rights) {
  if (!rights?.license_scheme) return "";
  if (rights.license_scheme === "kogl") return `kogl-${rights.kogl_type}`;
  if (rights.license_scheme === "cc") return `cc-${rights.cc_license}`;
  return rights.license_scheme;
}

// 선택지 값에 따라 정해지는 이용조건(공공누리·CC). 그 밖에는 null
export function conditionsOf(choice, terms) {
  if (choice.startsWith("kogl-")) return { ...terms?.kogl_type?.[choice.slice(5)], share_alike: false };
  if (choice.startsWith("cc-")) return terms?.cc_license?.[choice.slice(3)] || null;
  return null;
}

// 변경한 사람 이름 — 같은 브라우저에서 다시 적지 않게 기억한다. 저장소를 못 쓰는 환경이면 그냥 넘어간다
const NAME_KEY = "ncs-image-db-by";
export function loadName() {
  try { return window.localStorage.getItem(NAME_KEY) || ""; } catch { return ""; }
}
export function saveName(name) {
  try { window.localStorage.setItem(NAME_KEY, name); } catch { /* 기억하지 못해도 동작에는 문제없다 */ }
}
