r"""OCR 단계 — 이미지 전처리 + Google Cloud Vision + 좌표 기반 행 복원.

이 모듈만 갈아끼우면 다른 OCR(CLOVA 등)로 교체할 수 있습니다.
run_ocr() 가 최종 텍스트(시각적 행 단위)를 돌려주면 됩니다.

[인증]  아래 둘 중 하나 (실행 전 환경변수 지정):
  (A) API 키 방식 [간단]:
        setx GOOGLE_VISION_API_KEY "AIza...."
  (B) 서비스 계정 키(JSON) 방식:
        setx GOOGLE_APPLICATION_CREDENTIALS "C:\경로\key.json"
  → API 키가 있으면 (A), 아니면 (B)의 기본 인증(ADC)을 사용합니다.
"""
from __future__ import annotations

import os
import threading
import time

import cv2
import numpy as np
from google.api_core import exceptions as gexc
from google.cloud import vision

# 재시도할 일시 오류들 (인증/결제/잘못된요청은 제외 → 즉시 실패)
_TRANSIENT_EXC = (gexc.ServiceUnavailable, gexc.DeadlineExceeded,
                  gexc.InternalServerError, gexc.TooManyRequests,
                  gexc.ResourceExhausted, gexc.Aborted)

# Vision 클라이언트는 만들 때마다 gRPC 채널 + 자격증명 로드 + TLS 핸드셰이크가
# 붙습니다(요청당 수백 ms). 스레드 안전하므로 프로세스당 하나만 만들어 씁니다.
#   ※ 서버는 요청을 스레드풀에서 처리하므로 생성 자체를 락으로 감쌉니다.
_client: vision.ImageAnnotatorClient | None = None
_client_lock = threading.Lock()


def _vision_client() -> vision.ImageAnnotatorClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:       # 락 대기 중에 다른 스레드가 만들었을 수 있음
                # API 키가 있으면 그것을, 없으면 서비스 계정(ADC) 인증을 사용
                api_key = os.environ.get("GOOGLE_VISION_API_KEY")
                _client = (
                    vision.ImageAnnotatorClient(client_options={"api_key": api_key})
                    if api_key else vision.ImageAnnotatorClient()
                )
    return _client


# ======================================================================
# 1) 이미지 전처리
# ======================================================================
def preprocess(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"이미지를 열 수 없습니다: {image_path}")

    # (1) 해상도가 낮으면 크게 확대 — 작은 글씨 인식률이 크게 오릅니다.
    h, w = img.shape[:2]
    if max(h, w) < 2200:
        scale = 2200 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_CUBIC)

    # (2) 흑백 변환. 저해상도 영수증에선 디노이즈/이진화가 오히려 획을 뭉개므로
    #     그레이스케일만 넘겨주는 편이 정확합니다(엔진이 내부 이진화 처리).
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return gray


# ======================================================================
# 2) OCR (Google Cloud Vision)
# ======================================================================
# Tesseract 언어코드("kor+eng") → Vision 언어힌트(["ko","en"]) 매핑
_VISION_LANG = {"kor": "ko", "eng": "en", "ko": "ko", "en": "en"}

# --- 일시 오류 자동 재시도 설정 ---------------------------------------
#   Vision은 가끔 "service is currently unavailable" 같은 일시 오류를 냅니다.
#   네트워크/서버 문제이므로 잠시 뒤 재시도하면 대개 성공합니다.
#   반면 인증/결제/잘못된 요청은 재시도해도 소용없으므로 즉시 실패시킵니다.
OCR_MAX_ATTEMPTS = 4        # 총 시도 횟수
OCR_BACKOFF_BASE = 1.5      # 대기 = BASE ** 시도횟수 (초) — 1.5, 2.3, 3.4초
# 응답 본문에 담겨 오는 일시 오류 gRPC 코드
#   4=DEADLINE_EXCEEDED, 8=RESOURCE_EXHAUSTED, 13=INTERNAL, 14=UNAVAILABLE
_TRANSIENT_CODES = {4, 8, 13, 14}


