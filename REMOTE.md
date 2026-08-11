# 다른 망(외부)에서 앱 쓰기

같은 와이파이가 아니어도 — LTE/5G, 회사, 다른 집 — 앱에서 인식이 되게 하는 방법입니다.

## 고정 주소

Tailscale Funnel 을 켜면 아래 형태의 **고정 HTTPS 주소**가 나옵니다.

```
https://<PC이름>.<테일넷이름>.ts.net
```

실제 주소는 `tailscale funnel status` 로 확인하세요. **한 번 정해지면 바뀌지
않으므로** 앱 [설정] 탭에 한 번만 넣으면 끝입니다.

```
[휴대폰 / 어디서든]
        │  https (인증: X-API-Key)
        ▼
https://<PC이름>.<테일넷이름>.ts.net   ← Tailscale Funnel (고정)
        │
        ▼
   내 PC 127.0.0.1:8000  (FastAPI)
        │
        ▼
   Google Vision  (인증키는 PC에만)
```

공유기 포트포워딩이 필요 없습니다. Tailscale 이 PC에서 바깥으로 나가는
(outbound) 연결을 만들기 때문입니다. Vision 인증키도 PC 밖으로 나가지 않습니다.
휴대폰에는 아무것도 설치할 필요가 없습니다 — Funnel 은 공개 인터넷으로 열립니다.

**PC가 켜져 있고 서버가 떠 있어야 동작합니다.**

---

## 매번 하는 일 (PC)

### 서버 실행 — `start-server.cmd` 더블클릭

또는 직접:

```powershell
cd <프로젝트 폴더>
py -m uvicorn server:app --host 127.0.0.1 --port 8000
```

> `python` 이 아니라 `py` 입니다. 이 PC의 `python` 명령은 Microsoft Store
> 스텁으로 연결돼 있어 실행되지 않습니다.

> `--host 0.0.0.0` 이 아니라 `127.0.0.1` 입니다. Funnel 만 접속하면 되므로
> 굳이 LAN에까지 열어둘 이유가 없습니다.

**터널은 따로 켤 필요가 없습니다.** Tailscale 이 윈도우 서비스로 돌면서
부팅할 때 Funnel 설정을 알아서 복원합니다.

### 앱 [설정] 탭 (최초 1회만)

| 칸 | 넣을 값 |
|----|---------|
| 서버 주소 | `tailscale funnel status` 에 나온 `https://….ts.net` |
| API 키 | `api_key.txt` 의 값 |

**[연결 테스트]** 를 누르면 주소·키가 맞는지 바로 확인됩니다.
`연결 성공 ✓` 이 나오면 [인식] 탭에서 평소처럼 쓰면 됩니다.

### 서버도 자동으로 켜지게 하려면 (선택)

`Win+R` → `shell:startup` → 열린 폴더에 `start-server.cmd` 의 **바로가기**를
넣으면 로그인할 때 자동으로 실행됩니다.

창을 띄우고 싶지 않으면 작업 스케줄러(`taskschd.msc`)에 등록하세요:

- 트리거: 로그온할 때
- 동작: `C:\WINDOWS\pyw.exe`
  인수: `-m uvicorn server:app --host 127.0.0.1 --port 8000`
  시작 위치: `<프로젝트 폴더>`
- "숨겨진 작업으로 실행" 체크

(`pyw.exe` 는 콘솔 창 없이 도는 파이썬 런처입니다)

---

## 왜 API 키가 필요한가

터널 주소는 인터넷에 그대로 열려 있습니다. 인증이 없으면 주소를 알아낸
누구나 `/extract` 를 호출할 수 있고, 그 호출은 전부 **내 Google Vision
요금**이 됩니다. 그래서 `/extract` 는 `X-API-Key` 헤더를 요구합니다.

- 키는 서버가 처음 실행될 때 자동 생성되어 `api_key.txt` 에 저장됩니다
  (`.gitignore` 에 등록돼 있습니다).
- 키를 바꾸고 싶으면 `api_key.txt` 를 지우고 서버를 다시 켜면 새로 만들어집니다.
  그 뒤 앱 [설정] 탭의 키도 새 값으로 바꿔야 합니다.
- 환경변수 `RECEIPT_API_KEY` 가 설정돼 있으면 그 값이 우선합니다.

`/health` 만 키 없이 열려 있는데, 이건 `{"status":"ok"}` 외에 아무것도
돌려주지 않아 노출돼도 문제가 없습니다.

---

## 문제가 생기면

| 앱에 뜨는 말 | 원인 / 할 일 |
|---|---|
| 서버에 연결할 수 없습니다 | PC의 서버가 꺼져 있음. `start-server.cmd` 실행 |
| 서버 주소가 올바르지 않습니다 | 주소 오타. 위의 고정 주소와 대조 |
| API 키가 올바르지 않습니다 | `api_key.txt` 값과 [설정] 탭의 값이 다름 |
| 사진 용량이 너무 큽니다 | 15MB 초과. 카메라 화질을 낮추거나 다시 촬영 |
| 서버의 OCR 호출이 실패했습니다 | PC 콘솔 확인. 보통 Vision 인증 환경변수(`GOOGLE_APPLICATION_CREDENTIALS`) 문제 |

---

## 앱 다시 빌드할 때

명령줄에서 빌드하려면 JDK를 지정해야 합니다. 이 PC의 기본 `java` 는
Java 8 이라 Android Gradle Plugin 이 거부합니다.

```powershell
$env:JAVA_HOME = "D:\Android\Android Studio\jbr"   # Android Studio 번들 JDK 경로
cd <프로젝트 폴더>\android
.\gradlew.bat assembleDebug
```

APK: **`C:\AndroidBuild\ReceiptReader\app\outputs\apk\debug\app-debug.apk`**

산출물이 프로젝트 폴더가 아니라 `C:\AndroidBuild` 로 나가는 이유: 프로젝트가
OneDrive 안에 있으면 OneDrive 가 빌드 파일을 동기화하려고 잡고 있어 Gradle 이
`Unable to delete directory` 로 실패합니다. 경로는 `android/gradle.properties`
의 `buildOutputDir` 로 바꿀 수 있습니다.

(Android Studio에서 ▶ Run 하면 JDK 설정은 알아서 됩니다.)

---

## Funnel 켜고 끄기

```powershell
# 상태 확인
& "C:\Program Files\Tailscale\tailscale.exe" funnel status

# 끄기 (공개 주소를 닫습니다)
& "C:\Program Files\Tailscale\tailscale.exe" funnel --https=443 off

# 다시 켜기
& "C:\Program Files\Tailscale\tailscale.exe" funnel --bg 8000
```

---

## 남은 제약

**PC가 켜져 있어야 합니다.** 이것만 없애려면 서버를 Google Cloud Run 에
올리면 됩니다. Vision 과 같은 GCP 라서 인증키 파일 없이 IAM 으로 연결되고,
PC를 꺼도 동작합니다. 다만 `profiles.db`(학습된 양식)가 컨테이너와 함께
사라지므로 Cloud SQL 이나 GCS 로 옮기는 작업이 함께 필요합니다.

## 예전 방식 (Cloudflare 터널)

`cloudflared` 도 설치돼 있어 아래로 임시 터널을 열 수 있습니다. 주소가
매번 바뀌므로 지금은 쓰지 않지만, Tailscale 에 문제가 생겼을 때의 대안입니다.

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```
