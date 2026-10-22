package os.stream.tv

import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.coroutines.launch
import java.util.UUID

/**
 * Single-activity Android TV client: a D-pad channel column on the left and a
 * Media3/ExoPlayer surface. Playback uses the hub's /live/{id}/index.m3u8,
 * so the upstream is shared by the hub across every device in the house.
 *
 * Scaffold: focuses on the playback path. A production build would use the
 * Leanback BrowseFragment for rows/cards and a settings screen for the hub
 * address + pairing.
 */
class MainActivity : AppCompatActivity() {

    // Emulator reaches the host hub at 10.0.2.2; set LAN IP on real hardware.
    private val hubBase = "http://10.0.2.2:8099"
    private val hub by lazy { HubClient(hubBase) }
    private val deviceId by lazy { deviceId() }

    private lateinit var player: ExoPlayer
    private lateinit var playerView: PlayerView
    private lateinit var channelList: LinearLayout
    private var sessionId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
        channelList = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(420, LinearLayout.LayoutParams.MATCH_PARENT)
        }
        playerView = PlayerView(this).apply {
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.MATCH_PARENT, 1f)
        }
        root.addView(channelList); root.addView(playerView)
        setContentView(root)

        player = ExoPlayer.Builder(this).build()
        playerView.player = player

        loadChannels()
    }

    private fun loadChannels() = lifecycleScope.launch {
        runCatching { hub.listSources() }
            .onSuccess { sources ->
                channelList.removeAllViews()
                if (sources.isEmpty()) channelList.addView(label("No sources on hub"))
                sources.forEachIndexed { i, s ->
                    val b = Button(this@MainActivity).apply {
                        text = "${s.name}\n${s.kind.uppercase()}"
                        isFocusable = true
                        setOnClickListener { playSource(s) }
                    }
                    channelList.addView(b)
                    if (i == 0) b.requestFocus()
                }
            }
            .onFailure { channelList.addView(label("Hub unreachable: ${it.message}")) }
    }

    private fun playSource(s: HubClient.Source) = lifecycleScope.launch {
        val res = runCatching { hub.play(deviceId, s.id) }.getOrNull()
        if (res == null || !res.ok) {
            toast("Can't play: ${res?.reason ?: "error"}"); return@launch
        }
        val url = hub.absolute(res.playUrl!!)
        player.setMediaItem(MediaItem.fromUri(url))
        player.prepare()
        player.playWhenReady = true
        toast("${s.name} · ${res.mode}")
    }

    private fun label(t: String) = TextView(this).apply { text = t; setPadding(24, 24, 24, 24) }
    private fun toast(t: String) = Toast.makeText(this, t, Toast.LENGTH_SHORT).show()

    private fun deviceId(): String {
        val p = getSharedPreferences("streamos", MODE_PRIVATE)
        return p.getString("device_id", null) ?: UUID.randomUUID().toString().take(12)
            .also { p.edit().putString("device_id", it).apply() }
    }

    override fun onStop() {
        super.onStop()
        player.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        player.release()
    }
}
