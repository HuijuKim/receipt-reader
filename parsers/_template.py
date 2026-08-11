"""매장별 전용 파서 템플릿 (예시 · 자동 로드 안 됨).

새 전용 파서를 만들려면 이 파일을 복사해 밑줄 없는 이름으로 저장하세요.
예: parsers/costco.py

    from core import Profile, Receipt
    from parser import register_parser, parse_generic

    @register_parser("코스트코")          # ← Profile.name 과 정확히 일치해야 함
    def parse(text: str, profile: Profile) -> Receipt:
        # 1) 공용 엔진 결과에서 출발
        r = parse_generic(text, profile)

        # 2) 이 매장만의 보정 (예시)
        #    - 특정 줄 위치에서 카드번호/포인트 무시
        #    - 품목 금액을 단가×수량으로 재계산
        #    - 상호명을 정식 명칭으로 고정 등
        #    r.store = "코스트코"
        #    r.items = [it for it in r.items if 조건]

        return r

전용 파서는 '아주 특이해서 규칙 데이터로 표현하기 어려운' 매장에만 쓰세요.
대부분의 매장은 DB에 규칙(Profile)만 추가하면 공용 엔진으로 처리됩니다.
"""
