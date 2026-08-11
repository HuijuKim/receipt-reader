package com.example.receiptreader

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import coil.compose.AsyncImage
import com.example.receiptreader.data.AppDatabase
import com.example.receiptreader.data.ReceiptEntity
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import java.io.File
import java.text.NumberFormat
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { AppRoot() } }
    }
}

private enum class Tab { SCAN, HISTORY, SETTINGS }

@Composable
fun AppRoot() {
    var tab by remember { mutableStateOf(Tab.SCAN) }

    Column(Modifier.fillMaxSize()) {
        Text(
            "영수증 리더",
            style = MaterialTheme.typography.headlineSmall,
            textAlign = TextAlign.Center,
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 16.dp, bottom = 8.dp),
        )
        TabRow(selectedTabIndex = tab.ordinal) {
            Tab(selected = tab == Tab.SCAN, onClick = { tab = Tab.SCAN },
                text = { Text("인식") })
            Tab(selected = tab == Tab.HISTORY, onClick = { tab = Tab.HISTORY },
                text = { Text("내역") })
            Tab(selected = tab == Tab.SETTINGS, onClick = { tab = Tab.SETTINGS },
                text = { Text("설정") })
        }
        when (tab) {
            Tab.SCAN -> ScanScreen()
            Tab.HISTORY -> HistoryScreen()
            Tab.SETTINGS -> SettingsScreen()
        }
    }
}

/**
 * UiState 를 Bundle 에 담기 위한 변환기.
 *
 * 성공 결과만 보존합니다. 로딩·오류는 Idle 로 되돌리는데, 되살아난 뒤에도
 * 스피너가 영영 도는 상태로 남지 않게 하기 위해서입니다 (업로드하던 코루틴은
 * 이미 죽어 있으므로 결과가 도착할 일이 없습니다).
 */
private val UiStateSaver: Saver<UiState, String> = Saver(
    save = { s -> if (s is UiState.Success) receiptJsonAdapter.toJson(s.receipt) else "" },
    restore = { json ->
        if (json.isBlank()) UiState.Idle
        else receiptJsonAdapter.fromJson(json)?.let { UiState.Success(it) } ?: UiState.Idle
    },
)

// ======================================================================
// 인식 화면
// ======================================================================
@Composable
private fun ScanScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val dao = remember { AppDatabase.get(ctx).receiptDao() }

    // 아래 상태는 모두 rememberSaveable 입니다 — 그냥 remember 로 두면
    // 카메라 앱이 떠 있는 사이 시스템이 이 앱을 회수했다 되살릴 때 전부 날아가고,
    // 촬영하고 돌아와도 사진이 없는 것처럼 보입니다.
    var imageUri by rememberSaveable { mutableStateOf<Uri?>(null) }
    var state by rememberSaveable(stateSaver = UiStateSaver) {
        mutableStateOf<UiState>(UiState.Idle)
    }
    var saved by rememberSaveable { mutableStateOf(false) }   // 중복 저장 방지

    // 새 사진을 받았을 때 초기화할 것들 — 한 곳에만 둡니다.
    fun onNewImage(uri: Uri) {
        imageUri = uri
        state = UiState.Idle
        saved = false
    }

    val pickImage = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri -> if (uri != null) onNewImage(uri) }

    var tempUri by rememberSaveable { mutableStateOf<Uri?>(null) }
    val takePicture = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { ok ->
        // 실패해도 조용히 넘어가지 않고 이유를 화면에 남깁니다.
        val captured = tempUri
        when {
            !ok -> state = UiState.Error(
                "촬영한 사진을 받지 못했습니다 (촬영을 취소했거나 카메라가 저장에 실패)."
            )
            captured == null -> state = UiState.Error(
                "촬영 결과를 받을 위치를 잃었습니다. 다시 촬영해 주세요."
            )
            else -> onNewImage(captured)
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = {
                pickImage.launch(
                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                )
            }) { Text("갤러리") }

            Button(onClick = {
                // 캐시가 가득 차면 여기서 예외가 나는데, 그대로 두면 앱이 죽어
                // "촬영이 안 된다"로만 보입니다.
                val uri = try {
                    createTempImageUri(ctx)
                } catch (e: Exception) {
                    state = UiState.Error("사진을 저장할 공간을 만들지 못했습니다: ${e.message}")
                    null
                }
                if (uri != null) {
                    tempUri = uri
                    takePicture.launch(uri)
                }
            }) { Text("촬영") }
        }

        Spacer(Modifier.height(12.dp))

        imageUri?.let { uri ->
            AsyncImage(
                model = uri,
                contentDescription = "선택한 영수증",
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(max = 240.dp),
            )
            Spacer(Modifier.height(12.dp))
            Button(
                onClick = {
                    state = UiState.Loading
                    saved = false
                    scope.launch {
                        state = try {
                            val dto = withContext(Dispatchers.IO) { uploadReceipt(ctx, uri) }
                            UiState.Success(dto)
                        } catch (e: Exception) {
                            UiState.Error(describeError(e))
                        }
                    }
                },
                enabled = state !is UiState.Loading,
            ) { Text("인식하기") }
        }

        Spacer(Modifier.height(16.dp))

        when (val s = state) {
            is UiState.Idle -> {}
            is UiState.Loading -> CircularProgressIndicator()
            is UiState.Error -> Text("오류: ${s.message}", color = MaterialTheme.colorScheme.error)
            is UiState.Success -> {
                ReceiptCard(s.receipt)
                Spacer(Modifier.height(12.dp))
                Button(
                    onClick = {
                        scope.launch {
                            dao.insert(s.receipt.toEntity())
                            saved = true
                        }
                    },
                    enabled = !saved,
                ) { Text(if (saved) "저장됨 ✓" else "저장하기") }
            }
        }
    }
}

