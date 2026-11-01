import React, { useEffect, useRef } from "react";

// KRDS 모달(krds-modal) 마크업을 그대로 쓰되, 열기/닫기는 ui-script.js 대신 React 상태로 제어한다.
// 열리면 첫 버튼에 초점을 두고, ESC로 닫는다(KRDS 모달 스크립트와 같은 동작).
export function ConfirmDialog({ title, children, confirmLabel = "확인", busy = false, onConfirm, onCancel }) {
  const firstButton = useRef(null);
  useEffect(() => {
    firstButton.current?.focus();
    function onKey(event) { if (event.key === "Escape" && !busy) onCancel(); }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <section className="krds-modal shown in" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="modal-dialog modal-sm">
        <div className="modal-content">
          <div className="modal-header">
            <h2 id="confirm-title" className="modal-title">{title}</h2>
          </div>
          <div className="modal-conts">
            <div className="conts-area">{children}</div>
          </div>
          <div className="modal-btn btn-wrap">
            <button ref={firstButton} type="button" className="krds-btn medium tertiary" onClick={onCancel} disabled={busy}>취소</button>
            <button type="button" className="krds-btn medium primary" onClick={onConfirm} disabled={busy}>{busy ? "삭제 중…" : confirmLabel}</button>
          </div>
          <button type="button" className="krds-btn medium icon btn-close" onClick={onCancel} disabled={busy}>
            <span className="sr-only">닫기</span>
            <i className="svg-icon ico-popup-close" aria-hidden="true"></i>
          </button>
        </div>
      </div>
      <div className="modal-back in" onClick={busy ? undefined : onCancel}></div>
    </section>
  );
}
