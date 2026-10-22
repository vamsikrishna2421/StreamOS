package os.stream.tv

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * Minimal client for the StreamOS hub API. Deliberately dependency-light
 * (HttpURLConnection + org.json) so the scaffold builds with nothing exotic.
 *
 * The hub does the stream sharing; this client only lists sources, asks to
 * play, and reports heartbeats/history — it is a polite, thin player.
 */
class HubClient(private val baseUrl: String) {

    data class Source(val id: String, val name: String, val kind: String)
    data class PlayResult(val ok: Boolean, val mode: String,
                          val playUrl: String?, val reason: String?)

    suspend fun listSources(): List<Source> = withContext(Dispatchers.IO) {
        val arr = JSONArray(get("/api/sources?enabled_only=true"))
        (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            Source(o.getString("id"), o.getString("name"), o.getString("kind"))
        }
    }

    suspend fun play(deviceId: String, sourceId: String): PlayResult =
        withContext(Dispatchers.IO) {
            val q = "device_id=${enc(deviceId)}&source_id=${enc(sourceId)}"
            val o = JSONObject(post("/api/play?$q"))
            PlayResult(
                o.getBoolean("ok"),
                o.optString("mode"),
                o.optString("play_url", null),
                o.optString("reason", null),
            )
        }

    suspend fun heartbeat(sessionId: String, positionS: Double) =
        withContext(Dispatchers.IO) {
            runCatching { post("/api/sessions/$sessionId/heartbeat?position_s=$positionS") }
            Unit
        }

    fun absolute(playUrl: String): String =
        if (playUrl.startsWith("http")) playUrl else baseUrl.trimEnd('/') + playUrl

    // --- http helpers ---
    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
    private fun get(path: String) = request("GET", path)
    private fun post(path: String) = request("POST", path)

    private fun request(method: String, path: String): String {
        val c = (URL(baseUrl.trimEnd('/') + path).openConnection() as HttpURLConnection)
        return try {
            c.requestMethod = method
            c.connectTimeout = 5000; c.readTimeout = 8000
            c.inputStream.bufferedReader().use { it.readText() }
        } finally { c.disconnect() }
    }
}
