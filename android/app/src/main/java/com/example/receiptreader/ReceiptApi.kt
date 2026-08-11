package com.example.receiptreader

import android.content.Context
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import java.io.IOException
import java.util.concurrent.TimeUnit

interface ReceiptApi {
    /** 영수증 사진을 업로드하고 인식 결과를 받습니다. */
    @Multipart
    @POST("extract")
    suspend fun extract(@Part image: MultipartBody.Part): ReceiptDto

    /** 주소와 키가 모두 맞는지 확인합니다 ([설정] 탭의 연결 테스트). */
    @GET("verify")
    suspend fun verify(): StatusDto

    /** 폰에 저장된 내역을 서버로 올립니다 (여러 번 보내도 안전). */
    @POST("receipts")
    suspend fun uploadReceipts(@Body body: UploadRequest): UploadResultDto
}

object ApiClient {
    // 설정이 바뀌면 Retrofit 을 새로 만들어야 하므로 마지막 설정을 함께 들고 있습니다.
    // 한 쌍으로 묶어 두면 "설정만 갱신되고 api 는 옛것" 인 상태가 생길 수 없습니다.
    private var cached: Pair<ServerConfig, ReceiptApi>? = null

    @Synchronized
    fun api(ctx: Context): ReceiptApi {
        val cfg = Settings.load(ctx)
        cached?.let { (cachedCfg, api) -> if (cachedCfg == cfg) return api }

        require(cfg.url.isNotBlank()) { "서버 주소가 비어 있습니다 ([설정] 탭에서 입력하세요)" }

        val http = OkHttpClient.Builder()
            // OCR + 파싱에 수 초가 걸릴 수 있어 넉넉히 잡습니다.
            // 터널을 거치면 더 느려질 수 있어 읽기 시간을 늘렸습니다.
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(120, TimeUnit.SECONDS)
            .addInterceptor { chain ->
                chain.proceed(
                    chain.request().newBuilder()
                        .header("X-API-Key", cfg.apiKey)
                        .build()
                )
            }
            .addInterceptor(HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BASIC
            })
            .build()

        val api = Retrofit.Builder()
            .baseUrl(cfg.url)
            .client(http)
            .addConverterFactory(MoshiConverterFactory.create(appMoshi))
            .build()
            .create(ReceiptApi::class.java)

        cached = cfg to api
        return api
    }
}

/** 통신 예외를 화면에 그대로 띄울 수 있는 한국어 문장으로 바꿉니다. */
fun describeError(e: Throwable): String = when (e) {
    is HttpException -> when (e.code()) {
        401 -> "API 키가 올바르지 않습니다 — [설정] 탭에서 확인하세요"
        404 -> "서버 주소가 올바르지 않습니다 — [설정] 탭에서 확인하세요"
        413 -> "사진 용량이 너무 큽니다 (최대 15MB)"
        502 -> "서버의 OCR 호출이 실패했습니다 — PC 쪽 서버 로그를 확인하세요"
        else -> "서버 오류 (HTTP ${e.code()})"
    }
    is IOException -> "서버에 연결할 수 없습니다 — PC의 서버와 터널이 켜져 있는지 확인하세요"
    else -> e.message ?: "알 수 없는 오류"
}
