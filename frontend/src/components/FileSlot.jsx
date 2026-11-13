// 업로드 칸 하나 — 원고 / 개발계획서 / 출력본 PDF를 따로 고른다(#13). 한 칸에 파일 하나.
// 숨긴 <input type=file>을 진짜 <button>이 대신 열어 키보드(Enter/Space)로도 동작한다. 고른 뒤에는 '지우기'로 그 칸만 비운다
// (개발계획서는 그대로 두고 원고만 바꿔 올리는 식으로 쓴다).
import React, { useRef } from "react";

// file: 고른 File 또는 null. status: 파일명 뒤에 붙일 짧은 상태(예: "역할 확인 중…"). invalid: 이 칸의 오류 문구(있으면 빨간 도움말).
// hint: 그 아래 한 줄 안내(선택).
export function FileSlot({ id, label, required, accept, file, onChange, disabled, status, invalid, hint }) {
  const input = useRef(null);
  function clear() {
    if (input.current) input.current.value = "";   // 같은 파일을 다시 골라도 change가 나도록
    onChange(null);
  }
  return (
    <div className="form-group">
      <div className="form-tit">
        <label htmlFor={id}>
          {label}
          {required
            ? <span className="required"> <i aria-hidden="true">*</i><span className="sr-only">필수</span></span>
            : " (선택)"}
        </label>
      </div>
      <div className="form-conts file-slot">
        <input ref={input} id={id} type="file" accept={accept} className="sr-only" tabIndex={-1} aria-describedby={`${id}-hint`}
               aria-invalid={invalid ? "true" : undefined} aria-required={required ? "true" : undefined}
               onChange={(e) => onChange(e.target.files?.[0] || null)} />
        {/* 셀렉트·입력칸과 같은 large 높이(--krds-size-height large)로 칸의 규격을 맞춘다 */}
        <button type="button" className="krds-btn large tertiary" disabled={disabled} onClick={() => input.current?.click()}>
          {file ? "파일 바꾸기" : "파일 선택"}<span className="sr-only"> — {label}</span>
        </button>
        {file && (
          <button type="button" className="krds-btn medium text file-slot-clear" disabled={disabled} onClick={clear}>
            지우기<span className="sr-only"> — {label}</span>
          </button>
        )}
      </div>
      <p className="form-hint" id={`${id}-hint`}>{file ? `${file.name}${status ? ` — ${status}` : ""}` : "선택된 파일 없음"}</p>
      {invalid && <p className="form-hint-invalid" role="alert" style={{ whiteSpace: "pre-wrap" }}>{invalid}</p>}
      {hint && <p className="form-hint">{hint}</p>}
    </div>
  );
}
