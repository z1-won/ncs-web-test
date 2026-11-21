"""그림과 글을 같은 공간의 벡터로 바꾼다 — 그림 자체를 보고 문맥과 맞춰 보기 위한 것(REQ-02-011).

**외부로 아무것도 보내지 않는다.** 공개된 이미지-글 임베딩 모델(SigLIP 2 등)을 이 컴퓨터에서 직접 돌린다.
모델 파일은 처음 한 번 내려받아 두고(허깅페이스 캐시), 그 뒤로는 HF_HUB_OFFLINE=1로 네트워크 없이 쓴다.

  NCS_EMBED_MODEL   쓸 모델 이름(예: google/siglip2-base-patch16-224). **비어 있으면 꺼짐** — 추천은 키워드·수행준거로만 한다
  NCS_EMBED_DEVICE  cpu(기본) / mps / cuda

torch·transformers는 선택 설치다(pip install -e ".[embed]"). 없거나 모델을 못 읽으면 꺼진 것으로 보고 까닭을 why_not()에 남긴다.
벡터는 길이 1로 맞춰 돌려주므로 두 벡터의 내적이 곧 코사인 유사도다.
"""

import io
import os
import threading

TEXT_MAX_TOKENS = 64          # SigLIP 계열의 글 길이 상한. 긴 문단은 요약·핵심어로 줄여서 넣는다
BATCH = 8

# 그림 유사도의 바탕 — 서로 다른 분야의 글. 그림마다 '아무 글에나 이만큼은 닮는다'를 재는 데 쓴다(rank.visual_scores).
# 문맥과의 유사도가 이 바탕에서 뚜렷이 벗어나야 그 그림이 문맥과 맞는 것으로 본다. 추천 질의와 같은 꼴(한 문장 설명)로 둔다.
REFERENCE_TEXTS = (
    "재무제표의 계정과목을 분류하고 분개 내용을 전표에 기록한다.",
    "환자의 활력 징후를 측정하고 간호 기록지에 결과를 적는다.",
    "엔진 오일의 양과 점도를 점검하고 필요하면 교환한다.",
    "데이터베이스 테이블의 기본 키와 외래 키를 정의한다.",
    "벼의 생육 단계에 맞춰 논의 물 높이를 조절한다.",
    "철근의 간격과 피복 두께를 도면과 대조하여 검측한다.",
    "고객의 모발 상태를 진단하고 알맞은 염색 약제를 고른다.",
    "창고에 들어온 화물의 수량과 파손 여부를 검수한다.",
    "반죽을 1차 발효한 뒤 일정한 무게로 나누어 둥글린다.",
    "회로도에 따라 저항과 콘덴서를 기판에 납땜한다.",
    "원단의 결 방향에 맞춰 패턴을 배치하고 재단한다.",
    "수질 시료를 채취하여 용존 산소량을 측정한다.",
    "선반에 공작물을 고정하고 절삭 조건을 설정한다.",
    "근로 계약서의 임금과 근로 시간 조항을 검토한다.",
    "영유아의 발달 단계에 맞는 놀이 활동을 계획한다.",
    "설문 응답 자료를 정리하여 빈도와 평균을 산출한다.",
    "무대 조명의 위치와 밝기를 장면에 맞게 조정한다.",
    "태양광 모듈의 출력 전압과 전류를 계측한다.",
    "보험 가입자의 청구 서류를 접수하고 지급 요건을 심사한다.",
    "드론의 비행 전 배터리 잔량과 프로펠러 상태를 확인한다.",
    "수입 신고서에 품목 분류 번호와 과세 가격을 기재한다.",
    "소방 펌프의 압력계와 밸브 개폐 상태를 점검한다.",
    "웹 페이지의 화면 구성 요소를 배치하고 색상 체계를 정한다.",
    "가축의 사료 급여량을 체중과 성장 단계에 따라 조정한다.",
)

_lock = threading.Lock()
_references: dict[str, list[list[float]]] = {}      # 모델 이름 → 바탕 글의 벡터
_cached: tuple[str, object] | None = None      # (모델 이름, Embedder 또는 오류 글)


