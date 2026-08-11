"""파싱 엔진 — 양식(Profile) 규칙으로 상호/날짜/합계/품목을 추출.

하이브리드 구조:
  - 기본: 아래 parse_generic() 이 Profile 의 규칙(레이아웃/키워드/날짜정규식)을
          읽어 대부분의 매장을 처리합니다. (DB로 무코드 확장)
  - 예외: 아주 특이한 매장은 parsers/<매장>.py 에서 @register_parser 로 전용
          파서를 등록하면, 그 매장에 한해 전용 로직이 우선 적용됩니다.
"""
from __future__ import annotations

import re
from typing import Callable

from core import (ADDRESS_RE, BARCODE_RE, BIZ_RE, BRACKET_PRICE_RE,
                  CARD_ISSUER_RE, CARD_LABEL_RE, DATE_US_RE, JUNK_LINES,
                  KOREAN_RE, MAX_ITEM_NAME_LEN, PAY_SERVICES, PRICE_RE,
                  QTY_SMALL_PRICE_RE, STORE_STOPWORDS, LineItem, Profile,
                  Receipt, normalize_card, strip_money)


def _has_skip(ln: str, keywords: list[str]) -> bool:
    """제외 키워드 포함 여부 (대소문자 무시)."""
    low = ln.lower()
    return any(k.lower() in low for k in keywords)


def _is_junk_line(ln: str) -> bool:
    return ln.strip().lower() in JUNK_LINES


def _valid_item_name(name: str) -> bool:
    """품목명으로 인정할 만한지 — 한글 1자 이상 또는 영문 3자 이상."""
    if _is_junk_line(name):
        return False
    if len(KOREAN_RE.findall(name)) >= 1:
        return True
    return len(re.findall(r"[A-Za-z]", name)) >= 3


# ======================================================================
# 매장별 전용 파서 레지스트리 (하이브리드)
# ======================================================================
CUSTOM_PARSERS: dict[str, Callable[[str, Profile], Receipt]] = {}


def register_parser(name: str):
    """특정 양식 이름에 전용 파서를 등록하는 데코레이터.

    사용 예 (parsers/some_store.py):
        from parser import register_parser, parse_generic
        @register_parser("특이마트")
        def parse(text, profile):
            r = parse_generic(text, profile)   # 공용 결과에서 시작해
            ...                                 # 이 매장만의 보정 추가
            return r
    """
    def deco(fn: Callable[[str, Profile], Receipt]):
        CUSTOM_PARSERS[name] = fn
        return fn
    return deco


# ======================================================================
# 공용 유틸
# ======================================================================
def _to_int(s: str) -> int:
    # 천 단위 구분자(콤마/점)와 공백 제거 후 정수화
    return int(re.sub(r"[.,\s]", "", s))


def _clean_name(s: str) -> str:
    """줄에서 바코드/금액/대괄호단가/앞 품번을 제거해 품목명만 남깁니다."""
    s = strip_money(s)                        # 바코드 + [2.150] 같은 단가 표기
    s = PRICE_RE.sub(" ", s)                  # 금액 제거
    s = QTY_SMALL_PRICE_RE.sub(" ", s)        # 뒤쪽 '수량 금액'(소액) 제거
    s = re.sub(r"^\s*\d{1,3}\s*", "", s)      # 앞쪽 품번(001 등) 제거
    s = re.sub(r"\s+\d{1,2}\s*$", "", s)      # 뒤쪽 수량(예: "…프랑크 1") 제거
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" -|:*\t.")


def _has_money(ln: str) -> bool:
    """줄에 (바코드/대괄호단가를 제외한) 실제 금액이 있는지."""
    return bool(PRICE_RE.search(strip_money(ln)))