// ======================================================================
// 저장된 내역 화면
// ======================================================================
@Composable
private fun HistoryScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val dao = remember { AppDatabase.get(ctx).receiptDao() }

    val list by dao.observeAll().collectAsState(initial = emptyList())
    val sum by dao.observeTotalSum().collectAsState(initial = 0)
    val won = remember { NumberFormat.getNumberInstance(Locale.KOREA) }

    // 선택된 항목이 있으면 상세, 없으면 목록.
    // selected 는 list 에서 파생되므로 항목이 삭제되면 자동으로 목록으로 돌아갑니다.
    var selectedId by rememberSaveable { mutableStateOf<Long?>(null) }
    val selected = list.firstOrNull { it.id == selectedId }

    if (selected != null) {
        DetailScreen(
            entity = selected,
            onBack = { selectedId = null },
            onDelete = { scope.launch { dao.delete(selected) } },
        )
        return
    }

    // --- 내보내기 / 서버 보내기 ---
    var exportMsg by remember { mutableStateOf<String?>(null) }
    var uploading by remember { mutableStateOf(false) }
    // 저장 위치를 사용자가 고르게 합니다(SAF) — 앱이 저장소 권한을 받을 필요가 없습니다.
    val saveCsv = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("text/csv")
    ) { uri ->
        if (uri == null) { exportMsg = null; return@rememberLauncherForActivityResult }
        exportMsg = try {
            ctx.contentResolver.openOutputStream(uri)?.use { out ->
                out.write(buildCsv(list).toByteArray(Charsets.UTF_8))
            } ?: error("파일을 열 수 없습니다")
            "저장했습니다 (${list.size}건)"
        } catch (e: Exception) {
            "저장 실패: ${e.message}"
        }
    }

    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
            Text("총 ${list.size}건", fontWeight = FontWeight.Medium)
            Text("합계 ${won.format(sum)}원", fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.height(8.dp))

        if (list.isEmpty()) {
            Text("저장된 내역이 없습니다.", style = MaterialTheme.typography.bodyMedium)
            return@Column
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(
                onClick = {
                    exportMsg = null
                    saveCsv.launch(exportFileName())
                },
                enabled = !uploading,
            ) { Text("CSV 저장") }

            OutlinedButton(
                onClick = {
                    exportMsg = try {
                        shareCsv(ctx, buildCsv(list))
                        null
                    } catch (e: Exception) {
                        "공유 실패: ${e.message}"
                    }
                },
                enabled = !uploading,
            ) { Text("공유") }

            OutlinedButton(
                onClick = {
                    uploading = true
                    exportMsg = null
                    scope.launch {
                        exportMsg = try {
                            val r = withContext(Dispatchers.IO) { uploadHistory(ctx, list) }
                            "서버로 보냈습니다 (${r.saved}건 · 서버 누적 ${r.total}건)"
                        } catch (e: Exception) {
                            "전송 실패: ${describeError(e)}"
                        }
                        uploading = false
                    }
                },
                enabled = !uploading,
            ) { Text("서버로") }
        }
        if (uploading) {
            Spacer(Modifier.height(8.dp))
            CircularProgressIndicator()
        }
        exportMsg?.let {
            Spacer(Modifier.height(4.dp))
            StatusText(it)
        }
        Spacer(Modifier.height(8.dp))

        LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(list, key = { it.id }) { r ->
                Card(
                    Modifier
                        .fillMaxWidth()
                        .clickable { selectedId = r.id }      // 탭하면 상세로
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                            Text(r.store ?: "(상호 미상)", fontWeight = FontWeight.Bold)
                            Text(r.total?.let { "${won.format(it)}원" } ?: "-",
                                fontWeight = FontWeight.Bold)
                        }
                        Text(
                            listOfNotNull(r.date, r.card).joinToString(" · ")
                                .ifBlank { "(정보 없음)" },
                            style = MaterialTheme.typography.bodySmall,
                        )
                        Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                            Text("품목 ${r.items.size}건",
                                style = MaterialTheme.typography.bodySmall)
                            if (r.notes.isNotEmpty()) {
                                Text("⚠ ${r.notes.size}",
                                    style = MaterialTheme.typography.bodySmall)
                            }
                        }
                    }
                }
            }
        }
    }
}

