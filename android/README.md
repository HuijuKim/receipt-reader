# 영수증 리더 — 안드로이드 앱 (골격)

사진을 찍어 Python 백엔드로 보내면, 서버가 OCR + 파싱해서 결과를 돌려주는 최소 앱입니다.

## 왜 서버를 두나요?

Google Vision 인증키(서비스 계정 JSON)를 **APK에 넣으면 안 됩니다.** APK는 누구나
열어볼 수 있어 키가 유출되고, 남이 내 클라우드 요금을 쓰게 됩니다.
그래서 키는 **서버에만** 두고, 앱은 사진만 보냅니다.

    [앱] --사진--> [Python 서버] --> Cloud Vision --> 기존 파서 --> JSON --> [앱]

## 준비물

1. **Android Studio** 설치 — https://developer.android.com/studio
   (JDK 17 + Android SDK + Gradle 이 함께 설치됩니다. 현재 PC의 Java 8 로는 빌드 불가)

## 실행 방법

1. Android Studio 실행 → **Open** → 이 `android/` 폴더 선택
2. 첫 실행 시 Gradle 동기화가 자동으로 진행됩니다 (몇 분 소요)
3. 백엔드 서버를 먼저 띄웁니다 (프로젝트 루트에서):

       py -m uvicorn server:app --host 127.0.0.1 --port 8000

   콘솔에 찍히는 **API 키**를 앱 [설정] 탭에 넣어야 합니다.
   (`python` 이 아니라 `py` — 이 PC의 `python` 은 Store 스텁입니다)

4. 에뮬레이터에서 ▶ Run

명령줄에서 빌드할 때는 JDK 를 지정해야 합니다 (기본 `java` 가 Java 8):

    $env:JAVA_HOME = "D:\Android\Android Studio\jbr"
    .\gradlew.bat assembleDebug

## 서버 주소 설정

주소와 API 키는 **앱의 [설정] 탭**에서 바꿉니다. 기기에 저장되므로 앱을
다시 빌드할 필요가 없습니다. `app/build.gradle.kts` 의 `SERVER_URL` 은
설정을 한 번도 저장하지 않았을 때의 초기값일 뿐입니다.

| 실행 환경 | 주소 |
|-----------|------|
| 에뮬레이터 | `http://10.0.2.2:8000/` (초기값 · PC의 localhost를 가리킴) |
| 같은 Wi-Fi 의 실제 기기 | `http://<PC의 LAN IP>:8000/` (서버를 `--host 0.0.0.0` 으로 띄우고 방화벽 8000 허용) |
| **다른 망 (LTE 등)** | Cloudflare 터널 주소 — [REMOTE.md](../REMOTE.md) 참고 |

## 구성

    app/src/main/java/com/example/receiptreader/
      MainActivity.kt   화면 (갤러리/촬영 → 업로드 → 결과 → 내역 → 설정)
      ReceiptApi.kt     Retrofit 통신 설정 + 오류 메시지 변환
      Settings.kt       서버 주소 / API 키 저장 (SharedPreferences)
      Export.kt         내역 → CSV 변환 / 공유 파일 작성
      Models.kt         서버 응답 데이터 구조 (API.md 와 1:1)

## 내역 내보내기

[내역] 탭의 **[CSV 저장]** 은 안드로이드 파일 선택창을 띄워 원하는 위치에
저장합니다(SAF). **[공유]** 는 카톡·메일·드라이브 등으로 바로 보냅니다.

CSV 는 PC 쪽 `receipt_reader.py --csv` 와 **같은 형식**입니다 — BOM 붙은 UTF-8,
`상호,날짜,카드,품목,금액` 5열, 영수증마다 마지막에 합계 행. 두 파일을 그대로
이어붙일 수 있고, 엑셀에서 바로 열어도 한글이 깨지지 않습니다.

API 규격은 [API.md](API.md) 참고.

## 현재 범위 (골격)

- [x] 갤러리에서 사진 선택 / 카메라 촬영
- [x] 서버로 업로드 → 결과(상호/날짜/카드/품목/합계/경고) 표시
- [x] 결과 저장 / 목록 화면 / 상세·삭제
- [x] 외부 망 접속 (고정 주소 + API 키) — [REMOTE.md](../REMOTE.md)
- [x] 내역 CSV 내보내기 (저장 / 공유)
- [x] https 적용 (Tailscale Funnel 이 인증서까지 처리)
- [ ] 양식 검토(--review) 화면
