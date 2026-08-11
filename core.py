"""공통 기반 모듈 — 데이터 구조 / 정규식 / 키워드.

순환 import 를 피하기 위해, 다른 모듈(ocr/issuer/parser)이 공통으로 쓰는
데이터 구조와 상수를 여기 한 곳에 모읍니다. 이 모듈은 아무것도 import 하지
않습니다(표준 라이브러리 제외).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ======================================================================
# 공통 정규식
# ======================================================================
# 금액: 1,000 / 12.500 처럼 천 단위 구분자(콤마 또는 점)가 있는 숫자.
#   ※ OCR에 따라 구분자를 '.'로 읽는 경우가 많아 둘 다 허용합니다.
PRICE_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})+")
# 1,000원 미만 금액 (봉투값 100원 등)은 구분자가 없어 PRICE_RE 로 잡히지 않습니다.
#   그렇다고 맨 정수를 다 금액으로 보면 품번·수량·번지수까지 걸리므로,
#   '수량 금액' 꼴로 줄이 끝날 때만 인정합니다.
#     "002 NP 종이쇼핑백(중) 1 100"  → 100  (수량 1, 금액 100)
#     "경기 용인시 강남동로 100번길 5" → 매칭 안 됨 (앞이 수량 자리가 아님)
#   앞의 (?<!\d) 는 긴 숫자의 꼬리를 수량으로 오인하지 않게 합니다.
QTY_SMALL_PRICE_RE = re.compile(r"(?<!\d)\d{1,2}\s+(\d{1,3})\s*$")
# 바코드/사업자 등 6자리 이상 연속 숫자
BARCODE_RE = re.compile(r"\d{6,}")
# 대괄호로 감싼 단가 표기 (예: "[2.150]") — 품목명/금액 판정에서 제거용
BRACKET_PRICE_RE = re.compile(r"\[[^\]]*\]")
# 한글 한 글자 (상호명 후보 판별용)
KOREAN_RE = re.compile(r"[가-힣]")
# 사업자등록번호 123-45-67890 (상호는 보통 이 번호와 같은/직전 줄에 있음)
BIZ_RE = re.compile(r"\d{3}-\d{2}-\d{5}")
# 기본 날짜: 2025-01-03, 2025.01.03, 2025년 1월 3일 등
DEFAULT_DATE_PATTERN = r"(20\d{2})\s*[.\-/년]\s*(\d{1,2})\s*[.\-/월]\s*(\d{1,2})"
DATE_RE = re.compile(DEFAULT_DATE_PATTERN)
# 미국식 날짜 07/09/2026 (MM/DD/YYYY) — 코스트코 등에서 사용.
#   연도-우선 패턴이 안 맞을 때만 보조로 씁니다.
DATE_US_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")


def strip_money(ln: str) -> str:
    """바코드와 대괄호 단가를 지운 나머지 — 금액 판정의 기준 문자열.

    파싱(parser)과 양식 학습(issuer)이 '금액이 있는 줄'을 같은 기준으로 봐야
    학습한 레이아웃과 실제 파싱이 어긋나지 않으므로 여기 한 곳에 둡니다.
    """
    return BRACKET_PRICE_RE.sub(" ", BARCODE_RE.sub(" ", ln))


# ======================================================================
# 공통 키워드 (모든 양식이 기본으로 상속)
# ======================================================================
BASE_TOTAL_KEYWORDS = ["합계", "합 계", "총액", "총 액", "결제금액",
                       "받을금액", "판매금액", "합계금액", "결 제"]
BASE_SKIP_KEYWORDS = ["부가세", "면세", "과세", "카드", "승인", "할부",
                      "잔액", "포인트", "사업자", "대표자", "전화", "TEL",
                      "거스름", "받은금액", "현금", "사용금액",
                      "COUPON", "상품수", "소계", "잔돈", "거래구분",
                      # 영수증 머리말/요약 잡줄 (특히 코스트코)
                      "VAT", "PRESCAN", "종료", "BASKET", "BEGIN", "COUNT",
                      "MEMBER", "WHOLESALE", "만료"]

# 통째로 잡줄인 줄 (소문자로 비교) — 품목으로도, 이름 후보로도 쓰지 않습니다.
JUNK_LINES = {"판매", "corco", "costco", "cpn", "in", "wholesale", "a", "rn"}

# 품목명으로 보기엔 너무 긴 줄(하단 안내/마케팅 문구)을 걸러낼 기준
MAX_ITEM_NAME_LEN = 40

# 상호/시그니처로 쓰면 안 되는 범용어(문서 제목·정책 문구·요약 줄).
#   → 상호 감지에서 이런 단어가 든 줄은 건너뛰고, 학습 시그니처에서도 배제합니다.
STORE_STOPWORDS = ["영수증", "반품", "교환", "환불", "지참", "정부방침",
                   "상품명", "고객", "전표", "포인트", "적립", "할부",
                   "승인", "매입", "가맹", "단말기", "전자", "서명",
                   "합계", "금액", "수량", "과세", "면세", "부가세",
                   "결제", "판매", "취소", "공급",
                   # 라벨 성격의 머리말 — 상호가 아님
                   "사업자", "대표", "주소", "TEL", "번호", "소득공제", "매장"]

# 주소로 보이는 줄 — 상호가 아니므로 제외 (예: "경기 화성 시청로 113")
#   (1) '…로/길/번길/대로 + 숫자' 도로명   (2) 시·도 이름으로 시작
ADDRESS_RE = re.compile(
    r"(로|길|번길|대로)\s*\d"
    r"|^\s*(서울|경기|인천|부산|대구|광주|대전|울산|세종|강원|충북|충남|전북|전남"
    r"|경북|경남|제주|서울특별시|경기도|강원도|충청북도|충청남도|전라북도|전라남도"
    r"|경상북도|경상남도|제주특별자치도)\b"
)

# ======================================================================
# 카드사 / 결제수단 목록  ── 한국에서 유효한 것만 인정 (그 외는 미확인)
# ======================================================================
# {정식 명칭: (OCR 텍스트에 나타날 수 있는 별칭들 · 소문자로 비교)}
#   새 카드사를 지원하려면 여기에 한 줄만 추가하면 됩니다.
CARD_ISSUERS: dict[str, tuple[str, ...]] = {
    "신한카드":    ("신한",),
    "삼성카드":    ("삼성",),
    "현대카드":    ("현대",),
    "KB국민카드":  ("국민", "kb"),
    "롯데카드":    ("롯데",),
    "우리카드":    ("우리",),
    "하나카드":    ("하나", "외환"),
    "BC카드":      ("비씨", "bc"),
    "NH농협카드":  ("농협", "nh"),
    "씨티카드":    ("씨티", "citi"),
    "수협카드":    ("수협",),
    "전북카드":    ("전북",),
    "광주카드":    ("광주",),
    "제주카드":    ("제주",),
    "카카오뱅크":  ("카카오뱅크",),
    "케이뱅크":    ("케이뱅크",),
    "토스뱅크":    ("토스뱅크",),
    "IBK기업은행": ("ibk", "기업은행"),
    "우체국":      ("우체국",),
    "새마을금고":  ("새마을",),
    "신협":        ("신협",),
    "코나카드":    ("코나",),
}

# 간편결제 (카드사와 별개) — 카드사보다 먼저 검사합니다("삼성페이" vs "삼성카드").
PAY_SERVICES: dict[str, tuple[str, ...]] = {
    "카카오페이":  ("카카오페이",),
    "네이버페이":  ("네이버페이", "npay"),
    "삼성페이":    ("삼성페이",),
    "애플페이":    ("애플페이", "applepay"),
    "페이코":      ("페이코", "payco"),
    "제로페이":    ("제로페이",),
    "토스페이":    ("토스페이",),
    "SSG페이":     ("ssg페이", "ssgpay"),
    "스마일페이":  ("스마일페이",),
    "쿠페이":      ("쿠페이",),
}

# 국제 브랜드 — 발급사와 함께 표기됨 (예: "현대VISA" → 현대카드(VISA))
CARD_BRANDS = ("VISA", "MASTER", "AMEX", "JCB", "UNIONPAY", "은련")

# --- 카드 문자열 추출 패턴 ---------------------------------------------
# (1) 라벨 기반: "카드종류: 현대VISA", "[카드 사명] 롯데카드", "(매입사:국민카드)"
CARD_LABEL_RE = re.compile(
    r"(?:카드\s*종류|카드\s*사명|매입\s*사명|매입사|결제\s*수단)\s*[:\]\s]*([^\s:\]]{2,20})")
# (2) "○○카드" 형태 (라벨이 없을 때) — 위 별칭 목록에서 자동 생성
_ISSUER_ALIASES = sorted(
    {a for aliases in CARD_ISSUERS.values() for a in aliases}, key=len, reverse=True)
CARD_ISSUER_RE = re.compile(
    rf"({'|'.join(re.escape(a) for a in _ISSUER_ALIASES)})\s*카드", re.IGNORECASE)


def _alias_hit(alias: str, s: str) -> bool:
    """별칭이 문자열 안에 '독립적으로' 나타나는지.

    영문 별칭(bc, kb 등)은 다른 영숫자에 묻힌 경우를 배제합니다.
    (예: "abcd1234" 안의 'bc' 는 BC카드가 아님)
    """
    if alias.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", s) is not None
    return alias in s


def normalize_card(raw: Optional[str]) -> Optional[str]:
    """OCR에서 뽑은 카드 문자열을 위 목록의 정식 명칭으로 변환.

    목록에 없으면 None(=미확인)을 반환합니다. OCR이 깨진 값("호코나" 등)이
    그대로 결과에 나가는 것을 막기 위함입니다.
    """
    if not raw:
        return None
    s = raw.strip(" :]()[.,-*").lower()
    if not s:
        return None
    for canon, aliases in PAY_SERVICES.items():      # 간편결제 우선
        if any(_alias_hit(a, s) for a in aliases):
            return canon
    for canon, aliases in CARD_ISSUERS.items():
        if any(_alias_hit(a, s) for a in aliases):
            brand = next((b for b in CARD_BRANDS if _alias_hit(b.lower(), s)), None)
            return f"{canon}({brand})" if brand else canon
    return None

# 시그니처로 쓰면 위험한 지역명 (다른 매장 영수증에도 흔히 등장)
GEO_TOKENS = {"서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산",
              "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남",
              "제주", "한국", "코리아"}


# ======================================================================
# 데이터 구조
# ======================================================================
@dataclass
class LineItem:
    name:   str     # 품목명
    amount: int     # 금액(원)


@dataclass
class Receipt:
    store:  Optional[str] = None            # 상호명
    date:   Optional[str] = None            # 구매일 (YYYY-MM-DD)
    items:  list[LineItem] = field(default_factory=list)
    total:  Optional[int] = None            # 합계/결제금액
    card:   Optional[str] = None            # 카드/결제수단 (예: 현대VISA, 카카오페이)
    profile: str = ""                       # 인식에 사용된 양식(발행처) 이름
    notes:  list[str] = field(default_factory=list)  # 경고/알림(학습 거부, 미검증 양식 등)
    raw_text: str = ""                      # OCR 원문(디버깅용)


@dataclass(frozen=True)
class Profile:
    """하나의 영수증 양식(발행처)에 대한 파싱 규칙.

    대부분의 매장은 이 규칙 데이터만으로 처리됩니다(공용 파서 엔진).
    아주 특이한 매장은 parsers/<매장>.py 에 전용 파서를 등록해 오버라이드합니다.

    필드:
      name         : 양식(매장) 이름 · 표시/식별용
      signatures   : 이 양식을 식별하는 키워드(OCR 텍스트에 나타나면 감지)
      item_layout  : "inline"=한 줄에 이름+금액 / "two_line"=이름 줄 따로
      extra_*      : 이 양식에만 추가할 합계/제외 키워드
      date_pattern : 이 양식 전용 날짜 정규식(없으면 기본 DATE_RE 사용)
    """
    name: str
    signatures: tuple[str, ...] = ()
    item_layout: str = "inline"
    extra_total_keywords: tuple[str, ...] = ()
    extra_skip_keywords: tuple[str, ...] = ()
    date_pattern: Optional[str] = None

    def score(self, text: str) -> int:
        """OCR 텍스트에 이 양식의 시그니처가 몇 개나 나타나는지 (감지 점수)."""
        low = text.lower()
        return sum(1 for s in self.signatures if s.lower() in low)

    @property
    def total_keywords(self) -> list[str]:
        return BASE_TOTAL_KEYWORDS + list(self.extra_total_keywords)

    @property
    def skip_keywords(self) -> list[str]:
        return BASE_SKIP_KEYWORDS + list(self.extra_skip_keywords)

    @property
    def date_regex(self) -> re.Pattern:
        return re.compile(self.date_pattern) if self.date_pattern else DATE_RE

    # --- DB(dict) 직렬화 -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "signatures": list(self.signatures),
            "item_layout": self.item_layout,
            "extra_total_keywords": list(self.extra_total_keywords),
            "extra_skip_keywords": list(self.extra_skip_keywords),
            "date_pattern": self.date_pattern,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        return cls(
            name=d["name"],
            signatures=tuple(d.get("signatures", [])),
            item_layout=d.get("item_layout", "inline"),
            extra_total_keywords=tuple(d.get("extra_total_keywords", [])),
            extra_skip_keywords=tuple(d.get("extra_skip_keywords", [])),
            date_pattern=d.get("date_pattern"),
        )
