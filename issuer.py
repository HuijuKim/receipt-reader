"""발행처(매장) 식별 + 내장 양식 + 새 양식 자동 학습.

영수증은 보통 자주 가는 몇 곳에서만 받으므로, "먼저 어디서 발행됐는지"를
식별한 뒤 그 양식 규칙으로 나머지를 읽습니다. 이 모듈이 그 '식별' 단계를
담당합니다. 실제 필드 추출은 parser.py 가 합니다.
"""
from __future__ import annotations

import re
from typing import Optional

from core import (ADDRESS_RE, BARCODE_RE, BASE_SKIP_KEYWORDS,
                  BASE_TOTAL_KEYWORDS, BRACKET_PRICE_RE, GEO_TOKENS, KOREAN_RE,
                  PRICE_RE, STORE_STOPWORDS, Profile, Receipt, strip_money)


# ======================================================================
# 내장 양식
# ======================================================================
# 아무 양식에도 해당하지 않을 때 쓰는 일반(폴백) 프로파일.
GENERIC = Profile(name="일반")

# 매장별 내장 프로파일. 감지 점수가 가장 높은 것을 선택합니다.
#   ※ 'signatures'에는 OCR이 자주 틀리는 표기(예: 이마트→미마트)도 넣으면
#      감지가 더 안정적입니다.
PROFILES: list[Profile] = [
    Profile(
        name="이마트/신세계",
        signatures=("이마트", "미마트", "emart", "e-mart", "e·mart",
                    "노브랜드", "트레이더스", "신세계"),
        item_layout="two_line",
    ),
]

# --profile 옵션으로 수동 지정할 때 쓰는 키 → 프로파일 매핑
PROFILE_BY_KEY: dict[str, Profile] = {
    "generic": GENERIC,
    "emart": PROFILES[0],
}


# ======================================================================
# 발행처 감지
# ======================================================================
def detect_profile(text: str, profiles: Optional[list[Profile]] = None) -> Profile:
    """OCR 텍스트를 보고 가장 잘 맞는 양식을 고릅니다. 없으면 GENERIC.

    profiles 를 주면 (내장 + DB 학습분) 그 목록에서 감지합니다.
    """
    pool = PROFILES if profiles is None else profiles
    # (점수, 양식) 한 번만 계산 — score() 는 내부에서 원문을 소문자화하므로
    # 승자를 다시 채점하면 OCR 원문을 한 번 더 복사하게 됩니다.
    scored = max(((p.score(text), p) for p in pool), key=lambda t: t[0], default=None)
    if scored is not None and scored[0] > 0:
        return scored[1]
    return GENERIC


# ======================================================================
# 새 양식 자동 학습
# ======================================================================
def _looks_like_name_line(ln: str) -> bool:
    """금액 없이 한글 이름만 있는 줄인지 (two_line 양식의 이름 줄 후보)."""
    residual = strip_money(ln)
    return len(KOREAN_RE.findall(residual)) >= 2 and not PRICE_RE.search(residual)


def _guess_layout(lines: list[str]) -> str:
    """품목 레이아웃 추정. '금액이 있는 줄'을 기준으로:
      - 그 줄 자체에 한글 이름이 있으면 inline
      - 이름이 위쪽 별도 줄에 있으면 two_line
    """
    skip_kw = BASE_TOTAL_KEYWORDS + BASE_SKIP_KEYWORDS
    two = inline = 0
    for i, ln in enumerate(lines):
        if any(k in ln for k in skip_kw):
            continue
        residual = strip_money(ln)
        if not PRICE_RE.search(residual):        # 금액 있는 줄만 기준으로
            continue
        name_part = PRICE_RE.sub("", residual)
        if len(KOREAN_RE.findall(name_part)) >= 2:
            inline += 1
        elif any(_looks_like_name_line(p) for p in lines[max(0, i - 2):i]):
            two += 1
    return "two_line" if two > inline else "inline"


def _is_generic(token: str) -> bool:
    """상호/시그니처로 부적절한 범용어인지 (대소문자 무시)."""
    low = token.lower()
    return any(w.lower() in low for w in STORE_STOPWORDS)


# 법인격/범용 표기 — 시그니처로 쓰면 남의 영수증까지 매칭되므로 제외.
CORP_TOKENS = {"(주)", "㈜", "(유)", "주식회사", "유한회사", "주식", "코리아",
               "korea", "co", "ltd", "inc"}


def _usable_token(t: str) -> bool:
    """시그니처로 쓸 만큼 '특정적'인 토큰인지."""
    core = re.sub(r"[^\w가-힣]", "", t)          # 괄호 등 기호 제거
    if not core or core.lower() in CORP_TOKENS or t.lower() in CORP_TOKENS:
        return False
    if core.isdigit():                           # 순수 숫자(예: "113") 제외
        return False
    if core in GEO_TOKENS:                       # 지역명(예: "경기") 제외
        return False
    if _is_generic(t):
        return False
    # 한글 2자 이상 또는 영숫자 3자 이상이어야 특정적이라고 봅니다.
    return len(KOREAN_RE.findall(core)) >= 2 or len(core) >= 3


def validate_profile(p: Profile) -> tuple[bool, str]:
    """학습 전 검증 — DB 오염(범용 시그니처가 남의 영수증까지 매칭)을 막습니다.

    반환: (통과 여부, 거부 사유)
    """
    name = (p.name or "").strip()
    if len(name) < 2:
        return False, "상호가 너무 짧음"
    if len(name) > 40:
        return False, "상호가 너무 김 (안내 문구로 추정)"
    if name.startswith("["):
        return False, "문서 제목으로 추정"
    if ADDRESS_RE.search(name):
        return False, "주소로 추정 (상호가 아님)"
    if _is_generic(name):
        return False, "상호에 범용어 포함 (라벨/문구로 추정)"
    if not p.signatures:
        return False, "식별 가능한 시그니처 없음"
    # 최소 하나는 충분히 특정적이어야 함 (한글 2자 이상 또는 영숫자 3자 이상)
    specific = any(
        len(KOREAN_RE.findall(s)) >= 2 or len(re.sub(r"\W", "", s)) >= 3
        for s in p.signatures
    )
    if not specific:
        return False, "시그니처가 너무 일반적"
    return True, ""


def learn_profile(receipt: Receipt) -> Profile:
    """알려진 양식에 안 맞은 영수증에서 새 양식을 유추합니다.

    - 이름/시그니처: 상호명과 그 안의 2글자 이상 토큰(브랜드명 등)
      단, "영수증/반품/합계" 같은 범용어는 시그니처에서 제외해 오탐(DB 오염)을 막습니다.
    - 레이아웃: OCR 원문의 품목 배치를 보고 추정
    """
    store = (receipt.store or "").strip()
    tokens = [t for t in re.split(r"\s+", store) if _usable_token(t)]
    # 상호 전체(가장 특정적) + 쓸 만한 토큰. 중복 제거.
    candidates = [store, *tokens] if store and not _is_generic(store) else tokens
    signatures = tuple(dict.fromkeys(
        s for s in candidates if s == store or _usable_token(s)
    ))
    lines = [ln.strip() for ln in receipt.raw_text.splitlines() if ln.strip()]
    return Profile(
        name=store or "미상 양식",
        signatures=signatures,
        item_layout=_guess_layout(lines),
    )
