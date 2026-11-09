// 원본 JSON 접기 — 펼친 코드 상자 오른쪽 위에 복사 버튼(KRDS 아이콘 버튼 .krds-btn.icon). 누르면 아래 보이는 JSON 문자열 그대로 클립보드에 넣고 잠깐 '복사됨'을 띄운다.
import React, { useEffect, useRef, useState } from "react";

export function RawJson({ data, title }) {
  const text = JSON.stringify(data, null, 1);
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  async function copy() {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        // 클립보드 API가 없는 환경(http 등): 숨은 textarea로 선택 후 복사
        const ta = document.createElement("textarea");
        ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
        document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
      }
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 1500);
    } catch { setCopied(false); }
  }

  return (
    <details className="raw">
      <summary>{title}</summary>
      <div className="raw-body">
        <button type="button" className={`krds-btn small icon btn-copy${copied ? " is-copied" : ""}`} onClick={copy}
                title={copied ? "복사됨" : "JSON 복사"} aria-label={copied ? "복사됨" : "JSON 복사"}>
          <i className="svg-icon" aria-hidden="true"></i>
        </button>
        <span className="copy-toast" role="status" aria-live="polite">{copied ? "복사됨" : ""}</span>
        <pre>{text}</pre>
      </div>
    </details>
  );
}
