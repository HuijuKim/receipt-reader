"""매장별 전용 파서 패키지 (하이브리드 오버라이드).

이 폴더에 `<매장>.py` 파일을 두고 그 안에서 parser.register_parser 로 전용
파서를 등록하면, 해당 매장 영수증에 한해 공용 엔진 대신 그 파서가 쓰입니다.
밑줄(_)로 시작하는 파일은 자동 로드에서 제외됩니다(_template.py 등).

이 __init__ 은 import 되는 순간 폴더 안의 모듈들을 자동으로 불러와 등록합니다.
"""
import importlib
import pkgutil

for _finder, _name, _ispkg in pkgutil.iter_modules(__path__):
    if not _name.startswith("_"):
        importlib.import_module(f"{__name__}.{_name}")
