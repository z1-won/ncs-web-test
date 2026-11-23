// 서버가 보낸 '쓸 수 없는 까닭'을 이용자가 읽을 말로 바꾼다.
// 서버 문구에는 설치 명령, 설정 파일 이름, 환경 변수 이름이 들어 있다(명령줄과 로그에서도 쓰는 문구라 서버 쪽은 그대로 둔다).
// 이용자가 할 수 있는 일이 아니므로 화면에는 "관리자에게 문의"로만 알리고, 원문은 개발자 도구(console)에 남긴다.
const ASK = "관리자에게 문의해 주세요.";
const AI_OFF = "생성형 AI를 쓸 수 없음(관리자 설정 필요)";
const SETUP = /pip install|requirements\/|\.env|[A-Z]{2,}_[A-Z_]{2,}|패키지가 없|환경 ?변수|python -m|scripts\//;
const AI_WORDS = /anthropic|LLM|API_KEY|Claude|OPENAI/i;

export function plainReason(text) {
  if (!text || typeof text !== "string") return text;
  let out = text;
  // 짧은 상태 문구("AI 미설정 — 이유", 괄호 안에 든 것 포함)는 그 자리에서 바꾼다
  out = out.replace(/(?:(?:LLM|AI) 미설정 — )+[^()\n]*(?:\([^()\n]*\)[^()\n]*)*/g, AI_OFF);
  out = out.replace(/(원고|그림) 외부 전송(?: 미승인|이 승인되지 않았습니다)[^)\n]*/g, "생성형 AI를 쓸 수 없음($1 외부 전송 미승인)");
  // 생성형 AI 상태 배지: 호출 횟수까지만 보이고 토큰 수와 비용은 뺀다(서버 응답의 usage와 개발자 도구에는 그대로 있다)
  out = out.replace(/\(새 호출 \d+번\)/g, "").replace(/\s*·\s*입력 [\d,]+(?:\([^)]*\))?\s*·\s*출력 [\d,]+토큰(?:\s*·\s*약 \$[\d.]+)?/g, "");
  if (SETUP.test(out)) {
    out = AI_WORDS.test(out)
      ? `서버에 생성형 AI 설정이 되어 있지 않아 지금은 쓸 수 없습니다. ${ASK}`
      : `서버에 필요한 프로그램이나 설정이 없어 지금은 쓸 수 없습니다. ${ASK}`;
  }
  if (out !== text) console.info("서버가 보낸 원문:", text);
  return out;
}
