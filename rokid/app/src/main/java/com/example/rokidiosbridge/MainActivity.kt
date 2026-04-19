package com.example.rokidiosbridge

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.format.DateFormat
import android.util.Log
import android.view.KeyEvent
import android.view.View
import android.view.ViewTreeObserver
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.example.rokidiosbridge.databinding.ActivityMainBinding
import org.webrtc.PeerConnection
import java.util.Date

class MainActivity : AppCompatActivity(), RokidBridgePeer.Listener {

    companion object {
        private const val TAG = "RokidBridgeUi"
        private const val REQUEST_PERMISSIONS = 1001
        private const val MAX_LOG_LINES = 12
    }

    private lateinit var binding: ActivityMainBinding

    private var bridgePeer: RokidBridgePeer? = null
    private val reconnectHandler = Handler(Looper.getMainLooper())
    private val sessionUrl: String by lazy { BuildConfig.BRIDGE_SESSION_URL.trim() }

    private val logLines = ArrayDeque<String>()
    private var currentConnectionState = "Idle"
    private var currentStatus = ""
    private var permissionsGranted = false
    private var maintainBridgeSession = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        binding.tvDisplay.text = getString(R.string.display_waiting)
        currentStatus = getString(R.string.status_initializing)
        renderStatus()
        appendLog(getString(R.string.control_hint))
        setupAutoScroll()
        ensurePermissions()
    }

    override fun onStart() {
        super.onStart()
        maintainBridgeSession = true
        startBridgeIfPossible()
    }

    override fun onStop() {
        maintainBridgeSession = false
        reconnectHandler.removeCallbacksAndMessages(null)
        bridgePeer?.stop()
        updateConnection("Idle")
        currentStatus = getString(R.string.status_background)
        renderStatus()
        super.onStop()
    }

    override fun onDestroy() {
        maintainBridgeSession = false
        reconnectHandler.removeCallbacksAndMessages(null)
        stopBridge()
        window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        super.onDestroy()
    }

    override fun onKeyUp(keyCode: Int, event: KeyEvent?): Boolean {
        return when (keyCode) {
            KeyEvent.KEYCODE_DPAD_CENTER,
            KeyEvent.KEYCODE_ENTER -> {
                appendLog("Manual reconnect requested")
                restartBridgeSession()
                true
            }

            else -> super.onKeyUp(keyCode, event)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != REQUEST_PERMISSIONS) return

        if (grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            permissionsGranted = true
            startBridgeIfPossible()
        } else {
            permissionsGranted = false
            currentStatus = getString(R.string.status_permissions_denied)
            renderStatus()
            appendLog("Permissions denied")
        }
    }

    override fun onLog(message: String) {
        runOnUiThread {
            appendLog(message)
        }
    }

    override fun onConnectionStateChanged(state: PeerConnection.IceConnectionState) {
        runOnUiThread {
            updateConnection(state.name)
            when (state) {
                PeerConnection.IceConnectionState.CONNECTED,
                PeerConnection.IceConnectionState.COMPLETED -> {
                    reconnectHandler.removeCallbacksAndMessages(null)
                    currentStatus = "Streaming to Mac bridge."
                    renderStatus()
                }

                PeerConnection.IceConnectionState.DISCONNECTED,
                PeerConnection.IceConnectionState.CLOSED,
                PeerConnection.IceConnectionState.FAILED -> {
                    currentStatus = if (maintainBridgeSession) {
                        "Link lost. Reconnecting…"
                    } else {
                        getString(R.string.status_background)
                    }
                    renderStatus()
                    if (maintainBridgeSession) {
                        scheduleReconnect()
                    }
                }

                else -> Unit
            }
        }
    }

    override fun onDisplayTextChanged(text: String) {
        runOnUiThread {
            binding.tvDisplay.text = text.ifBlank { getString(R.string.display_waiting) }
        }
    }

    override fun onStatusTextChanged(text: String) {
        runOnUiThread {
            currentStatus = text.ifBlank { "Streaming to Mac bridge." }
            renderStatus()
        }
    }

    override fun onError(message: String, throwable: Throwable?) {
        runOnUiThread {
            appendLog("Error: $message")
            currentStatus = message
            renderStatus()
            if (maintainBridgeSession) {
                scheduleReconnect()
            }
        }
        Log.e(TAG, message, throwable)
    }

    private fun ensurePermissions() {
        val missing = buildList {
            if (!hasPermission(Manifest.permission.CAMERA)) add(Manifest.permission.CAMERA)
            if (!hasPermission(Manifest.permission.RECORD_AUDIO)) add(Manifest.permission.RECORD_AUDIO)
        }

        if (missing.isEmpty()) {
            permissionsGranted = true
            startBridgeIfPossible()
        } else {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), REQUEST_PERMISSIONS)
        }
    }

    private fun startBridgeIfPossible() {
        if (!maintainBridgeSession) return
        if (!permissionsGranted) return
        if (sessionUrl.isBlank()) {
            updateConnection("Config")
            currentStatus = "Set BRIDGE_SESSION_URL in rokid/local.properties."
            renderStatus()
            appendLog("Missing BRIDGE_SESSION_URL")
            return
        }

        if (bridgePeer == null) {
            bridgePeer = RokidBridgePeer(applicationContext, this)
        }

        reconnectHandler.removeCallbacksAndMessages(null)
        binding.tvDisplay.text = getString(R.string.display_waiting)
        updateConnection("Connecting")
        currentStatus = "Connecting to Mac bridge…"
        renderStatus()
        bridgePeer?.start(sessionUrl)
    }

    private fun restartBridgeSession() {
        reconnectHandler.removeCallbacksAndMessages(null)
        if (bridgePeer == null) {
            startBridgeIfPossible()
            return
        }
        bridgePeer?.stop()
        bridgePeer?.start(sessionUrl)
        updateConnection("Reconnecting")
        currentStatus = "Reconnecting to Mac bridge…"
        renderStatus()
    }

    private fun scheduleReconnect() {
        if (sessionUrl.isBlank()) return
        reconnectHandler.removeCallbacksAndMessages(null)
        reconnectHandler.postDelayed(
            { if (!isFinishing && !isDestroyed) restartBridgeSession() },
            BridgeConfig.RECONNECT_DELAY_MS
        )
    }

    private fun stopBridge() {
        bridgePeer?.release()
        bridgePeer = null
    }

    private fun hasPermission(permission: String): Boolean {
        return ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
    }

    private fun updateConnection(text: String) {
        currentConnectionState = text
        renderStatus()
    }

    private fun renderStatus() {
        binding.tvConnection.text = "Link: $currentConnectionState"
        binding.tvService.text = if (sessionUrl.isBlank()) {
            "Backend: configure BRIDGE_SESSION_URL"
        } else {
            "Backend: $sessionUrl"
        }
        binding.tvStatus.text = buildString {
            append(currentStatus.ifBlank { getString(R.string.status_ready) })
            append('\n')
            append(getString(R.string.control_hint))
        }
    }

    private fun appendLog(message: String) {
        Log.d(TAG, message)
        val timestamp = DateFormat.format("HH:mm:ss", Date()).toString()
        logLines.addLast("$timestamp  $message")
        while (logLines.size > MAX_LOG_LINES) {
            logLines.removeFirst()
        }
        binding.tvLog.text = logLines.joinToString("\n")
    }

    private fun setupAutoScroll() {
        binding.tvLog.viewTreeObserver.addOnGlobalLayoutListener(
            object : ViewTreeObserver.OnGlobalLayoutListener {
                override fun onGlobalLayout() {
                    binding.logScrollView.post {
                        binding.logScrollView.fullScroll(View.FOCUS_DOWN)
                    }
                }
            }
        )
    }
}
