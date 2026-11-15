// 업스케일링 — 원고(hwpx)를 올리면 목표 DPI 미만 그림을 보여 주고, 고른 그림만 한 장씩 키워 내려받는다(UpscalePanel).
// 검수와 따로 쓰는 기능이라 원고 검수 페이지에서 떼어 메인 메뉴의 한 페이지로 둔다. 원고는 이 페이지에서 따로 올린다.
import React, { useEffect, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { FileSlot } from "../components/FileSlot.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { UpscalePanel } from "../components/UpscalePanel.jsx";
import { usePageTitle } from "../lib/hooks.js";

export default function UpscalePage() {
  usePageTitle("업스케일링");
  const [file, setFile] = useState(null);
  const [upload, setUpload] = useState({ status: "idle" });   // { status: idle|uploading|ready|error, token, name, error }
  const tokenRef = useRef(null);   // 서버에 올려 둔 토큰 — 파일을 바꾸거나 페이지를 떠날 때 반납한다

  useEffect(() => {
    if (tokenRef.current) { api.uploads.remove(tokenRef.current); tokenRef.current = null; }
    if (!file) { setUpload({ status: "idle" }); return undefined; }
    if (!/\.hwpx$/i.test(file.name)) {
      setUpload({ status: "error", error: "hwp 원고는 그림을 읽지 못합니다. 한글에서 hwpx로 저장해 다시 올리세요." });
      return undefined;
    }
    const controller = new AbortController();
    setUpload({ status: "uploading" });
    // 칸이 곧 역할(#13) — 내용 판별 없이 원고로 올린다
    api.uploads.create([file], controller.signal, ["manuscript"]).then(({ ok, data, error: message, aborted }) => {
      if (aborted) return;
      if (!ok) { setUpload({ status: "error", error: message }); return; }
      tokenRef.current = data.upload;
      setUpload({ status: "ready", token: data.upload, name: data.roles?.manuscript || file.name });
    });
    return () => controller.abort();
  }, [file]);

  useEffect(() => () => { if (tokenRef.current) api.uploads.remove(tokenRef.current); }, []);

  return (
    <>
    <Header anchors={[]} hasHistory={false} hasResult={false} />
    <main id="container" className="inner page">
      <h1 className="page-title">업스케일링</h1>
      <p className="page-desc">
        원고(.hwpx)를 올리면 쪽에 출력되는 크기에 비해 해상도가 낮은 그림을 찾아 보여 줍니다. 그림을 골라 한 장씩 키우고,
        결과 그림이나 그 그림들을 같은 자리에 넣은 제안본 hwpx를 내려받습니다. 원고 본문은 바꾸지 않습니다.
      </p>

      <div className="fieldset review-form">
        <FileSlot id="file-upscale" label="원고" required accept=".hwpx" file={file} onChange={setFile}
                  uploading={upload.status === "uploading"} invalid={upload.status === "error" ? upload.error : null}
                  hint="hwpx 원고만 됩니다. hwp는 한글에서 hwpx로 저장해 올리세요." />
      </div>

      {upload.status === "ready"
        ? <UpscalePanel key={upload.token} token={upload.token} manuscriptName={upload.name} moduleCode="" />
        : <p className="empty">원고를 올리면 해상도가 낮은 그림 목록이 여기에 표시됩니다.</p>}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
