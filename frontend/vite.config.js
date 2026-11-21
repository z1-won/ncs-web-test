import { rm } from "node:fs/promises";
import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 빌드 전에 출력 폴더를 직접 비운다. Vite가 기본으로 쓰는 동기 삭제(fs.rmSync)는
// Windows의 Node 23에서 경로에 한글 등 비ASCII 글자가 있으면 프로세스가 죽는다
// (예: C:\...\2026년_2학기\...\frontend\dist). 비동기 삭제는 같은 경로에서도 동작한다.
function cleanOutDir() {
  let outDir;
  return {
    name: "clean-out-dir",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    async buildStart() {
      await rm(outDir, { recursive: true, force: true });
    },
  };
}

// 개발 중에는 /api 요청을 로컬 Python 서버(8765)로 넘긴다.
export default defineConfig({
  plugins: [react(), cleanOutDir()],
  build: { emptyOutDir: false },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
});
