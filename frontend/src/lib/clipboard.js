// 글을 클립보드에 복사한다 — 이미지 추천의 출처 문구, 권리 증빙 점검의 알림 글이 함께 쓴다.
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // 클립보드 API가 없는 환경(http 등): 숨은 textarea로 선택 후 복사
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const done = document.execCommand("copy");
    area.remove();
    return done;
  }
}
