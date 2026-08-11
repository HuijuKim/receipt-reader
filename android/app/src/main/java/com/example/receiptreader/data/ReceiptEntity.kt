package com.example.receiptreader.data

import androidx.room.Entity
import androidx.room.PrimaryKey
import androidx.room.TypeConverter
import com.example.receiptreader.LineItemDto
import com.example.receiptreader.appMoshi
import com.squareup.moshi.Types

/**
 * 저장된 인식 결과 한 건.
 *
 * 품목/경고 목록은 별도 테이블 대신 JSON 문자열로 보관합니다.
 * (항상 영수증 단위로 통째로 읽고 쓰므로 조인이 필요 없습니다)
 */
@Entity(tableName = "receipts")
data class ReceiptEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val store: String?,
    val date: String?,
    val card: String?,
    val total: Int?,
    val profile: String,
    val items: List<LineItemDto>,
    val notes: List<String>,
    val savedAt: Long,          // 저장 시각 (epoch millis) — 목록 정렬용
)

/** List<LineItemDto> / List<String> ↔ JSON 변환 */
class Converters {
    // 네트워크·화면상태와 같은 Moshi 를 씁니다 (Models.kt).
    private val moshi = appMoshi

    private val itemsAdapter = moshi.adapter<List<LineItemDto>>(
        Types.newParameterizedType(List::class.java, LineItemDto::class.java)
    )
    private val stringsAdapter = moshi.adapter<List<String>>(
        Types.newParameterizedType(List::class.java, String::class.java)
    )

    @TypeConverter
    fun itemsToJson(v: List<LineItemDto>): String = itemsAdapter.toJson(v)

    @TypeConverter
    fun jsonToItems(s: String): List<LineItemDto> = itemsAdapter.fromJson(s) ?: emptyList()

    @TypeConverter
    fun stringsToJson(v: List<String>): String = stringsAdapter.toJson(v)

    @TypeConverter
    fun jsonToStrings(s: String): List<String> = stringsAdapter.fromJson(s) ?: emptyList()
}
