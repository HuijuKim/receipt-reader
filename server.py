"""영수증 리더 백엔드 (FastAPI)

안드로이드 앱이 사진을 올리면 기존 파이프라인(extract)을 그대로 돌려
결과 JSON을 돌려줍니다. API 규격은 android/API.md 참고.

핵심: Google Vision 인증키는 이 서버에만 두고, 앱에는 절대 넣지 않습니다.
      (APK는 누구나 열어볼 수 있어 키가 유출됩니다)

[인증]  외부(인터넷)에 열어두면 URL을 아는 누구나 OCR을 돌릴 수 있고
      그대로 Vision 요금이 되므로, /extract 는 X-API-Key 헤더를 요구합니다.
      키는 아래 순서로 결정됩니다.
        1) 환경변수 RECEIPT_API_KEY
        2) 이 파일 옆의 api_key.txt
        3) 둘 다 없으면 새로 만들어 api_key.txt 에 저장 (콘솔에 출력)

[실행]
    # Google Vision 인증 환경변수가 설정된 상태여야 합니다.
    uvicorn server:app --host 0.0.0.0 --port 8000
    # 개발 중 자동 리로드: uvicorn server:app --reload
"""
from __future__ import annotations

import os
import secrets
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from core import Receipt
from csv_export import BOM, rows_to_csv
from profile_db import ProfileDB
from receipt_db import ReceiptDB
from receipt_reader import extract

app = FastAPI(title="영수증 리더 API", version="0.3")

# 휴대폰 카메라 사진은 보통 3~8MB 입니다. 넉넉히 잡되 상한은 둡니다.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_KEY_FILE = Path(__file__).with_name("api_key.txt")


# ======================================================================
# 인증
# ======================================================================
def _load_api_key() -> str:
    """API 키를 환경변수 → 파일 순으로 찾고, 없으면 새로 만들어 저장합니다."""
    from_env = os.environ.get("RECEIPT_API_KEY", "").strip()
    if from_env:
        return from_env

    if _KEY_FILE.exists():
        saved = _KEY_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved

    generated = secrets.token_urlsafe(32)
    _KEY_FILE.write_text(generated, encoding="utf-8")
    print(f"[영수증 리더] API 키를 새로 만들어 {_KEY_FILE.name} 에 저장했습니다.")
    return generated


API_KEY = _load_api_key()
print(f"[영수증 리더] API 키: {API_KEY}")
print("[영수증 리더] 앱의 [설정] 탭에 위 키를 그대로 붙여넣으세요.")


def require_api_key(x_api_key: str = Header(default="", alias="X-API-Key")) -> None:
    """키 검증. compare_digest 로 비교해 타이밍 공격을 막습니다.

    바이트로 비교하는 이유: str 을 넘기면 비ASCII 문자에서 TypeError 가 나
    500 이 되어버립니다. 잘못된 키는 항상 401 이어야 합니다.
    """
    if not secrets.compare_digest(x_api_key.encode("utf-8"), API_KEY.encode("utf-8")):
        raise HTTPException(401, "API 키가 올바르지 않습니다")


def _to_dto(r: Receipt) -> dict:
    """Receipt → API 응답 dict (raw_text 는 크고 앱에 불필요하므로 제외)."""
    return {
        "store": r.store,
        "date": r.date,
        "card": r.card,
        "total": r.total,
        "profile": r.profile,
        "items": [{"name": i.name, "amount": i.amount} for i in r.items],
        "notes": r.notes,
    }


# ======================================================================
# 엔드포인트
# ======================================================================
@app.get("/health")
def health() -> dict:
    """서버까지 연결이 닿는지만 확인합니다 (키 불필요, 정보 노출 없음)."""
    return {"status": "ok"}


@app.get("/verify", dependencies=[Depends(require_api_key)])
def verify() -> dict:
    """앱의 [연결 테스트]용 — 주소와 키가 모두 맞는지 확인합니다."""
    return {"status": "ok"}


# async 가 아닌 def 로 둡니다 → FastAPI가 스레드풀에서 실행하므로
# (네트워크를 쓰는) OCR 호출이 이벤트 루프를 막지 않습니다.
@app.post("/extract", dependencies=[Depends(require_api_key)])
def extract_receipt(image: UploadFile = File(...)) -> dict:
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(400, f"이미지 파일이 아닙니다: {image.content_type}")

    tmp_path = _save_upload(image)
    try:
        # 요청마다 DB 연결을 새로 엽니다 (sqlite 연결은 스레드 간 공유 불가)
        with ProfileDB() as db:
            receipt = extract(tmp_path, db=db, learn=True)
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:                    # OCR 엔진 오류(재시도 후 실패 포함)
        raise HTTPException(502, str(e)) from e
    finally:
        os.unlink(tmp_path)

    return _to_dto(receipt)


# ======================================================================
# 내역 보관 — 앱이 폰에 저장한 목록을 서버로 올립니다
# ======================================================================
class LineItemIn(BaseModel):
    name: str
    amount: int


class ReceiptIn(BaseModel):
    client_id: int              # 폰 DB 의 행 번호 (device_id 와 묶어 중복 방지)
    store: str | None = None
    date: str | None = None
    card: str | None = None
    total: int | None = None
    profile: str = ""
    items: list[LineItemIn] = []
    notes: list[str] = []
    saved_at: int = 0


class UploadIn(BaseModel):
    device_id: str
    receipts: list[ReceiptIn]


@app.post("/receipts", dependencies=[Depends(require_api_key)])
def upload_receipts(body: UploadIn) -> dict:
    """앱이 보낸 내역을 저장합니다.

    같은 내역을 다시 보내도 쌓이지 않고 갱신만 됩니다(device_id + client_id 기준).
    덕분에 앱은 '무엇을 이미 보냈는지' 기억하지 않고 전체를 보내면 됩니다.
    """
    device_id = body.device_id.strip()
    if not device_id:
        raise HTTPException(400, "device_id 가 비어 있습니다")

    with ReceiptDB() as db:
        saved = db.upsert_many(device_id, [r.model_dump() for r in body.receipts])
        return {"saved": saved, "total": db.count()}


@app.get("/receipts", dependencies=[Depends(require_api_key)])
def list_receipts(device_id: str | None = None) -> dict:
    with ReceiptDB() as db:
        rows = db.load(device_id)
    return {"count": len(rows), "receipts": rows}


@app.get("/receipts.csv", dependencies=[Depends(require_api_key)])
def receipts_csv(device_id: str | None = None) -> Response:
    """올라온 내역 전체를 CSV 로. 브라우저에서 열면 그대로 내려받아집니다."""
    with ReceiptDB() as db:
        rows = db.load(device_id)
    body = BOM + rows_to_csv(rows)          # BOM: 엑셀 한글 깨짐 방지
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="receipts.csv"'},
    )


def _save_upload(image: UploadFile) -> str:
    """업로드를 임시 파일로 저장하고 경로를 돌려줍니다 (OpenCV 가 경로를 받으므로).

    한 번에 읽지 않고 조각으로 받으면서 상한을 확인합니다 — 거대한 파일로
    디스크를 채우는 요청을 막기 위해서입니다.
    """
    suffix = Path(image.filename or "upload.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    total = 0
    try:
        while chunk := image.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    413, f"이미지가 너무 큽니다 (최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB)"
                )
            tmp.write(chunk)
    except BaseException:
        tmp.close()
        os.unlink(tmp.name)
        raise
    else:
        tmp.close()
        return tmp.name