def _line_amount(ln: str, residual: str) -> int | None:
    """줄에서 금액을 뽑습니다. 금액으로 볼 게 없으면 None.

    구분자 있는 금액(12,500)이 가장 확실하고, 없을 때만 줄 모양으로 복구합니다.
    복구 규칙은 서로 배타적인 두 가지입니다 — 바코드 줄의 순수 숫자열, 그리고
    '수량 금액' 으로 끝나는 소액 줄.
    """
    if hits := list(PRICE_RE.finditer(residual)):
        last = hits[-1]
        amount = _to_int(last.group())
        # 금액 바로 뒤에 '-'가 붙으면 쿠폰/환불(음수). 예: "16,000-T"
        return -amount if residual[last.end():last.end() + 1] == "-" else amount

    if BARCODE_RE.search(ln) and not re.search(r"[A-Za-z가-힣]", residual):
        # 바코드 줄인데 구분자 금액이 없고(예: 500/750) 남은 게 순수 숫자열일
        # 때만 마지막 2~4자리 정수를 금액으로. → 거래번호/CASHIER 등 메타 줄 배제.
        bare = re.findall(r"\d{2,4}", residual)
        return int(bare[-1]) if bare else None

    if (m := QTY_SMALL_PRICE_RE.search(residual)) and not ADDRESS_RE.search(ln):
        # 1,000원 미만 품목(봉투값 등) — '수량 금액' 으로 끝나는 줄에서만.
        # 주소는 "…로 100번길 5" 처럼 같은 꼴이 될 수 있어 따로 배제합니다.
        return int(m.group(1))

    return None


# ---- 상호명 감지 ------------------------------------------------------
def _looks_like_store(ln: str) -> bool:
    """상호명 후보로 볼 만한 줄인지 (문서제목/정책문구/주소/요약 줄 제외)."""
    t = ln.strip()
    if t.startswith("["):                     # [반품 영수증] 같은 문서 제목
        return False
    if ADDRESS_RE.search(t):                  # 주소는 상호가 아님
        return False
    if len(KOREAN_RE.findall(t)) < 2 and not re.search(r"[A-Za-z]{2,}", t):
        return False
    return not _has_skip(t, STORE_STOPWORDS)  # 라벨/문구 줄 제외 (대소문자 무시)


def _clean_store(ln: str) -> str:
    """상호 줄에서 상호만 뽑아냅니다.

    사업자번호를 기준으로 줄을 나눈 뒤, '상호다운' 조각을 고릅니다.
    영수증이 접혀 칼럼이 붙으면 상호가 번호 뒤에 올 수도 있어(예:
    "사업자번호: 582-64-00519들온정(구성점)") 앞/뒤를 모두 검사합니다.
    라벨(사업자/대표/TEL...)만 있는 조각은 버립니다.
    """
    segs = BIZ_RE.split(ln) if BIZ_RE.search(ln) else [ln]
    best = ""
    for seg in segs:
        s = BARCODE_RE.sub(" ", seg)                 # 10자리 등 번호 제거
        s = re.sub(r"\s{2,}", " ", s).strip(" -|:*\t\"'")
        if len(s) < 2:
            continue
        if _has_skip(s, STORE_STOPWORDS):            # 라벨/문구 조각 제외(대소문자 무시)
            continue
        if ADDRESS_RE.search(s):                     # 주소 조각 제외
            continue
        if len(KOREAN_RE.findall(s)) < 2 and not re.search(r"[A-Za-z]{2,}", s):
            continue
        if len(s) > len(best):
            best = s
    return best


# ---- 카드/결제수단 감지 -----------------------------------------------
def _detect_card(text: str) -> str | None:
    """카드/결제수단 추정. 결과는 항상 core 의 카드사 목록으로 정규화되며,
    목록에 없는(=OCR이 깨진) 값이면 None(미확인)을 돌려줍니다.

    (1) 라벨 기반  : "카드종류: 현대VISA", "[카드 사명] 롯데카드", "(매입사:국민카드)"
    (2) "○○카드"   : "우리카드:4902***"
    (3) 간편결제   : "카카오페이"
    """
    if m := CARD_LABEL_RE.search(text):
        if v := normalize_card(m.group(1)):
            return v
    if m := CARD_ISSUER_RE.search(text):
        if v := normalize_card(m.group(0)):
            return v
    low = text.lower()
    for canon, aliases in PAY_SERVICES.items():
        if any(a in low for a in aliases):
            return canon
    return None


