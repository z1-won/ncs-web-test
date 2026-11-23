// 처음 화면(/) — 위쪽 띠(무엇을 할지 묻는 제목 + 시작 버튼), 내 할 일(세분류 건에서 지금 내 차례인 권), 최근 원고의 진행 현황 미리 보기, 묶음별 기능 카드.
// 일의 출발점은 세분류 건의 '내 할 일'이다. DB가 있는 서버에서 로그인했으면 그것을 맨 위에 보이고 시작 버튼도 세분류 건으로 간다.
// 미리 보기는 서버가 DB 이력을 쓸 때만(/api/health의 history) 보인다. 전체 목록과 한 원고의 단계·진행도는 /progress(머리글의 '진행 현황').
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../lib/api.js";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { useAuth } from "../lib/auth.jsx";
import { usePageTitle } from "../lib/hooks.js";
import { StageBar } from "./ProgressPage.jsx";

const TODO_PREVIEW = 3;   // 처음 화면에 보이는 내 할 일 수 — 나머지는 세분류 건 화면에서
const PREVIEW = 4;        // 미리 보기에 보이는 원고 수 — 아래 기능 묶음과 같은 4열 한 줄
const STAGE_COUNT = 7;
// 기능 묶음 넷(집필·검수·이미지·마무리 — 묶음 구성은 정해진 것이라 배치 때문에 바꾸지 않는다). 번호를 붙이지 않는다(이미지 작업은 검수와 나란히 가고, 묶음이 곧 순서는 아니다). 카드: 무엇을 하는지 한 줄 + 필요한 파일.
// ai: 원고 문장이나 입력한 글 일부가 생성형 AI 서비스로 나가는 기능(개인정보처리방침 '외부로 보내는 내용'과 같아야 한다)
const GROUPS = [
  { title: "집필", items: [
    { path: "/plan", label: "개발계획서 작성", desc: "세분류를 고르면 NCS 기준정보를 채운 초안을 만들고, 작성한 계획서를 점검합니다.",
      files: "초안은 파일 없이 세분류 선택. 점검은 개발계획서(hwp, hwpx)" },
    { path: "/suggest", label: "문장 추천", desc: "작성 규칙에 맞지 않는 문장을 찾아 고칠 후보를 보여 줍니다.", files: "원고(hwp, hwpx)", ai: "생성형 AI 사용" },
  ] },
  { title: "검수", items: [
    { path: "/review", label: "원고 검수", desc: "검수 확인서 항목별로 적합 여부와 위치, 사유를 보여 줍니다.", main: true,
      files: "원고(hwp, hwpx). 개발계획서와 출력본 PDF는 선택", ai: "일부 항목에 생성형 AI 사용" },
    { path: "/opinion", label: "의견 반영 검토", desc: "검토의견서와 심의의견서의 의견이 최종 원고에 반영되었는지 대조합니다.",
      files: "검토의견서 또는 심의의견서, 최종 원고", ai: "생성형 AI 사용" },
  ] },
  { title: "이미지", items: [
    { path: "/upscale", label: "업스케일링", desc: "해상도가 낮은 그림의 화질을 높인 제안본을 만듭니다.", files: "원고(hwpx)" },
    { path: "/images", label: "이미지 저작권 DB", desc: "그림과 권리 정보를 등록하고 기관이 확정합니다.", files: "그림 파일과 권리 정보(JSON)" },
    { path: "/recommend", label: "이미지 추천", desc: "문단에 어울리는 그림을 이미지 저작권 DB에서 찾아 줍니다.", files: "파일 없이 문단을 화면에 입력", ai: "켰을 때만 생성형 AI 사용" },
    { path: "/ai-image", label: "이미지 AI 보완", desc: "AI로 만들거나 고친 그림에 활용 표기를 넣고, 서약서에 붙일 결과물 현황을 만듭니다.", files: "원고(hwp, hwpx). 출력본 PDF는 선택" },
  ] },
  { title: "마무리", items: [
    { path: "/rights", label: "권리 증빙 점검", desc: "원고의 그림과 제출 서류를 대조해 빠진 증빙과 기한을 알려 줍니다.", files: "원고, 제출 서류(수록 현황 목록, 동의서, 서약서)" },
    { path: "/volume", label: "원고 분량", desc: "계약서 기준으로 원고 분량(매)과 집필료를 산정합니다.", files: "최종 원고(hwp, hwpx). 기존 원고와 출력본 PDF는 선택" },
  ] },
];