// ======================================================================
// 상세 화면
// ======================================================================
@Composable
private fun DetailScreen(
    entity: ReceiptEntity,
    onBack: () -> Unit,
    onDelete: () -> Unit,
) {
    var confirmDelete by remember { mutableStateOf(false) }
    val savedAt = remember(entity.savedAt) {
        SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.KOREA).format(Date(entity.savedAt))
    }

    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        TextButton(onClick = onBack) { Text("← 목록") }
        Spacer(Modifier.height(4.dp))

        ReceiptCard(entity.toDto())

        Spacer(Modifier.height(8.dp))
        Text("저장 시각 : $savedAt", style = MaterialTheme.typography.bodySmall)

        Spacer(Modifier.height(16.dp))
        if (!confirmDelete) {
            OutlinedButton(onClick = { confirmDelete = true }) { Text("삭제") }
        } else {
            Text("이 내역을 삭제할까요?", style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { onDelete(); onBack() }) { Text("삭제") }
                OutlinedButton(onClick = { confirmDelete = false }) { Text("취소") }
            }
        }
    }
}

// ======================================================================
// 설정 화면 — 서버 주소 / API 키
// ======================================================================
@Composable
private fun SettingsScreen() {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()

    val saved = remember { Settings.load(ctx) }
    var url by rememberSaveable { mutableStateOf(saved.url) }
    var key by rememberSaveable { mutableStateOf(saved.apiKey) }
    var testing by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<String?>(null) }

    Column(
        Modifier
            .fillMaxSize()
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
    ) {
        Text("서버 주소", fontWeight = FontWeight.Medium)
        OutlinedTextField(
            value = url,
            onValueChange = { url = it; result = null },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text("https://....trycloudflare.com") },
        )
        Text(
            "PC에서 터널을 다시 켜면 주소가 바뀝니다. 새 주소를 여기에 붙여넣으세요.",
            style = MaterialTheme.typography.bodySmall,
        )

        Spacer(Modifier.height(16.dp))

        Text("API 키", fontWeight = FontWeight.Medium)
        OutlinedTextField(
            value = key,
            onValueChange = { key = it; result = null },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
            placeholder = { Text("서버 실행 시 콘솔에 출력됩니다") },
        )
        Text(
            "PC의 api_key.txt 에 있는 값과 같아야 합니다.",
            style = MaterialTheme.typography.bodySmall,
        )

        Spacer(Modifier.height(20.dp))

        // 두 버튼 모두 저장부터 합니다 — 연결 테스트도 실제 인식과 같은 경로를 타도록.
        fun persist() {
            val saved = Settings.save(ctx, ServerConfig(url, key))
            url = saved.url                     // 보정된 주소를 화면에 반영
            key = saved.apiKey
        }

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(
                onClick = { persist(); result = "저장했습니다." },
                enabled = !testing,
            ) { Text("저장") }

            OutlinedButton(
                onClick = {
                    persist()
                    testing = true
                    result = null
                    scope.launch {
                        result = try {
                            withContext(Dispatchers.IO) { ApiClient.api(ctx).verify() }
                            "연결 성공 ✓ 주소와 키가 모두 맞습니다."
                        } catch (e: Exception) {
                            "실패: ${describeError(e)}"
                        }
                        testing = false
                    }
                },
                enabled = !testing,
            ) { Text("연결 테스트") }
        }

        Spacer(Modifier.height(12.dp))

        if (testing) CircularProgressIndicator()
        result?.let { StatusText(it, MaterialTheme.typography.bodyMedium) }
    }
}