def _same_store(detected: str, canonical: str) -> bool:
    """OCR로 읽은 상호가 양식의 정식 상호와 같은 매장으로 볼 수 있는지.

    - 한쪽이 다른 쪽의 부분 문자열(예: "공세점" ⊂ "코스트코 … 공세점"), 또는
    - 2글자 이상 토큰을 2개 이상 공유(OCR 오타 대비: "ㅛ스트코 코리아 공세점").
    체인점의 다른 지점(토큰 거의 안 겹침)은 False → OCR 상호를 유지합니다.
    """
    a, b = detected.strip(), canonical.strip()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    ta = {t for t in re.split(r"\s+", a) if len(t) >= 2}
    tb = {t for t in re.split(r"\s+", b) if len(t) >= 2}
    return len(ta & tb) >= 2


def _detect_store(lines: list[str], profile: Profile) -> str | None:
    """발행처 상호 추정.
      (1) 감지된 양식의 시그니처가 든 줄 최우선
      (2) 사업자번호가 있는 줄(또는 그 직전 상호형 줄)
      (3) 헤더/정책을 제외한 첫 상호형 줄
    """
    # (1) 시그니처 우선
    for ln in lines[:12]:
        if profile.signatures and any(s.lower() in ln.lower() for s in profile.signatures):
            cand = _clean_store(ln)
            if len(cand) >= 2:
                return cand
    # (2) 사업자번호(3-2-5 또는 10자리) 근처 — 번호 앞/뒤에서 상호 조각을 찾고,
    #     그 줄에 상호가 없으면 직전 줄에서 찾습니다.
    for i, ln in enumerate(lines[:12]):
        if BIZ_RE.search(ln) or re.search(r"\b\d{10}\b", ln):
            cand = _clean_store(ln)
            if len(cand) >= 2:
                return cand
            for prev in reversed(lines[:i]):
                if _looks_like_store(prev):
                    cand = _clean_store(prev)
                    if len(cand) >= 2:
                        return cand
            break
    # (3) 헤더/정책 제외 첫 상호형 줄
    for ln in lines[:8]:
        if _looks_like_store(ln):
            cand = _clean_store(ln)
            if len(cand) >= 2:
                return cand
    return lines[0] if lines else None


