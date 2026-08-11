"""CSV 출력 형식 — 한 곳에만 둡니다.

세 곳이 같은 형식을 써야 합니다:
  - PC CLI            receipt_reader.py --csv  (result/ 폴더에 저장)
  - 서버              GET /receipts.csv        (앱이 올린 내역 전체)
  - 안드로이드 앱     Export.kt                (폰 안의 내역)

앱은 폰에서 오프라인으로도 내보낼 수 있어야 해 별도 구현이 불가피하지만,
파이썬 쪽 둘은 여기를 함께 씁니다. 형식이 갈라지면 두 파일을 이어붙일 수
없게 되므로 열 구성을 바꿀 때는 Export.kt 도 같이 고쳐야 합니다.
"""
from __future__ import annotations

import csv
import io

CSV_HEADER = ["상호", "날짜", "카드", "품목", "금액"]

# 엑셀은 BOM 없는 UTF-8 CSV 를 시스템 인코딩으로 읽어 한글을 깨뜨립니다.
BOM = "﻿"


def rows_to_csv(receipts: list[dict]) -> str:
    """영수증 dict 목록 → CSV 문자열 (BOM 없음).

    영수증마다 품목 행들을 쓰고 마지막에 합계 행을 붙입니다.
    """
    buf = io.StringIO(newline="")
    w = csv.writer(buf)                      # 기본 excel 방언 → 줄바꿈 CRLF
    w.writerow(CSV_HEADER)
    for r in receipts:
        for item in r.get("items") or []:
            w.writerow([r.get("store"), r.get("date"), r.get("card"),
                        item["name"], item["amount"]])
        w.writerow([r.get("store"), r.get("date"), r.get("card"),
                    "합계", r.get("total")])
    return buf.getvalue()
