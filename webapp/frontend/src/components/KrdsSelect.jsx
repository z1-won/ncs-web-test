import React, { useEffect, useRef, useState } from "react";

// KRDS 셀렉트 + 드롭다운 메뉴. 브라우저 기본 <select>는 펼친 목록의 모양을 바꿀 수 없어서, 닫힌 모양은 KRDS 셀렉트(krds-form-select),
// 펼친 목록은 KRDS 드롭다운(krds-drop-wrap › drop-menu › drop-list › item-link)으로 그린다.
// 동작은 KRDS 셀렉트 가이드대로: 클릭·Enter·Space로 열고 닫기, Esc로 닫고 초점은 컨테이너로, 닫힌 상태에서 ↑↓로 바로 이전·다음 값,
// 열린 상태에서 ↑↓·Home·End로 이동 후 Enter로 선택, Tab·바깥 클릭이면 닫힘. 값이 바뀌어도 폼은 제출하지 않는다.
// option.dividerAfter가 참이면 그 항목 아래에 구분선을 긋는다(성격이 다른 항목 묶음 분리용).
export function KrdsSelect({ id, value, options, onChange, title, describedBy }) {
  const [open, setOpen] = useState(false);
  const [focusIndex, setFocusIndex] = useState(0);
  const wrap = useRef(null);
  const button = useRef(null);
  const selectedIndex = Math.max(0, options.findIndex((o) => o.value === value));
  const selected = options[selectedIndex];

  useEffect(() => {
    if (!open) return undefined;
    setFocusIndex(selectedIndex);
    function onDocumentClick(event) { if (!wrap.current?.contains(event.target)) setOpen(false); }
    document.addEventListener("mousedown", onDocumentClick);
    return () => document.removeEventListener("mousedown", onDocumentClick);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (open) wrap.current?.querySelector(`#${id}-opt-${focusIndex}`)?.focus();
  }, [open, focusIndex, id]);

  function choose(index) {
    onChange(options[index].value);
    setOpen(false);
    button.current?.focus();
  }

  function onButtonKey(event) {
    const last = options.length - 1;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (open) setFocusIndex((i) => Math.min(last, Math.max(0, i + (event.key === "ArrowDown" ? 1 : -1))));
      else onChange(options[Math.min(last, Math.max(0, selectedIndex + (event.key === "ArrowDown" ? 1 : -1)))].value);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen((o) => !o);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
    }
  }

  function onOptionKey(event, index) {
    const last = options.length - 1;
    const moves = { ArrowDown: Math.min(last, index + 1), ArrowUp: Math.max(0, index - 1), Home: 0, End: last };
    if (event.key in moves) {
      event.preventDefault();
      setFocusIndex(moves[event.key]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      choose(index);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
      button.current?.focus();
    } else if (event.key === "Tab") {
      setOpen(false);
    }
  }

  return (
    <div ref={wrap} className={`krds-drop-wrap drop-left check-select${open ? " is-open" : ""}`}>
      <button ref={button} type="button" id={id} className={`krds-form-select${value ? " completed" : ""}${open ? " is-active" : ""}`}
              title={title} aria-haspopup="listbox" aria-expanded={open} aria-controls={`${id}-list`} aria-describedby={describedBy}
              onClick={() => setOpen((o) => !o)} onKeyDown={onButtonKey}>
        {selected?.label}
      </button>
      <div className="drop-menu" id={`${id}-list`} hidden={!open}>
        <div className="drop-in">
          <ul className="drop-list" role="listbox" aria-labelledby={id}>
            {options.map((option, index) => (
              <li key={option.value} role="none" className={option.dividerAfter ? "has-divider" : undefined}>
                <button type="button" role="option" id={`${id}-opt-${index}`} tabIndex={index === focusIndex ? 0 : -1}
                        className={`item-link${option.value === value ? " active" : ""}`} aria-selected={option.value === value}
                        onClick={() => choose(index)} onKeyDown={(event) => onOptionKey(event, index)}>
                  {option.label}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
