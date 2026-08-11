package com.example.receiptreader

import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory

/**
 * 서버(/extract) 응답 구조 — API.md 의 계약과 1:1로 대응합니다.
 * Python 쪽 core.Receipt 와 같은 모양입니다.
 *
 * (Moshi 의 KotlinJsonAdapterFactory 가 리플렉션으로 처리하므로
 *  @JsonClass 코드생성(KSP) 설정은 필요 없습니다.)
 */
data class ReceiptDto(
    val store: String?,
    val date: String?,
    val card: String?,
    val total: Int?,
    val profile: String = "",
    val items: List<LineItemDto> = emptyList(),
    val notes: List<String> = emptyList(),
)

data class LineItemDto(
    val name: String,
    val amount: Int,          // 쿠폰/할인이면 음수
)

/** /health, /verify 의 응답 */
data class StatusDto(val status: String)

// ----------------------------------------------------------------------
// 내역 업로드 (POST /receipts)
// ----------------------------------------------------------------------
/**
 * 서버로 보내는 영수증 한 건.
 *
 * client_id 는 폰 DB 의 행 번호입니다. 서버가 (기기 id + client_id) 로 중복을
 * 판정하므로, 같은 내역을 여러 번 보내도 쌓이지 않고 갱신만 됩니다.
 */
data class ReceiptUploadDto(
    val client_id: Long,
    val store: String?,
    val date: String?,
    val card: String?,
    val total: Int?,
    val profile: String,
    val items: List<LineItemDto>,
    val notes: List<String>,
    val saved_at: Long,
)

data class UploadRequest(
    val device_id: String,
    val receipts: List<ReceiptUploadDto>,
)

/** saved: 이번에 처리한 건수, total: 서버에 쌓인 전체 건수 */
data class UploadResultDto(val saved: Int, val total: Int)

/** 화면 상태 */
sealed interface UiState {
    data object Idle : UiState
    data object Loading : UiState
    data class Success(val receipt: ReceiptDto) : UiState
    data class Error(val message: String) : UiState
}

/**
 * 앱 전체가 쓰는 Moshi 인스턴스.
 *
 * 네트워크 응답, 화면 상태 저장, Room 의 JSON 컬럼이 모두 같은 규칙으로
 * (역)직렬화되어야 합니다. 인스턴스를 따로 만들면 어댑터 설정을 바꿀 때
 * 한 곳을 빠뜨려 저장한 JSON 과 읽는 JSON 이 어긋날 수 있습니다.
 * (리플렉션 어댑터 캐시도 한 벌만 유지됩니다)
 */
internal val appMoshi: Moshi by lazy {
    Moshi.Builder().add(KotlinJsonAdapterFactory()).build()
}

/**
 * 인식 결과를 JSON 으로 바꾸는 어댑터.
 *
 * 카메라 앱이 떠 있는 동안 시스템이 이 앱을 메모리에서 회수했다가 되살리는 일이
 * 흔합니다. 그때 결과를 잃으면 Vision 을 다시 호출해야 하고 그건 그대로 요금이라,
 * 화면 상태까지 저장했다가 복원합니다 (MainActivity 의 UiStateSaver).
 */
internal val receiptJsonAdapter: JsonAdapter<ReceiptDto> by lazy {
    appMoshi.adapter(ReceiptDto::class.java)
}
