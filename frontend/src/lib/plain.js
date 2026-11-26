// 서버가 보낸 '쓸 수 없는 까닭'을 이용자가 읽을 말로 바꾼다.
// 서버 문구에는 설치 명령, 설정 파일 이름, 환경 변수 이름이 들어 있다(명령줄과 로그에서도 쓰는 문구라 서버 쪽은 그대로 둔다).
// 이용자가 할 수 있는 일이 아니므로 화면에는 "관리자에게 문의"로만 알리고, 원문은 개발자 도구(console)에 남긴다.
const ASK = "관리자에게 문의해 주세요.";
const AI_OFF = "생성형 AI를 쓸 수 없음(관리자 설정 필요)";
const SETUP = /pip install|requirements\/|\.env|[A-Z]{2,}_[A-Z_]{2,}|패키지가 없|환경 ?변수|python -m|scripts\//;
const AI_WORDS = /anthropic|LLM|API_KEY|Claude|OPENAI/i;

// 생성형 AI 호출이 실패했을 때: 서버는 까닭을 원문 그대로(HTTP 상태, 서비스가 보낸 영어 JSON) 실어 보낸다.
// 이용자에게는 무슨 일인지와 할 수 있는 일을 한 문장씩으로 바꿔 보인다. 원문은 개발자 도구(console)에 남는다.
// 서버 문구의 두 꼴: "생성형 AI 호출에 실패…(원문). 뒷말" 과 "LLM 호출 실패: 원문[ — 뒷말]"
const CALL_FAILED = /생성형 AI 호출에 실패|LLM 호출 실패:/;
const KEY_PROBLEM = "생성형 AI 서비스의 인증 키가 만료되었거나 올바르지 않아 지금은 사용할 수 없습니다. 관리자에게 문의해 주세요.";
const FAIL_CAUSES = [
  [/HTTP 40[13]\b|expired|invalid[_ ]api[_ ]key|incorrect api key|authentication|unauthorized/i, KEY_PROBLEM],
  [/HTTP 429\b|rate[_ ]limit|quota|insufficient/i, "생성형 AI 서비스의 사용 한도를 넘었습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 문의해 주세요."],
  [/HTTP 5\d\d\b|overloaded|unavailable/i, "생성형 AI 서비스가 일시적으로 응답하지 않습니다. 잠시 후 다시 시도해 주세요."],
  [/연결 실패|timed? ?out|시간 초과|network|unreachable|getaddrinfo/i, "생성형 AI 서비스에 연결하지 못했습니다. 네트워크 연결을 확인한 뒤 다시 시도해 주세요."],
  [/HTTP 40[04]\b|허용되지 않은 작업/i, "서버의 생성형 AI 설정에 문제가 있어 지금은 사용할 수 없습니다. 관리자에게 문의해 주세요."],
  [/JSON|잘림|거절/, "생성형 AI가 결과를 올바른 형식으로 보내지 않았습니다. 다시 시도해 주세요."],
];
const FAIL_OTHER = "생성형 AI를 호출하지 못했습니다. 잠시 후 다시 시도해 주세요. 계속되면 관리자에게 문의해 주세요.";
const sentence = (text) => (text && !/[.!?]$/.test(text) ? `${text}.` : text);

// 여는 괄호의 짝이 되는 닫는 괄호의 자리(원문 안에 괄호가 겹쳐 있을 수 있다). 짝이 없으면 -1
function closing(text, open) {
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "(") depth += 1;
    else if (text[i] === ")") { depth -= 1; if (depth === 0) return i; }
  }
  return -1;
}

export function plainFailure(text) {
  const found = CALL_FAILED.exec(text);
  if (!found) return text;
  const cause = (FAIL_CAUSES.find(([pattern]) => pattern.test(text)) || [null, FAIL_OTHER])[1];
  const before = text.slice(0, found.index).trim();
  if (found[0].startsWith("LLM")) {            // "LLM 호출 실패: 원문 — 사람이 확인" → 까닭 + 뒷말
    const rest = text.slice(found.index + found[0].length);
    const dash = rest.lastIndexOf(" — ");
    const said = dash >= 0 ? rest.slice(dash + 3).trim() : "";
    const tail = said === "사람이 확인" ? "이 항목은 담당자가 직접 확인해 주세요" : said;
    return [before, cause, sentence(tail)].filter(Boolean).join(" ");
  }
  const open = text.indexOf("(", found.index);
  const close = open >= 0 ? closing(text, open) : -1;
  if (close < 0) return [before, cause].filter(Boolean).join(" ");
  // 괄호 앞의 말이 '실패했습니다'뿐이면 까닭 문장이 대신한다. 다른 말이 있으면(예: 규칙으로 대신 뽑았다) 남긴다
  const head = text.slice(found.index, open).trim();
  const kept = /^생성형 AI 호출에 실패했습니다$/.test(head) ? "" : sentence(head);
  const tail = text.slice(close + 1).replace(/^[\s.]+/, "").trim();
  return [before, kept, cause, sentence(tail)].filter(Boolean).join(" ");
}

export function plainReason(text) {
  if (!text || typeof text !== "string") return text;
  let out = plainFailure(text);
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
