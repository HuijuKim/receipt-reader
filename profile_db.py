"""영수증 양식(프로파일) 영구 저장소 — SQLite 기반.

receipt_reader 와의 순환 import 를 피하기 위해, 이 모듈은 Profile 클래스를
모릅니다. 프로파일을 아래 스키마의 dict 형태로만 주고받습니다.

프로파일 dict 스키마:
    {
        "name":                 str,        # 양식(매장) 이름 · 기본키
        "signatures":           list[str],  # 자동 감지용 키워드
        "item_layout":          str,        # "inline" | "two_line"
        "extra_total_keywords": list[str],
        "extra_skip_keywords":  list[str],
        "date_pattern":         str | None, # 이 양식 전용 날짜 정규식(없으면 None)
    }
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# 기본 DB 위치: 이 스크립트와 같은 폴더의 profiles.db
DEFAULT_DB_PATH = Path(__file__).with_name("profiles.db")


class ProfileDB:
    """학습된 영수증 양식을 저장/조회하는 SQLite 래퍼."""

    def __init__(self, path: Optional[str | Path] = None) -> None:
        self.path = str(path or DEFAULT_DB_PATH)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                name                 TEXT PRIMARY KEY,
                signatures           TEXT NOT NULL DEFAULT '[]',
                item_layout          TEXT NOT NULL DEFAULT 'inline',
                extra_total_keywords TEXT NOT NULL DEFAULT '[]',
                extra_skip_keywords  TEXT NOT NULL DEFAULT '[]',
                date_pattern         TEXT,
                sample_store         TEXT,
                status               TEXT NOT NULL DEFAULT 'pending',
                created_at           TEXT
            )
            """
        )
        # 기존 DB(구 스키마) 마이그레이션: 없는 컬럼을 추가
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(profiles)")}
        if "date_pattern" not in cols:
            self._conn.execute("ALTER TABLE profiles ADD COLUMN date_pattern TEXT")
        if "status" not in cols:
            self._conn.execute(
                "ALTER TABLE profiles ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
        self._conn.commit()

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def load(self, status: Optional[str] = None) -> list[dict]:
        """저장된 프로파일을 dict 목록으로 반환. status 를 주면 그 상태만."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM profiles WHERE status = ? ORDER BY created_at",
                (status,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM profiles ORDER BY created_at").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def has(self, name: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM profiles WHERE name = ?", (name,)
        )
        return cur.fetchone() is not None

    # ------------------------------------------------------------------
    # 추가/갱신
    # ------------------------------------------------------------------
    def add(self, profile: dict, sample_store: Optional[str] = None,
            status: str = "pending") -> None:
        """프로파일을 저장(같은 이름이면 갱신).

        status: 'pending'(자동 학습 · 미검증) | 'active'(사용자 승인됨)
        """
        self._conn.execute(
            """
            INSERT OR REPLACE INTO profiles
                (name, signatures, item_layout,
                 extra_total_keywords, extra_skip_keywords,
                 date_pattern, sample_store, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile["name"],
                json.dumps(profile.get("signatures", []), ensure_ascii=False),
                profile.get("item_layout", "inline"),
                json.dumps(profile.get("extra_total_keywords", []), ensure_ascii=False),
                json.dumps(profile.get("extra_skip_keywords", []), ensure_ascii=False),
                profile.get("date_pattern"),
                sample_store,
                status,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self._conn.commit()

    def set_status(self, name: str, status: str) -> int:
        """프로파일 상태 변경('pending' → 'active' 승인 등). 변경된 행 수 반환."""
        cur = self._conn.execute(
            "UPDATE profiles SET status = ? WHERE name = ?", (status, name))
        self._conn.commit()
        return cur.rowcount

    def delete(self, name: str) -> int:
        """이름으로 프로파일 삭제. 삭제된 행 수 반환."""
        cur = self._conn.execute("DELETE FROM profiles WHERE name = ?", (name,))
        self._conn.commit()
        return cur.rowcount

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_dict(r: sqlite3.Row) -> dict:
        return {
            "name": r["name"],
            "signatures": json.loads(r["signatures"]),
            "item_layout": r["item_layout"],
            "extra_total_keywords": json.loads(r["extra_total_keywords"]),
            "extra_skip_keywords": json.loads(r["extra_skip_keywords"]),
            "date_pattern": r["date_pattern"],
            # 아래는 관리용 메타(Profile.from_dict 은 무시함)
            "status": r["status"],
            "sample_store": r["sample_store"],
            "created_at": r["created_at"],
        }

    def close(self) -> None:
        self._conn.close()

    # with 문 지원
    def __enter__(self) -> "ProfileDB":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
