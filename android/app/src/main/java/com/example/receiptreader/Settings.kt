package com.example.receiptreader

import android.content.Context
import java.util.UUID

/**
 * 서버 접속 설정.
 *
 * 주소를 앱에 박아두지 않고 기기에 저장하는 이유: Cloudflare 무료 터널은
 * 서버를 다시 띄울 때마다 주소가 바뀝니다. 설정 화면에서 붙여넣을 수 있으면
 * 그때마다 APK 를 다시 빌드하지 않아도 됩니다.
 */
data class ServerConfig(val url: String, val apiKey: String)

object Settings {
    private const val PREF = "server"
    private const val KEY_URL = "url"
    private const val KEY_API = "api_key"
    private const val KEY_DEVICE = "device_id"

    private fun prefs(ctx: Context) =
        ctx.applicationContext.getSharedPreferences(PREF, Context.MODE_PRIVATE)

    fun load(ctx: Context): ServerConfig {
        val p = prefs(ctx)
        return ServerConfig(
            url = p.getString(KEY_URL, null) ?: BuildConfig.SERVER_URL,
            apiKey = p.getString(KEY_API, null) ?: "",
        )
    }

    /** 저장하고, 실제로 저장된(정규화된) 값을 돌려줍니다 — 화면에 바로 반영하도록. */
    fun save(ctx: Context, cfg: ServerConfig): ServerConfig {
        val saved = ServerConfig(normalizeUrl(cfg.url), cfg.apiKey.trim())
        prefs(ctx).edit()
            .putString(KEY_URL, saved.url)
            .putString(KEY_API, saved.apiKey)
            .apply()
        return saved
    }

    /**
     * 이 기기의 고유 id — 최초 1회 만들어 계속 씁니다.
     *
     * 서버는 (기기 id + 폰 DB 행번호)를 묶어 중복을 판정합니다. 그래서 앱은
     * 무엇을 이미 올렸는지 기억할 필요 없이 전체를 다시 보내면 되고,
     * 나중에 다른 기기가 붙어도 서로 섞이지 않습니다.
     */
    fun deviceId(ctx: Context): String {
        val p = prefs(ctx)
        p.getString(KEY_DEVICE, null)?.let { return it }
        val id = UUID.randomUUID().toString()
        p.edit().putString(KEY_DEVICE, id).apply()
        return id
    }

    /**
     * 붙여넣은 주소를 Retrofit 이 받아들이는 형태로 보정합니다.
     * (baseUrl 은 '/' 로 끝나야 하고, 스킴이 있어야 합니다)
     */
    fun normalizeUrl(raw: String): String {
        var s = raw.trim()
        if (s.isEmpty()) return s
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "https://$s"
        if (!s.endsWith("/")) s += "/"
        return s
    }
}
