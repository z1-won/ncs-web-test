// 이미지 해상도 기준(실효 DPI) — 원고 검수(기타 ⑤·⑧)와 업스케일링이 같은 선택지를 쓴다.
// 값은 서버(ncs_core.pictures.DPI_CHOICES·DEFAULT_TARGET_DPI)와 같아야 한다 — tests/contract/test_engines.py가 맞는지 본다.
export const IMAGE_DPI_CHOICES = [150, 300];
export const IMAGE_DPI_DEFAULT = 300;

const NOTE = { 300: "인쇄 권장", 150: "인쇄 최소" };

// KrdsSelect 옵션 — 값은 문자열(폼 값)
export const IMAGE_DPI_OPTIONS = IMAGE_DPI_CHOICES.slice().sort((a, b) => b - a)
  .map((dpi) => ({ value: String(dpi), label: `${dpi} DPI${NOTE[dpi] ? ` — ${NOTE[dpi]}` : ""}` }));