# ======================================================================
# 공용 파서 엔진
# ======================================================================
def parse_generic(text: str, profile: Profile) -> Receipt:
    """Profile 규칙에 따라 필드를 추출하는 공용 엔진."""
    total_kw = profile.total_keywords
    skip_kw = profile.skip_keywords
    two_line = profile.item_layout == "two_line"

    receipt = Receipt(raw_text=text, profile=profile.name)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # --- 상호명 / 카드(결제수단) ---
    store = _detect_store(lines, profile)
    # 알려진 특정 매장(학습된 양식)인데 OCR 상호가 부분/오타면 양식명(정식 상호)으로 보정.
    #   ("이마트/신세계"처럼 '/'가 든 카테고리 양식은 지점명을 유지하려 건너뜁니다)
    if store and "/" not in profile.name and _same_store(store, profile.name):
        store = profile.name
    receipt.store = store
    receipt.card = _detect_card(text)

    # --- 날짜 (양식 전용 정규식 → 없으면 미국식 MM/DD/YYYY 보조) ---
    if m := profile.date_regex.search(text):
        y, mo, d = m.groups()
        receipt.date = f"{y}-{int(mo):02d}-{int(d):02d}"
    elif m := DATE_US_RE.search(text):
        mo, d, y = m.groups()              # 07/09/2026 → 2026-07-09
        receipt.date = f"{y}-{int(mo):02d}-{int(d):02d}"

    # --- 합계: 총액 키워드가 있는 줄들 중 '마지막' 것의 금액 ---
    #   (소계 성격의 "합계수량/금액"이 앞에 오고 진짜 "합계"가 뒤에 오는 경우 대응)
    for ln in lines:
        if any(k in ln for k in total_kw):
            if prices := PRICE_RE.findall(strip_money(ln)):
                receipt.total = _to_int(prices[-1])
    # 키워드가 OCR로 깨졌을 때 보정: 부가세 등 제외한 금액 중 최대값
    if receipt.total is None:
        candidates = []
        for ln in lines:
            if any(k in ln for k in skip_kw):
                continue
            candidates += [_to_int(p) for p in PRICE_RE.findall(ln)]
        if candidates:
            receipt.total = max(candidates)

    # --- 품목 ---
    #   품목 줄 판정: 바코드가 있거나(two_line 가격줄) 천단위 금액이 있는 줄
    #   금액: 바코드 제거 후 마지막 금액(구분자 금액 우선, 없으면 소액 정수)
    #   이름: 줄에 한글이 있으면 그대로(inline), 부족하면 바로 위 텍스트 줄(two_line)
    in_summary = False   # '소계/합계' 이후 요약 구역인지 (그 뒤 고아 숫자는 품목 아님)
    all_kw = total_kw + skip_kw
    for i, ln in enumerate(lines):
        if "소계" in ln or _has_skip(ln, total_kw):
            in_summary = True
        if _has_skip(ln, all_kw) or _is_junk_line(ln):
            continue

        amount = _line_amount(ln, strip_money(ln))
        if not amount:                        # None(금액 아님) 또는 0. 음수는 유효
            continue
        # 합계와 동일 금액은 결제/요약 줄일 수 있어 제외 — 단, 단일품목(=합계)인
        # 영수증을 위해 '이미 품목이 있을 때'만 건너뜁니다.
        if amount == receipt.total and receipt.items:
            continue

        name = _clean_name(ln)
        needs_lookup = two_line and len(KOREAN_RE.findall(name)) < 2
        # 요약 구역의 '이름 없는 숫자 줄'(예: 분리된 COUPON TOTAL 값)은 품목 아님
        if in_summary and needs_lookup:
            continue
        if needs_lookup:
            for prev in reversed(lines[:i]):      # 가장 가까운 '금액 없는' 줄을 이름으로
                if _has_skip(prev, all_kw) or _is_junk_line(prev):
                    continue
                if _has_money(prev):               # 금액 있는 줄(=가격줄)은 이름 아님
                    continue
                cand = _clean_name(prev)
                if cand:
                    name = cand
                    break

        # 유효한 이름(한글/영문)이고 너무 길지 않을 때만 품목으로 인정.
        if _valid_item_name(name) and len(name) <= MAX_ITEM_NAME_LEN:
            receipt.items.append(LineItem(name=name, amount=amount))

    # --- 검산: 품목 합이 영수증 합계와 다르면 알림 ---
    #   OCR이 금액을 잘못 읽었거나(예: 수량+금액 병합) 품목을 놓친 경우를 잡아냅니다.
    if receipt.items and receipt.total:
        s = sum(i.amount for i in receipt.items)
        if s != receipt.total:
            receipt.notes.append(
                f"품목 합({s:,}원)이 영수증 합계({receipt.total:,}원)와 다릅니다 "
                f"— 품목 누락 또는 금액 오인식 가능성")

    return receipt


# ======================================================================
# 진입점 — 전용 파서가 있으면 그것을, 없으면 공용 엔진을 사용
# ======================================================================
def parse(text: str, profile: Profile) -> Receipt:
    fn = CUSTOM_PARSERS.get(profile.name)
    receipt = fn(text, profile) if fn else parse_generic(text, profile)
    # 전용 파서가 빠뜨렸을 수 있는 메타값 보정
    if not receipt.profile:
        receipt.profile = profile.name
    if not receipt.raw_text:
        receipt.raw_text = text
    return receipt


# 매장별 전용 파서 자동 등록: parsers/ 패키지를 import 하면 그 안의
# @register_parser 들이 실행됩니다. (없거나 실패해도 무시)
try:  # pragma: no cover
    import parsers  # noqa: F401
except Exception:
    pass
