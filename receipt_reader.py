r"""영수증 소비내역 추출기 (Receipt Spending Extractor) — 오케스트레이션 + CLI
=====================================================================
스캔된 영수증 이미지에서 상호명 / 날짜 / 품목 / 합계 금액을 추출합니다.

파이프라인:  이미지 전처리 → OCR(Vision) → 발행처 식별 → 양식별 파싱

모듈 구성:
    core.py         공통 데이터구조(Receipt/Profile) + 정규식/키워드
    ocr.py          전처리 + Google Vision OCR + 좌표 기반 행 복원
    issuer.py       발행처(매장) 식별 + 내장 양식 + 새 양식 자동 학습
    parser.py       양식 규칙 기반 파싱 엔진 + 매장별 전용 파서 등록
    parsers/        (하이브리드) 매장별 전용 파서 파일 — 특이 매장만
    profile_db.py   양식(Profile) 저장소 (SQLite)

[설치]
    pip install opencv-python numpy google-cloud-vision
    # 인증: setx GOOGLE_VISION_API_KEY "AIza...."   (또는 서비스계정 JSON)
    #   자세한 내용은 ocr.py 상단 참고.

[실행]
    python receipt_reader.py 영수증.jpg              # 새 양식이면 자동 학습·저장
    python receipt_reader.py 영수증.jpg --csv         # result/영수증.csv 로 저장
    python receipt_reader.py 영수증.jpg --profile emart
    python receipt_reader.py --list-profiles         # 저장된 양식 목록
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from core import Profile, Receipt
from csv_export import rows_to_csv
from ocr import preprocess, run_ocr
from issuer import (GENERIC, PROFILE_BY_KEY, PROFILES, detect_profile,
                    learn_profile, validate_profile)
from parser import parse
from profile_db import ProfileDB


# ======================================================================
# 파이프라인
# ======================================================================
def extract(image_path: str, profile: Optional[Profile] = None,
            db: Optional[ProfileDB] = None, learn: bool = True) -> Receipt:
    """이미지 → Receipt.

    db 를 주면 학습된 양식도 감지에 사용하고, 알려진 양식에 안 맞는 새 영수증이면
    그 양식을 학습해 DB에 저장합니다. profile 을 주면 감지를 건너뜁니다.
    """
    image = preprocess(image_path)
    text = run_ocr(image)

    # 내장 양식 + DB에 학습된 양식을 합쳐 감지 후보로 사용.
    # rows 는 아래 '미검증 경고'에서 다시 씁니다 — 같은 테이블을 두 번 읽지 않도록.
    rows = db.load() if db is not None else []
    pool = list(PROFILES) + [Profile.from_dict(d) for d in rows]

    detected = profile if profile is not None else detect_profile(text, pool)
    receipt = parse(text, detected)

    # 자동 감지였는데 어디에도 안 맞아(GENERIC) 상호를 읽었다면 → 새 양식 학습
    if learn and profile is None and receipt.profile == GENERIC.name and receipt.store:
        learned = learn_profile(receipt)
        ok, reason = validate_profile(learned)          # ① 검증 게이트
        if not ok:
            # 범용어/문구를 양식으로 학습하면 다른 영수증까지 오탐(DB 오염)하므로 거부
            receipt.notes.append(f"새 양식 학습 거부: {reason} (상호: {learned.name!r})")
        else:
            # 유추한 양식으로 다시 파싱하면 첫 인식 결과도 개선됩니다.
            receipt = parse(text, learned)
            if db is not None and not db.has(learned.name):
                db.add(learned.to_dict(), sample_store=receipt.store,
                       status="pending")                # ② 미검증 상태로 격리
                receipt.profile = f"{learned.name} (신규 학습·미검증)"
                receipt.notes.append(
                    "새 양식을 '미검증'으로 저장했습니다. "
                    "`--review` 로 확인 후 `--approve` 하세요.")
            else:
                receipt.profile = learned.name

    # 미검증(pending) 양식으로 인식한 경우 경고 (위에서 읽어둔 rows 재사용)
    if db is not None:
        pending = {d["name"] for d in rows if d["status"] == "pending"}
        base = receipt.profile.split(" (")[0]
        if base in pending and "신규 학습" not in receipt.profile:
            receipt.notes.append(f"미검증 양식 '{base}' 으로 인식했습니다 (--review 로 확인).")

    return receipt


# ======================================================================
# 출력 & 저장
# ======================================================================
def print_receipt(r: Receipt) -> None:
    print("=" * 40)
    print(f"양식 : {r.profile or '(미상)'}")
    print(f"상호 : {r.store or '(인식 실패)'}")
    print(f"날짜 : {r.date or '(인식 실패)'}")
    print(f"카드 : {r.card or '(미확인)'}")
    print("-" * 40)
    for it in r.items:
        print(f"  {it.name:<24} {it.amount:>10,}원")
    print("-" * 40)
    print(f"합계 : {r.total:,}원" if r.total else "합계 : (인식 실패)")
    print("=" * 40)
    for note in r.notes:
        print(f"  [!] {note}")


# CSV 결과 기본 저장 폴더 (스크립트 옆 result/)
RESULT_DIR = Path(__file__).with_name("result")


def resolve_csv_path(csv_arg: str, image_path: Optional[str]) -> Path:
    """--csv 인자를 실제 저장 경로로 변환.

    - 값 없이 --csv 만: result/<이미지이름>.csv
    - 파일명만 지정   : result/<파일명>
    - 폴더 포함/절대경로: 그 경로를 그대로 사용
    """
    if csv_arg:
        p = Path(csv_arg)
        if p.parent == Path("."):        # 디렉터리 없이 파일명만 준 경우
            p = RESULT_DIR / p.name
    else:                                # --csv 만 준 경우: 이미지 이름 기반
        stem = Path(image_path).stem if image_path else "receipt"
        p = RESULT_DIR / f"{stem}.csv"
    return p


def save_csv(r: Receipt, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)   # result/ 폴더 자동 생성
    data = rows_to_csv([{
        "store": r.store, "date": r.date, "card": r.card, "total": r.total,
        "items": [{"name": i.name, "amount": i.amount} for i in r.items],
    }])
    # utf-8-sig 로 BOM 을 붙입니다(엑셀 한글). newline="" 은 csv 가 이미 넣은
    # CRLF 가 다시 변환되지 않도록.
    path.write_text(data, encoding="utf-8-sig", newline="")
    print(f"[저장 완료] {path}")


# ======================================================================
# CLI
# ======================================================================
def list_profiles(db: ProfileDB) -> None:
    """내장 + DB에 학습된 양식 목록을 출력."""
    print("[내장 양식]")
    for p in [*PROFILES, GENERIC]:
        print(f"  - {p.name:<16} layout={p.item_layout:<8} "
              f"signatures={list(p.signatures)}")
    learned = db.load()
    print(f"\n[학습된 양식] ({len(learned)}개)  @ {db.path}")
    for d in learned:
        mark = "✓" if d["status"] == "active" else "?"   # ? = 미검증(pending)
        print(f"  {mark} {d['name']:<16} layout={d['item_layout']:<8} "
              f"signatures={d['signatures']}")


def review_profiles(db: ProfileDB) -> None:
    """미검증(pending) 양식을 자세히 출력 — 승인/삭제 판단용."""
    pending = db.load(status="pending")
    if not pending:
        print("미검증 양식이 없습니다. (모두 승인됨)")
        return
    print(f"[미검증 양식] {len(pending)}개 — 오탐 위험이 없는지 확인하세요.\n")
    for d in pending:
        print(f"  이름       : {d['name']}")
        print(f"  시그니처   : {d['signatures']}   ← 이 단어가 다른 매장 영수증에도"
              f" 나오면 오탐 위험")
        print(f"  품목 배치  : {d['item_layout']}")
        print(f"  학습 출처  : {d['sample_store']}  ({d['created_at']})")
        print(f"  승인: --approve \"{d['name']}\"   |   삭제: --reject \"{d['name']}\"\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="영수증 소비내역 추출기")
    ap.add_argument("image", nargs="?", help="영수증 이미지 경로 (jpg/png)")
    ap.add_argument("--csv", nargs="?", const="", default=None,
                    help="결과를 CSV로 저장. 파일명만 주거나 생략하면 result/ 폴더에 "
                         "저장(생략 시 이미지 이름 사용), 전체 경로면 그 경로에 저장")
    ap.add_argument("--raw", action="store_true", help="OCR 원문도 출력")
    ap.add_argument("--profile", choices=["auto", *PROFILE_BY_KEY],
                    default="auto",
                    help="영수증 양식 지정 (기본 auto=자동 감지)")
    ap.add_argument("--db", default=None,
                    help="양식 DB 경로 (기본: 스크립트 옆 profiles.db)")
    ap.add_argument("--no-learn", action="store_true",
                    help="새 양식을 발견해도 DB에 추가하지 않음")
    ap.add_argument("--list-profiles", action="store_true",
                    help="저장된 양식 목록만 출력하고 종료")
    ap.add_argument("--review", action="store_true",
                    help="미검증(자동 학습) 양식을 검토용으로 출력하고 종료")
    ap.add_argument("--approve", metavar="이름",
                    help="미검증 양식을 승인(active)으로 변경")
    ap.add_argument("--reject", metavar="이름",
                    help="잘못 학습된 양식을 DB에서 삭제")
    args = ap.parse_args()

    with ProfileDB(args.db) as db:
        if args.list_profiles:
            list_profiles(db)
            return
        if args.review:
            review_profiles(db)
            return
        if args.approve:
            n = db.set_status(args.approve, "active")
            print(f"승인됨: {args.approve}" if n else f"양식을 찾을 수 없음: {args.approve}")
            return
        if args.reject:
            n = db.delete(args.reject)
            print(f"삭제됨: {args.reject}" if n else f"양식을 찾을 수 없음: {args.reject}")
            return

        if not args.image:
            ap.error("영수증 이미지 경로가 필요합니다 (또는 --list-profiles)")

        profile = None if args.profile == "auto" else PROFILE_BY_KEY[args.profile]
        receipt = extract(args.image, profile, db=db, learn=not args.no_learn)
        print_receipt(receipt)

        if args.raw:
            print("\n[OCR 원문]\n" + receipt.raw_text)
        if args.csv is not None:
            save_csv(receipt, resolve_csv_path(args.csv, args.image))


if __name__ == "__main__":
    main()