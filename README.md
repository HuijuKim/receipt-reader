# 영수증 리더 (Receipt Reader)

한국 영수증 사진에서 **상호 · 날짜 · 카드사 · 품목 · 금액**을 뽑아내는 도구입니다.
PC 명령줄로도, 안드로이드 앱으로도 쓸 수 있습니다.

```
[앱] 사진 → 업로드 → [서버] 전처리 → OCR → 발행처 식별 → 파싱 → 검산 → JSON
```

앱은 얇은 클라이언트입니다. **판단은 전부 서버에 있어서, 파서를 고치면 앱을
다시 설치하지 않아도 반영됩니다.**

## 무엇이 되나

- 발행처(매장)를 먼저 식별하고 **그 양식에 맞춰** 나머지를 읽습니다
- 처음 보는 양식이면 **레이아웃을 학습해 DB에 저장**합니다 (미검증 상태로 격리)
- 쿠폰·할인은 음수 품목으로, 봉투값 같은 1,000원 미만 금액도 인식
- 카드사 이름을 한국 카드사 목록으로 정규화
- **검산** — 품목 합이 영수증 합계와 다르면 경고를 붙입니다
- CSV 내보내기 (엑셀에서 한글이 깨지지 않도록 BOM 포함)

## 구성

| 파일 | 역할 |
|---|---|
| `receipt_reader.py` | 파이프라인 오케스트레이션 + CLI |
| `ocr.py` | 이미지 전처리 → Google Cloud Vision → 좌표 기반 행 복원 |
| `issuer.py` | 발행처 식별 + 새 양식 자동 학습 |
| `parser.py` · `core.py` · `parsers/` | 양식 규칙 기반 파싱 |
| `profile_db.py` | 학습된 양식 저장소 (`profiles.db`) |
| `receipt_db.py` | 앱이 올린 인식 내역 (`receipts.db`) |
| `csv_export.py` | CSV 형식 — CLI 와 서버가 공유 |
| `server.py` | 백엔드 (FastAPI) |
| `android/` | 안드로이드 앱 (Compose + Retrofit + Room) |

## 준비

```powershell
py -m pip install -r requirements.txt
```

Google Cloud Vision 인증이 필요합니다 (둘 중 하나):

```powershell
setx GOOGLE_VISION_API_KEY "AIza..."                  # API 키 방식
setx GOOGLE_APPLICATION_CREDENTIALS "C:\경로\key.json"  # 서비스 계정 방식
```

> **인증키는 서버에만 둡니다.** APK 는 누구나 열어볼 수 있어 앱에 넣으면 유출됩니다.

## 쓰는 법

### 명령줄

```powershell
py receipt_reader.py 영수증.jpg            # 인식 결과 출력
py receipt_reader.py 영수증.jpg --csv      # result/영수증.csv 로 저장
py receipt_reader.py --list-profiles       # 학습된 양식 목록
```

### 서버 + 앱

```powershell
py -m uvicorn server:app --host 127.0.0.1 --port 8000
```

첫 실행 때 API 키가 만들어져 `api_key.txt` 에 저장되고 콘솔에 찍힙니다.
그 값을 앱 [설정] 탭에 넣으세요.

- API 규격: [android/API.md](android/API.md)
- 앱 빌드: [android/README.md](android/README.md)
- **다른 망(LTE 등)에서 쓰기**: [REMOTE.md](REMOTE.md)

## 개발 규칙

[CLAUDE.md](CLAUDE.md) 에 작업 규칙과 이 프로젝트의 도구 체인 주의점이 있습니다.
특히 **파서를 고칠 때는 샘플 전체를 돌려 전후를 비교**해야 합니다 — 정규식 하나가
여러 곳에서 쓰이기 때문입니다.

## 저장소에 없는 것

개인 데이터라 제외했습니다.

- `Sample/` — 실제 영수증 사진 (상호·품목·금액은 물론 생활 반경까지 드러남)
- `result/` — 인식 결과 CSV
- `api_key.txt`, `profiles.db`, `receipts.db` — 실행하면 자동으로 만들어집니다

## 한계

- **Google Vision 이 필요합니다.** 무료 할당량을 넘으면 과금됩니다.
- 서버가 도는 PC 가 켜져 있어야 앱이 동작합니다.
- 인식 내역은 앱이 올려야 서버에 남습니다 (자동 동기화 아님).
- OCR 오인식으로 검산이 어긋나는 영수증이 남아 있습니다 — 경고로 표시됩니다.
