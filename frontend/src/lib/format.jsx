// 결과 값을 화면 글로 바꾸는 순수 함수들.

import React from "react";

export function formatDate(iso) {
  return new Date(iso).toLocaleString("ko-KR");
}

// 좁은 칸용: 날짜와 시각(오전/오후 포함)을 두 줄로. "2026. 11. 2. 오후 3:35:43" → ["2026. 11. 2.", "오후 3:35:43"]
export function formatDateLines(iso) {
  const d = new Date(iso);
  return [d.toLocaleDateString("ko-KR"), d.toLocaleTimeString("ko-KR")];
}

// 결과 텍스트의 네모 번호 표기 [1]~[20]을 한컴 원고처럼 네모 안 숫자로 그린다(유니코드에 대응 글자가 없어 CSS로 그림).
export function withBoxNumbers(text) {
  if (typeof text !== "string" || !/\[\d{1,2}\]/.test(text)) return text;
  const parts = text.split(/(\[\d{1,2}\])/);
  return parts.map((part, i) => (/^\[\d{1,2}\]$/.test(part)
    ? <span key={i} className="box-number" aria-label={`네모 번호 ${part.slice(1, -1)}`}>{part.slice(1, -1)}</span>
    : part));
}

// 결과 값(문자열·목록·딕셔너리)을 표 칸에 읽기 좋게 편다. 데이터 자체(JSON·ZIP)는 구조를 그대로 유지한다.
//   목록      → 한 줄에 하나
//   딕셔너리  → "이름: 값" 한 줄에 하나 (값이 목록이면 그 아래에 한 줄씩)
export function asText(value, depth = 0) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (value.every((item) => item == null || typeof item !== "object")) return value.map((item) => asText(item)).join("\n");
    return value.map((item) => asText(item, depth + 1)).join("\n");
  }
  if (depth > 1) return JSON.stringify(value);
  return Object.entries(value)
    .map(([key, item]) => (Array.isArray(item) && item.length > 1 ? `${key}:\n${asText(item, depth + 1)}` : `${key}: ${asText(item, depth + 1)}`))
    .join(depth === 0 ? "\n" : ", ");
}