def _lines_from_vision(annotation) -> str:
    """Vision 결과를 단어 좌표 기준으로 '시각적 행'으로 재구성.

    Vision의 기본 text 는 읽기 순서로 나열돼, 영수증처럼 열(칼럼)이 있는
    문서는 품목명과 금액이 서로 다른 줄로 흩어집니다. 각 단어의 y좌표로
    같은 가로줄을 묶고 x좌표로 정렬하면 원래 행(이름 ... 금액)이 복원됩니다.
    """
    words = []
    for page in annotation.pages:
        for block in page.blocks:
            for para in block.paragraphs:
                for w in para.words:
                    txt = "".join(s.text for s in w.symbols)
                    ys = [v.y for v in w.bounding_box.vertices]
                    xs = [v.x for v in w.bounding_box.vertices]
                    words.append({
                        "x0": min(xs), "x1": max(xs),   # 좌/우 x
                        "y": sum(ys) / len(ys),          # 세로 중심
                        "h": max(ys) - min(ys),          # 글자 높이
                        "t": txt,
                    })
    if not words:
        return annotation.text  # 좌표가 없으면 기본 텍스트로 폴백

    heights = sorted(w["h"] for w in words)
    tol = max(1.0, heights[len(heights) // 2] * 0.6)  # 같은 행 판정 허용오차

    # y좌표 순으로 훑으며 같은 행끼리 묶기
    words.sort(key=lambda w: w["y"])
    rows: list[list[dict]] = []
    cur: list[dict] = []
    cur_y = None
    for w in words:
        if cur_y is None or abs(w["y"] - cur_y) <= tol:
            cur.append(w)
            cur_y = w["y"] if cur_y is None else (cur_y + w["y"]) / 2
        else:
            rows.append(cur)
            cur, cur_y = [w], w["y"]
    if cur:
        rows.append(cur)

    # 각 행은 x좌표 순 정렬 후, 단어 사이 '간격'이 글자 높이의 일정 비율을
    # 넘을 때만 공백을 넣습니다(Vision이 한 단어를 잘게 쪼갠 경우 → 붙임).
    lines = []
    for r in rows:
        parts = sorted(r, key=lambda w: w["x0"])
        text = parts[0]["t"]
        for prev, w in zip(parts, parts[1:]):
            gap = w["x0"] - prev["x1"]
            avg_h = (prev["h"] + w["h"]) / 2 or 1
            text += (" " if gap > avg_h * 0.4 else "") + w["t"]
        lines.append(text)
    return "\n".join(lines)


def run_ocr(image: np.ndarray, lang: str = "kor+eng") -> str:
    hints = [_VISION_LANG.get(x, x) for x in lang.split("+")]

    # 전처리된 numpy 이미지를 PNG 바이트로 인코딩해 Vision에 전달
    ok, buf = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("이미지 인코딩 실패")

    client = _vision_client()
    vimage = vision.Image(content=buf.tobytes())

    for attempt in range(1, OCR_MAX_ATTEMPTS + 1):
        try:
            # document_text_detection: 영수증처럼 밀집된 문서 텍스트에 최적화
            response = client.document_text_detection(
                image=vimage,
                image_context=vision.ImageContext(language_hints=hints),
            )
            if response.error.message:
                # 일시 오류는 예외로 바꿔 아래 except 에서 재시도
                if response.error.code in _TRANSIENT_CODES:
                    raise gexc.ServiceUnavailable(response.error.message)
                raise RuntimeError(f"Vision API 오류: {response.error.message}")
            # 기본 text 대신 좌표 기반으로 행을 재구성해 반환
            return _lines_from_vision(response.full_text_annotation)
        except _TRANSIENT_EXC as e:
            if attempt == OCR_MAX_ATTEMPTS:
                raise RuntimeError(
                    f"Vision API 일시 오류가 계속됩니다 ({OCR_MAX_ATTEMPTS}회 시도): {e}"
                ) from e
            wait = OCR_BACKOFF_BASE ** attempt
            print(f"  [!] Vision 일시 오류 — {wait:.1f}초 후 재시도 "
                  f"({attempt}/{OCR_MAX_ATTEMPTS - 1}): {e}")
            time.sleep(wait)


# --- (구) Tesseract OCR — 참고용 보관 --------------------------------
#   되돌리려면: pip install pytesseract + Tesseract 본체 설치 후 아래 사용.
# import pytesseract
# def run_ocr(image: np.ndarray, lang: str = "kor+eng") -> str:
#     config = "--oem 3 --psm 6"   # psm 6 = 하나의 균일한 텍스트 블록
#     return pytesseract.image_to_string(image, lang=lang, config=config)