export default function HomePage() {
  usePageTitle("");
  const [list, setList] = useState(null);      // null: DB 없음, 로그인 전 또는 확인 전(미리 보기 자리를 그리지 않는다)
  const [todo, setTodo] = useState(null);      // 내 할 일(세분류 건). null이면 그 자리를 그리지 않는다
  const { status } = useAuth();
  const signedOut = status === "out";            // 로그인 전에도 이 화면은 보인다 — 기능을 누르면 로그인 화면이 나온다

  useEffect(() => {
    if (signedOut) { setList(null); setTodo(null); return undefined; }
    let alive = true;
    (async () => {
      const health = await api.health();
      if (!alive || !(health.ok && health.data?.history)) return;
      const [{ ok, data }, mine] = await Promise.all([api.manuscripts.list(), api.cases.todo()]);
      if (!alive) return;
      if (ok) setList(data);
      if (mine.ok) setTodo(mine.data);
    })();
    return () => { alive = false; };
  }, [signedOut]);

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page home-page">
      <div className="home-hero">
        <div>
          <h1 className="page-title">어떤 업무를 하시겠습니까?</h1>
          <p className="page-desc">
            개발계획서 작성부터 원고 검수, 그림의 권리 확인까지 한곳에서 할 수 있습니다. 결과는 모두 참고용이며 최종 판단은 담당자가 합니다.
            {signedOut && " 기능을 쓰려면 로그인해 주세요."}
          </p>
        </div>
        {signedOut ? <Link className="krds-btn large primary" to="/login">로그인</Link>
                   : todo ? <Link className="krds-btn large primary" to="/cases">세분류 건 열기</Link>
                   : <Link className="krds-btn large primary" to="/review">원고 검수 시작</Link>}
      </div>

      {todo && (
        <section aria-labelledby="home-todo-title">
          <div className="home-section-head">
            <h2 className="section-title" id="home-todo-title">내 할 일 <span className="meta">{todo.length}건, 세분류 건에서 지금 내 차례인 일</span></h2>
            <Link className="krds-btn small tertiary" to="/cases">세분류 건 전체 보기</Link>
          </div>
          {todo.length === 0 ? <p className="meta">지금 내 차례인 일이 없습니다.</p> : (
            <ul className="cases-todo-list">
              {todo.slice(0, TODO_PREVIEW).map((item) => (
                <li key={`${item.case_id}-${item.volume_id || item.stage}`}>
                  <div>
                    <strong>{item.title}</strong> <span className="meta">{item.case_name} {item.year}년{item.module_code ? `, ${item.module_code}` : ""}</span>
                    <p>{item.stage_name}: {item.todo}{item.proxy && <span className="meta"> {item.turn.join(", ")} 차례이며 대신 기록할 수 있습니다.</span>}</p>
                    {item.note && <p className="meta">보완 요청 메모: {item.note}</p>}
                  </div>
                  <Link className="krds-btn small secondary" to={`/cases?case=${item.case_id}${item.volume_id ? `&volume=${item.volume_id}` : ""}`}>열기</Link>
                </li>
              ))}
            </ul>
          )}
          {todo.length > TODO_PREVIEW && <p className="meta">나머지 {todo.length - TODO_PREVIEW}건은 세분류 건 화면에서 볼 수 있습니다.</p>}
        </section>
      )}

      {list && (
        <section aria-labelledby="home-recent-title">
          <div className="home-section-head">
            <h2 className="section-title" id="home-recent-title">최근 원고 <span className="meta">담당자가 완료로 표시한 단계, {STAGE_COUNT}단계 중</span></h2>
            <Link className="krds-btn small tertiary" to="/progress">진행 현황 전체 보기</Link>
          </div>
          {list.length === 0 ? (
            <p className="meta">아직 기록이 없습니다. 파일 이름에 모듈 코드가 있는 원고로 검수나 산정을 하면 여기에 보입니다.</p>
          ) : (
            <ul className="home-grid home-recent">
              {list.slice(0, PREVIEW).map((row) => (
                <li key={row.module_code}>
                  <Link to={`/progress?code=${encodeURIComponent(row.module_code)}`}>
                    <strong className="home-card-title">{row.name || row.module_code}</strong>
                    <span className="home-card-files">{row.module_code}</span>
                    <StageBar done={row.stages_done} />
                    <span className="home-card-files">최근 기록 {new Date(row.last_at).toLocaleDateString("ko-KR")}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section aria-labelledby="home-groups-title">
        <h2 className="sr-only" id="home-groups-title">기능</h2>
        <div className="home-grid home-groups">
          {GROUPS.map((group) => (
            <div key={group.title} className="home-group">
              <h3 className="home-group-title">{group.title}</h3>
              <ul>
                {group.items.map((item) => (
                  <li key={item.path}>
                    <Link to={item.path} className={item.main ? "is-main" : ""}>
                      <strong className="home-card-title">{item.label}</strong>
                      <span className="home-card-desc">{item.desc}</span>
                      <span className="home-card-files">필요한 파일: {item.files}</span>
                      {/* 표시는 카드 맨 아래 줄에 둔다 — 제목 옆에 두면 표시가 있는 카드만 제목 줄이 두 줄이 되어 카드마다 글 위치가 달라진다 */}
                      <span className="home-card-tags">{item.ai && <span className="krds-badge bg-light-gray">{item.ai}</span>}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
