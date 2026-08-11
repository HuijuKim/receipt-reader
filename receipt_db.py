"""인식된 영수증 내역 저장소 — SQLite 기반.

양식(profiles.db)과 달리 여기에는 '영수증 자체'가 쌓입니다. 앱이 폰에 저장한
내역을 올려두는 곳이라, 폰을 바꾸거나 앱을 지워도 기록이 남습니다.

중복 방지:
    앱은 폰마다 한 번 만든 device_id 와 폰 DB 의 행 번호(client_id)를 함께
    보냅니다. 이 둘을 묶어 기본키로 쓰므로, 같은 내역을 몇 번 올려도
    쌓이지 않고 갱신만 됩니다(멱등). 앱이 '무엇을 이미 보냈는지' 기억할
    필요가 없어집니다.

영수증 dict 스키마 (server.py 의 API 와 1:1):
    {
        "client_id": int,        # 폰 DB 의 행 번호
        "store": str | None,
        "date":  str | None,     # YYYY-MM-DD
        "card":  str | None,
        "total": int | None,
        "profile": str,
        "items": [{"name": str, "amount": int}, ...],
        "notes": list[str],
        "saved_at": int,         # 폰에서 저장한 시각 (epoch millis)
    }
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# 기본 DB 위치: 이 스크립트와 같은 폴더의 receipts.db
DEFAULT_DB_PATH = Path(__file__).with_name("receipts.db")


class ReceiptDB:
    """업로드된 영수증 내역을 저장/조회하는 SQLite 래퍼."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = str(path or DEFAULT_DB_PATH)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS receipts (
                device_id   TEXT NOT NULL,
                client_id   INTEGER NOT NULL,
                store       TEXT,
                date        TEXT,
                card        TEXT,
                total       INTEGER,
                profile     TEXT NOT NULL DEFAULT '',
                items       TEXT NOT NULL DEFAULT '[]',
                notes       TEXT NOT NULL DEFAULT '[]',
                saved_at    INTEGER NOT NULL DEFAULT 0,
                uploaded_at TEXT,
                PRIMARY KEY (device_id, client_id)
            )
            """
        )
        # 날짜순 조회가 기본이라 인덱스를 하나 둡니다.
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date)")
        self._conn.commit()

    # ------------------------------------------------------------------
    # 저장
    # ------------------------------------------------------------------
    def upsert_many(self, device_id: str, receipts: list[dict]) -> int:
        """여러 건을 저장(같은 device_id+client_id 면 갱신). 처리한 건수를 반환."""
        now = datetime.now().isoformat(timespec="seconds")
        rows = [
            (
                device_id,
                int(r["client_id"]),
                r.get("store"),
                r.get("date"),
                r.get("card"),
                r.get("total"),
                r.get("profile") or "",
                json.dumps(r.get("items") or [], ensure_ascii=False),
                json.dumps(r.get("notes") or [], ensure_ascii=False),
                int(r.get("saved_at") or 0),
                now,
            )
            for r in receipts
        ]
        self._conn.executemany(
            """
            INSERT INTO receipts (device_id, client_id, store, date, card, total,
                                  profile, items, notes, saved_at, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id, client_id) DO UPDATE SET
                store=excluded.store, date=excluded.date, card=excluded.card,
                total=excluded.total, profile=excluded.profile,
                items=excluded.items, notes=excluded.notes,
                saved_at=excluded.saved_at, uploaded_at=excluded.uploaded_at
            """,
            rows,
        )
        self._conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def load(self, device_id: Optional[str] = None) -> list[dict]:
        """저장된 내역을 최근 구매일 순으로. device_id 를 주면 그 기기 것만."""
        sql = "SELECT * FROM receipts"
        params: tuple = ()
        if device_id:
            sql += " WHERE device_id = ?"
            params = (device_id,)
        sql += " ORDER BY date DESC, saved_at DESC"
        return [self._row_to_dict(r) for r in self._conn.execute(sql, params)]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]

    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict:
        return {
            "device_id": r["device_id"],
            "client_id": r["client_id"],
            "store": r["store"],
            "date": r["date"],
            "card": r["card"],
            "total": r["total"],
            "profile": r["profile"],
            "items": json.loads(r["items"]),
            "notes": json.loads(r["notes"]),
            "saved_at": r["saved_at"],
            "uploaded_at": r["uploaded_at"],
        }

    def close(self) -> None:
        self._conn.close()

    # with 문 지원
    def __enter__(self) -> "ReceiptDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
