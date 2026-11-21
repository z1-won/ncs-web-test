// 업스케일링 — 원고(hwpx)를 올리면 목표 DPI 미만 그림을 보여 주고, 고른 그림만 한 장씩 키워 내려받는다(UpscalePanel).
// 검수와 따로 쓰는 기능이라 원고 검수 페이지에서 떼어 메인 메뉴의 한 페이지로 둔다. 원고는 이 페이지에서 따로 올린다.
import React, { useEffect, useRef, useState } from "react";

import { api } from "../lib/api.js";
import { FileSlot } from "../components/FileSlot.jsx";
import { KrdsSelect } from "../components/KrdsSelect.jsx";
import { Footer, Header, TopButton } from "../components/Layout.jsx";
import { UpscalePanel } from "../components/UpscalePanel.jsx";
import { IMAGE_DPI_DEFAULT, IMAGE_DPI_OPTIONS } from "../lib/dpi.js";
import { usePageTitle } from "../lib/hooks.js";

export default function UpscalePage() {
  usePageTitle("업스케일링");
  const [file, setFile] = useState(null);
  const [targetDpi, setTargetDpi] = useState(String(IMAGE_DPI_DEFAULT));   // 해상도 기준 — 원고 검수(기타 ⑤·⑧)와 같은 선택지
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
    <main id="container" className="inner page upscale-page">
      <h1 className="page-title">업스케일링</h1>
      <p className="page-desc">
        원고(hwpx)를 올리면 쪽에 출력되는 크기에 비해 해상도가 낮은 그림을 찾아 보여 줍니다. 그림을 골라 키운 뒤,
        그 그림만 같은 자리에 바꿔 넣은 제안본 hwpx를 내려받습니다. 제안본은 그림 화질만 다르고 글·표와 그림의 크기·위치는 원고와 같습니다.
        올린 원고 파일은 바뀌지 않습니다.
      </p>

      <div className="fieldset review-form">
        <FileSlot id="file-upscale" label="원고" required accept=".hwpx" file={file} onChange={setFile}
                  uploading={upload.status === "uploading"} invalid={upload.status === "error" ? upload.error : null}
                  hint="hwpx 원고만 됩니다. hwp는 한글에서 hwpx로 저장해 올리세요." />
        <div className="form-group">
          <div className="form-tit"><label htmlFor="upscale-dpi">이미지 해상도 기준</label></div>
          <div className="form-conts">
            <KrdsSelect id="upscale-dpi" value={targetDpi} options={IMAGE_DPI_OPTIONS} onChange={setTargetDpi} title="이미지 해상도 기준 선택" describedBy="upscale-dpi-hint" />
          </div>
          <p className="form-hint" id="upscale-dpi-hint">이 값보다 낮은 그림을 찾아 보여 줍니다. 원고 검수의 기준과 같은 선택지입니다.</p>
        </div>
      </div>

      {upload.status === "ready"
        && <UpscalePanel key={`${upload.token}-${targetDpi}`} token={upload.token} manuscriptName={upload.name} moduleCode="" targetDpi={Number(targetDpi)} />}
      <TopButton />
    </main>
    <Footer />
    </>
  );
}
