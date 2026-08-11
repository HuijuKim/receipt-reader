package com.example.receiptreader

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import com.example.receiptreader.data.ReceiptEntity
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 저장된 내역을 CSV 로 내보냅니다.
 *
 * 열 구성은 PC 쪽 receipt_reader.py 의 save_csv() 와 같습니다
 * (상호/날짜/카드/품목/금액 + 영수증마다 합계 행). 같은 모양이라 PC의 result 폴더에
 * 쌓이는 csv 와 앱에서 뽑은 파일을 그대로 이어붙일 수 있습니다.
 *
 * (주석에 별표+빗금 조합을 쓰지 마세요 — Kotlin 은 블록 주석이 중첩되어
 *  주석 안의 여는 표시가 새 주석을 열고 파일 끝까지 닫히지 않습니다)
 */
private val CSV_HEADER = listOf("상호", "날짜", "카드", "품목", "금액")

/**
 * 엑셀은 BOM 이 없는 UTF-8 CSV 를 시스템 인코딩으로 읽어 한글을 깨뜨립니다.
 * 그래서 파이썬 쪽과 동일하게 BOM 을 붙입니다 (utf-8-sig 와 같은 결과).
 */
private const val BOM = "\uFEFF"

/** RFC 4180 — 쉼표/따옴표/줄바꿈이 든 값은 따옴표로 감싸고, 따옴표는 두 번 씁니다. */
private fun csvField(value: Any?): String {
    val s = value?.toString() ?: ""
    return if (s.any { it == ',' || it == '"' || it == '\n' || it == '\r' }) {
        "\"" + s.replace("\"", "\"\"") + "\""
    } else {
        s
    }
}

private fun csvRow(cells: List<Any?>): String =
    cells.joinToString(",") { csvField(it) } + "\r\n"   // 엑셀 호환을 위해 CRLF

fun buildCsv(receipts: List<ReceiptEntity>): String = buildString {
    append(BOM)
    append(csvRow(CSV_HEADER))
    for (r in receipts) {
        for (item in r.items) {
            append(csvRow(listOf(r.store, r.date, r.card, item.name, item.amount)))
        }
        append(csvRow(listOf(r.store, r.date, r.card, "합계", r.total)))
    }
}

/**
 * 폰에 저장된 내역을 서버로 올립니다. 올린 건수를 돌려줍니다.
 *
 * '무엇을 이미 올렸는지' 를 앱이 관리하지 않고 매번 전체를 보냅니다 —
 * 서버가 (기기 id + 행번호) 로 중복을 걸러내므로 그래도 쌓이지 않고,
 * 폰에서 수정·삭제한 내용도 자연스럽게 반영됩니다.
 */
suspend fun uploadHistory(ctx: Context, list: List<ReceiptEntity>): UploadResultDto {
    val body = UploadRequest(
        device_id = Settings.deviceId(ctx),
        receipts = list.map { r ->
            ReceiptUploadDto(
                client_id = r.id,
                store = r.store,
                date = r.date,
                card = r.card,
                total = r.total,
                profile = r.profile,
                items = r.items,
                notes = r.notes,
                saved_at = r.savedAt,
            )
        },
    )
    return ApiClient.api(ctx).uploadReceipts(body)
}

/** 내보낼 파일 이름 — 같은 날 여러 번 내보내도 구분되도록 시각까지 넣습니다. */
fun exportFileName(): String {
    val stamp = SimpleDateFormat("yyyyMMdd_HHmm", Locale.KOREA).format(Date())
    return "영수증내역_$stamp.csv"
}

/**
 * 공유용 임시 파일을 캐시에 씁니다 (FileProvider 로 넘기기 위해).
 * 이전 파일은 지웁니다 — 내보낼 때마다 캐시가 늘어나지 않도록.
 */
fun writeShareFile(ctx: Context, csv: String, name: String): File {
    val dir = File(ctx.cacheDir, "exports").apply { mkdirs() }
    dir.listFiles()?.forEach { it.delete() }
    val file = File(dir, name)
    file.writeText(csv)          // 문자열에 이미 BOM 이 들어 있습니다
    return file
}

/**
 * 캐시 파일을 다른 앱에 넘길 수 있는 URI 로 바꿉니다.
 *
 * authority 문자열은 AndroidManifest 의 `${'$'}{applicationId}.fileprovider` 와
 * 맞아야 하고, 틀리면 런타임에야 터집니다. 규약을 여기 한 곳에만 둡니다.
 */
fun cacheUri(ctx: Context, file: File): Uri =
    FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
