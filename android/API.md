# 앱 ↔ 서버 API 계약

앱은 사진만 보내고, 서버가 OCR + 파싱을 해서 결과 JSON을 돌려줍니다.
(Vision 인증키는 서버에만 두어 앱에서 유출될 수 없게 합니다.)

## 인증

`/extract` 와 `/verify` 는 **`X-API-Key` 헤더**를 요구합니다. 키가 없거나
틀리면 `401` 입니다. 키는 서버가 만들어 `api_key.txt` 에 저장하며, 앱에서는
[설정] 탭에 넣습니다. 외부 접속 설정은 [REMOTE.md](../REMOTE.md) 참고.

## POST /extract

사진 한 장을 업로드해 인식 결과를 받습니다.

**요청** — `multipart/form-data`, 헤더 `X-API-Key: <키>`

| 필드 | 타입 | 설명 |
|------|------|------|
| `image` | file | 영수증 사진 (jpg/png), 최대 15MB |

**응답 200** — `application/json`

```json
{
  "store": "(주) 코스트코 코리아 공세점",
  "date": "2026-07-09",
  "card": "현대카드(VISA)",
  "total": 78900,
  "profile": "(주) 코스트코 코리아 공세점",
  "items": [
    { "name": "화과방우피파이", "amount": 94900 },
    { "name": "화과방우피파이", "amount": -16000 }
  ],
  "notes": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `store` | string \| null | 상호 (인식 실패 시 null) |
| `date` | string \| null | 구매일 `YYYY-MM-DD` |
| `card` | string \| null | 카드/결제수단. 알려진 카드사가 아니면 null |
| `total` | int \| null | 합계 금액(원) |
| `profile` | string | 인식에 사용된 양식 이름 |
| `items` | array | 품목 목록. `amount` 는 쿠폰/할인이면 음수 |
| `notes` | string[] | 경고 (예: 품목 합 불일치, 미검증 양식) |

**오류 응답**

| 코드 | 상황 | 본문 |
|------|------|------|
| 400 | 이미지가 아니거나 열 수 없음 | `{"detail": "..."}` |
| 401 | `X-API-Key` 없음/불일치 | `{"detail": "API 키가 올바르지 않습니다"}` |
| 413 | 15MB 초과 | `{"detail": "..."}` |
| 502 | OCR 엔진 오류(재시도 후에도 실패) | `{"detail": "..."}` |

## POST /receipts

앱이 폰에 저장한 내역을 서버로 올립니다. 키 필요.

**요청** — `application/json`

```json
{
  "device_id": "5f3c…",
  "receipts": [
    {
      "client_id": 12,
      "store": "용인지석초교 파리바게뜨",
      "date": "2026-06-28",
      "card": "KB국민카드",
      "total": 15000,
      "profile": "파리바게뜨",
      "items": [{ "name": "벌꿀)명가카스테라", "amount": 14900 }],
      "notes": [],
      "saved_at": 1754800000000
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `device_id` | 기기마다 최초 1회 생성한 UUID |
| `client_id` | 폰 DB(Room)의 행 번호 |
| `saved_at` | 폰에서 저장한 시각 (epoch millis) |

**중복 처리** — `device_id` + `client_id` 가 기본키입니다. 같은 내역을 여러 번
보내도 쌓이지 않고 갱신만 됩니다. 그래서 앱은 무엇을 이미 보냈는지 기억하지
않고 매번 전체를 보냅니다.

**응답 200** — `{"saved": 12, "total": 34}`
(`saved` 이번에 처리한 건수, `total` 서버에 쌓인 전체 건수)

## GET /receipts

올라온 내역을 최근 구매일 순으로. 키 필요.
`?device_id=…` 로 특정 기기 것만 볼 수 있습니다.

**응답 200** — `{"count": 34, "receipts": [ … ]}`

## GET /receipts.csv

올라온 내역 전체를 CSV 로 내려받습니다. 키 필요.
BOM 붙은 UTF-8 이라 엑셀에서 바로 열립니다. `?device_id=…` 필터 가능.

## GET /verify

주소와 키가 모두 맞는지 확인 (앱의 [연결 테스트]). 키 필요.
성공 시 `{"status": "ok"}`, 키가 틀리면 `401`.

## GET /health

서버까지 연결이 닿는지 확인. **키 불필요** — 터널 점검용이라 아무 정보도
돌려주지 않습니다. `{"status": "ok"}`