def model_name() -> str:
    return os.getenv("NCS_EMBED_MODEL", "").strip()


class Embedder:
    """모델 하나를 메모리에 올려 두고 그림·글을 벡터로 바꾼다."""

    def __init__(self, name: str, device: str = "cpu"):
        import torch
        from transformers import AutoModel, AutoProcessor

        self.name = name
        self.device = device
        self._torch = torch
        self._model = AutoModel.from_pretrained(name).to(device).eval()
        self._processor = AutoProcessor.from_pretrained(name)

    def _unit(self, features) -> list[list[float]]:
        features = getattr(features, "pooler_output", features)      # 버전에 따라 텐서 또는 출력 객체
        features = features / features.norm(dim=-1, keepdim=True).clamp(min=1e-12)
        return features.cpu().float().tolist()

    def images(self, contents: list[bytes]) -> list[list[float] | None]:
        """그림 파일 내용들 → 벡터들. 열 수 없는 그림은 None."""
        from PIL import Image

        opened: list[tuple[int, object]] = []
        for index, content in enumerate(contents):
            try:
                opened.append((index, Image.open(io.BytesIO(content)).convert("RGB")))
            except Exception:      # noqa: BLE001 — 깨진 그림 하나 때문에 나머지를 버리지 않는다
                continue
        out: list[list[float] | None] = [None] * len(contents)
        for start in range(0, len(opened), BATCH):
            chunk = opened[start:start + BATCH]
            inputs = self._processor(images=[image for _, image in chunk], return_tensors="pt").to(self.device)
            with self._torch.no_grad():
                vectors = self._unit(self._model.get_image_features(**inputs))
            for (index, _), vector in zip(chunk, vectors):
                out[index] = vector
        return out

    def text(self, text: str) -> list[float]:
        inputs = self._processor(text=[text], padding="max_length", truncation=True, max_length=TEXT_MAX_TOKENS,
                                 return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            return self._unit(self._model.get_text_features(**inputs))[0]


def get():
    """켜져 있고 쓸 수 있으면 Embedder, 아니면 None. 모델은 처음 부를 때 한 번만 올린다."""
    global _cached
    name = model_name()
    if not name:
        return None
    with _lock:
        if _cached is None or _cached[0] != name:
            try:
                _cached = (name, Embedder(name, os.getenv("NCS_EMBED_DEVICE", "cpu").strip() or "cpu"))
            except Exception as error:      # noqa: BLE001 — 설치 안 됨·모델 없음·메모리 부족 모두 '꺼짐'으로 다룬다
                _cached = (name, f"{type(error).__name__}: {error}")
        return None if isinstance(_cached[1], str) else _cached[1]      # 글이면 못 올린 까닭


def reference_vectors(embedder) -> list[list[float]]:
    """바탕 글(REFERENCE_TEXTS)의 벡터. 모델마다 처음 한 번만 계산한다. 계산하지 못하면 빈 목록(그림 유사도를 쓰지 않게 된다)."""
    name = getattr(embedder, "name", "")
    with _lock:
        if name not in _references:
            try:
                _references[name] = [embedder.text(text) for text in REFERENCE_TEXTS]
            except Exception:      # noqa: BLE001 — 바탕을 못 만들면 그림 유사도만 끈다
                return []
        return _references[name]


def why_not() -> str:
    """꺼져 있는 까닭(화면에 그대로 보여 줄 글). 켜져 있으면 빈 글."""
    name = model_name()
    if not name:
        return "그림 임베딩이 꺼져 있습니다(.env의 NCS_EMBED_MODEL이 비어 있음)"
    if get() is not None:
        return ""
    return f"그림 임베딩 모델 {name}을(를) 쓸 수 없습니다 — {str(_cached[1])[:200] if _cached else '알 수 없는 오류'}"


def cosine(a: list[float] | None, b: list[float] | None) -> float | None:
    """길이 1인 두 벡터의 코사인 유사도. 하나라도 없거나 길이가 다르면 None."""
    if not a or not b or len(a) != len(b):
        return None
    return sum(x * y for x, y in zip(a, b))