// ======================================================================
// 공통 UI
// ======================================================================
@Composable
private fun ReceiptCard(r: ReceiptDto) {
    val won = remember { NumberFormat.getNumberInstance(Locale.KOREA) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp)) {
            Field("양식", r.profile.ifBlank { "(미상)" })
            Field("상호", r.store ?: "(인식 실패)")
            Field("날짜", r.date ?: "(인식 실패)")
            Field("카드", r.card ?: "(미확인)")
            HorizontalDivider(Modifier.padding(vertical = 8.dp))

            r.items.forEach { item ->
                Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                    Text(item.name, Modifier.weight(1f))
                    Text("${won.format(item.amount)}원")
                }
            }
            if (r.items.isEmpty()) Text("(품목 없음)", style = MaterialTheme.typography.bodySmall)

            HorizontalDivider(Modifier.padding(vertical = 8.dp))
            Row(Modifier.fillMaxWidth(), Arrangement.SpaceBetween) {
                Text("합계", fontWeight = FontWeight.Bold)
                Text(
                    r.total?.let { "${won.format(it)}원" } ?: "(인식 실패)",
                    fontWeight = FontWeight.Bold,
                )
            }
            r.notes.forEach { note ->
                Spacer(Modifier.height(6.dp))
                Text("⚠ $note", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/** 동작 결과 한 줄. '실패' 가 들어 있으면 오류색으로 — 판정 기준을 한 곳에 둡니다. */
@Composable
private fun StatusText(
    message: String,
    style: TextStyle = MaterialTheme.typography.bodySmall,
) {
    Text(
        message,
        style = style,
        color = if ("실패" in message) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurface,
    )
}

@Composable
private fun Field(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, Modifier.width(48.dp), fontWeight = FontWeight.Medium)
        Text(value)
    }
}

// ======================================================================
// 동작
// ======================================================================
private fun ReceiptDto.toEntity() = ReceiptEntity(
    store = store,
    date = date,
    card = card,
    total = total,
    profile = profile,
    items = items,
    notes = notes,
    savedAt = System.currentTimeMillis(),
)

/** 저장된 항목도 인식 결과와 같은 카드 UI로 보여주기 위한 변환 */
private fun ReceiptEntity.toDto() = ReceiptDto(
    store = store,
    date = date,
    card = card,
    total = total,
    profile = profile,
    items = items,
    notes = notes,
)

/** 사진을 서버로 업로드하고 결과를 받습니다. */
private suspend fun uploadReceipt(ctx: Context, uri: Uri): ReceiptDto {
    // content:// URI 는 바로 File 로 못 쓰므로 캐시에 복사합니다.
    val file = File(ctx.cacheDir, "upload.jpg")
    ctx.contentResolver.openInputStream(uri).use { input ->
        requireNotNull(input) { "이미지를 열 수 없습니다" }
        file.outputStream().use { input.copyTo(it) }
    }
    val part = MultipartBody.Part.createFormData(
        "image", file.name, file.asRequestBody("image/*".toMediaType())
    )
    return ApiClient.api(ctx).extract(part)
}

/** CSV 를 다른 앱(카톡·메일·드라이브 등)으로 보냅니다. */
private fun shareCsv(ctx: Context, csv: String) {
    val file = writeShareFile(ctx, csv, exportFileName())
    val uri = cacheUri(ctx, file)
    val intent = Intent(Intent.ACTION_SEND).apply {
        type = "text/csv"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_SUBJECT, file.name)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    ctx.startActivity(Intent.createChooser(intent, "영수증 내역 보내기"))
}

/** 카메라 촬영 결과를 받을 임시 파일 URI (FileProvider 경유) */
private fun createTempImageUri(ctx: Context): Uri {
    val dir = File(ctx.cacheDir, "captures").apply { mkdirs() }
    // 촬영본은 사진 한 장당 수 MB 라 그냥 두면 캐시가 계속 불어납니다.
    // 하루 지난 것만 지웁니다 — 방금 찍고 아직 인식 안 한 파일은 건드리지 않도록.
    val cutoff = System.currentTimeMillis() - 24 * 60 * 60 * 1000
    dir.listFiles()?.forEach { if (it.lastModified() < cutoff) it.delete() }

    val file = File.createTempFile("receipt_", ".jpg", dir)
    return cacheUri(ctx, file)
}
