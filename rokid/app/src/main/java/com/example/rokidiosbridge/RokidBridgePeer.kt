package com.example.rokidiosbridge

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaRecorder
import android.util.Log
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.Camera2Enumerator
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoCapturer
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import org.webrtc.audio.JavaAudioDeviceModule
import java.nio.ByteBuffer
import java.nio.charset.StandardCharsets
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

class RokidBridgePeer(
    private val context: Context,
    private val listener: Listener
) {
    companion object {
        private const val TAG = "RokidBridgePeer"
    }

    interface Listener {
        fun onLog(message: String)
        fun onConnectionStateChanged(state: PeerConnection.IceConnectionState)
        fun onDisplayTextChanged(text: String)
        fun onStatusTextChanged(text: String)
        fun onError(message: String, throwable: Throwable? = null)
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private val okHttp = OkHttpClient()
    private val eglBase: EglBase = EglBase.create()

    private val audioDeviceModule by lazy {
        JavaAudioDeviceModule.builder(context)
            .setSampleRate(16_000)
            .setUseHardwareAcousticEchoCanceler(false)
            .setUseHardwareNoiseSuppressor(false)
            .setUseStereoInput(false)
            .setUseStereoOutput(false)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioSource(MediaRecorder.AudioSource.MIC)
            .createAudioDeviceModule().apply {
                setMicrophoneMute(false)
                setSpeakerMute(false)
            }
    }

    private val peerConnectionFactory: PeerConnectionFactory by lazy {
        createPeerConnectionFactory()
    }

    private val offerConstraints = MediaConstraints().apply {
        mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
        mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "false"))
    }

    private var peerConnection: PeerConnection? = null
    private var localAudioSource: AudioSource? = null
    private var localAudioTrack: AudioTrack? = null
    private var localVideoSource: VideoSource? = null
    private var localVideoTrack: VideoTrack? = null
    private var localVideoCapturer: VideoCapturer? = null
    private var surfaceTextureHelper: SurfaceTextureHelper? = null
    private var dataChannel: DataChannel? = null
    private var iceGatheringDeferred: CompletableDeferred<Unit>? = null

    fun start(sessionUrl: String) {
        scope.launch {
            if (peerConnection != null) {
                listener.onLog("Bridge session already active")
                return@launch
            }
            try {
                startInternal(sessionUrl)
            } catch (t: Throwable) {
                Log.e(TAG, "Failed to connect bridge session", t)
                listener.onError("Failed to connect to Mac bridge", t)
                stopInternal()
            }
        }
    }

    fun stop() {
        runBlocking {
            stopInternal()
        }
    }

    fun release() {
        runBlocking {
            stopInternal()
        }
        scope.cancel()
        audioDeviceModule.release()
        peerConnectionFactory.dispose()
        eglBase.release()
    }

    private suspend fun startInternal(sessionUrl: String) = withContext(Dispatchers.Default) {
        val pc = createPeerConnection()
        peerConnection = pc

        createAndAddLocalTracks(pc)
        setupControlChannel(pc)

        val offer = createOffer(pc)
        setLocalDescription(pc, offer)
        waitForIceGatheringComplete(pc)

        val localDescription = pc.localDescription ?: error("LocalDescription is null")
        listener.onLog("Sending offer to Mac backend")
        val answerSdp = sendOfferAndGetAnswer(sessionUrl, normalizeSdp(localDescription.description))
        setRemoteDescription(pc, SessionDescription(SessionDescription.Type.ANSWER, answerSdp))
        listener.onLog("Mac bridge negotiation complete")
    }

    private fun createPeerConnectionFactory(): PeerConnectionFactory {
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .createInitializationOptions()
        )

        val encoderFactory = DefaultVideoEncoderFactory(eglBase.eglBaseContext, true, true)
        val decoderFactory = DefaultVideoDecoderFactory(eglBase.eglBaseContext)

        return PeerConnectionFactory.builder()
            .setAudioDeviceModule(audioDeviceModule)
            .setVideoEncoderFactory(encoderFactory)
            .setVideoDecoderFactory(decoderFactory)
            .createPeerConnectionFactory()
    }

    private fun createPeerConnection(): PeerConnection {
        val config = PeerConnection.RTCConfiguration(emptyList()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
        }

        return peerConnectionFactory.createPeerConnection(config, object : PeerConnection.Observer {
            override fun onSignalingChange(newState: PeerConnection.SignalingState) {
                listener.onLog("Signaling: $newState")
            }

            override fun onIceConnectionChange(newState: PeerConnection.IceConnectionState) {
                listener.onConnectionStateChanged(newState)
            }

            override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit

            override fun onIceGatheringChange(newState: PeerConnection.IceGatheringState) {
                listener.onLog("ICE gathering: $newState")
                if (newState == PeerConnection.IceGatheringState.COMPLETE) {
                    iceGatheringDeferred?.complete(Unit)
                }
            }

            override fun onIceCandidate(candidate: IceCandidate) {
                listener.onLog("ICE candidate: ${candidate.sdpMid}:${candidate.sdpMLineIndex}")
            }

            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit

            override fun onAddStream(stream: MediaStream) = Unit

            override fun onRemoveStream(stream: MediaStream) = Unit

            override fun onDataChannel(dc: DataChannel) {
                listener.onLog("Ignoring remote data channel: ${dc.label()}")
            }

            override fun onRenegotiationNeeded() {
                listener.onLog("Renegotiation requested")
            }

            override fun onAddTrack(receiver: RtpReceiver, mediaStreams: Array<out MediaStream>) {
                val track = receiver.track()
                when (track?.kind()) {
                    "audio" -> {
                        (track as? AudioTrack)?.setEnabled(true)
                        listener.onLog("Remote audio track ready")
                    }

                    else -> listener.onLog("Remote ${track?.kind() ?: "unknown"} track ignored")
                }
            }
        }) ?: error("Failed to create PeerConnection")
    }

    private fun setupControlChannel(pc: PeerConnection) {
        val channel = pc.createDataChannel(BridgeConfig.DATA_CHANNEL_LABEL, DataChannel.Init())
        dataChannel = channel
        registerDataChannelObserver(channel)
    }

    private fun registerDataChannelObserver(dc: DataChannel) {
        dc.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previousAmount: Long) = Unit

            override fun onStateChange() {
                listener.onLog("Control channel state: ${dc.state()}")
                if (dc.state() == DataChannel.State.OPEN) {
                    sendJson(
                        JSONObject()
                            .put("type", "wearable_ready")
                            .put("device", android.os.Build.MODEL)
                    )
                }
            }

            override fun onMessage(buffer: DataChannel.Buffer) {
                if (buffer.binary) {
                    listener.onLog("Ignoring binary control message")
                    return
                }
                val bytes = ByteArray(buffer.data.remaining())
                buffer.data.get(bytes)
                handleControlMessage(String(bytes, StandardCharsets.UTF_8))
            }
        })
    }

    private fun handleControlMessage(message: String) {
        runCatching {
            val json = JSONObject(message)
            when (json.optString("type")) {
                "display_text" -> listener.onDisplayTextChanged(json.optString("text").trim())
                "status" -> listener.onStatusTextChanged(json.optString("text").trim())
                "clear_display" -> listener.onDisplayTextChanged("")
                "ping" -> {
                    val pong = JSONObject().put("type", "pong")
                    json.optString("id").takeIf { it.isNotBlank() }?.let { pong.put("id", it) }
                    sendJson(pong)
                }

                else -> listener.onLog("Control: $message")
            }
        }.getOrElse {
            listener.onDisplayTextChanged(message.trim())
        }
    }

    private fun sendJson(json: JSONObject) {
        val dc = dataChannel ?: return
        if (dc.state() != DataChannel.State.OPEN) return
        val bytes = json.toString().toByteArray(StandardCharsets.UTF_8)
        dc.send(DataChannel.Buffer(ByteBuffer.wrap(bytes), false))
    }

    private fun createAndAddLocalTracks(pc: PeerConnection) {
        localAudioSource = peerConnectionFactory.createAudioSource(MediaConstraints())
        localAudioTrack = peerConnectionFactory.createAudioTrack("wearable-audio", localAudioSource)
        localAudioTrack?.setEnabled(true)
        localAudioTrack?.let { pc.addTrack(it) }

        val videoCapturer = createCameraCapturer()
        if (videoCapturer == null) {
            listener.onLog("No camera capturer available")
            return
        }
        localVideoCapturer = videoCapturer

        surfaceTextureHelper = SurfaceTextureHelper.create("BridgeCapture", eglBase.eglBaseContext)
        localVideoSource = peerConnectionFactory.createVideoSource(videoCapturer.isScreencast).apply {
            adaptOutputFormat(720, 1280, 10)
        }

        localVideoSource?.let { source ->
            videoCapturer.initialize(surfaceTextureHelper, context, source.capturerObserver)
            videoCapturer.startCapture(720, 1280, 15)
            localVideoTrack = peerConnectionFactory.createVideoTrack("wearable-video", source)
            localVideoTrack?.setEnabled(true)
            localVideoTrack?.let { pc.addTrack(it) }
        }
    }

    private fun createCameraCapturer(): VideoCapturer? {
        val enumerator = Camera2Enumerator(context)
        val deviceNames = enumerator.deviceNames

        val preferred = selectPreferredCameraName(enumerator, deviceNames)
        if (preferred != null) {
            enumerator.createCapturer(preferred, null)?.let { capturer ->
                listener.onLog("Using camera: $preferred")
                return capturer
            }
        }

        for (name in deviceNames) {
            enumerator.createCapturer(name, null)?.let { capturer ->
                listener.onLog("Using fallback camera: $name")
                return capturer
            }
        }

        return null
    }

    private fun selectPreferredCameraName(
        enumerator: Camera2Enumerator,
        deviceNames: Array<String>
    ): String? {
        var fallback: String? = null
        for (name in deviceNames) {
            if (!enumerator.isFrontFacing(name)) return name
            if (fallback == null) fallback = name
        }
        return fallback
    }

    private suspend fun createOffer(pc: PeerConnection): SessionDescription =
        suspendCancellableCoroutine { cont ->
            pc.createOffer(object : org.webrtc.SdpObserver {
                override fun onCreateSuccess(desc: SessionDescription?) {
                    if (desc != null && !cont.isCompleted) {
                        cont.resume(desc)
                    }
                }

                override fun onCreateFailure(error: String?) {
                    if (!cont.isCompleted) {
                        cont.resumeWithException(RuntimeException("createOffer failed: $error"))
                    }
                }

                override fun onSetSuccess() = Unit
                override fun onSetFailure(error: String?) = Unit
            }, offerConstraints)
        }

    private suspend fun setLocalDescription(pc: PeerConnection, desc: SessionDescription) =
        suspendCancellableCoroutine<Unit> { cont ->
            pc.setLocalDescription(object : org.webrtc.SdpObserver {
                override fun onSetSuccess() {
                    if (!cont.isCompleted) cont.resume(Unit)
                }

                override fun onSetFailure(error: String?) {
                    if (!cont.isCompleted) {
                        cont.resumeWithException(RuntimeException("setLocalDescription failed: $error"))
                    }
                }

                override fun onCreateSuccess(desc: SessionDescription?) = Unit
                override fun onCreateFailure(error: String?) = Unit
            }, desc)
        }

    private suspend fun setRemoteDescription(pc: PeerConnection, desc: SessionDescription) =
        suspendCancellableCoroutine<Unit> { cont ->
            pc.setRemoteDescription(object : org.webrtc.SdpObserver {
                override fun onSetSuccess() {
                    if (!cont.isCompleted) cont.resume(Unit)
                }

                override fun onSetFailure(error: String?) {
                    if (!cont.isCompleted) {
                        cont.resumeWithException(RuntimeException("setRemoteDescription failed: $error"))
                    }
                }

                override fun onCreateSuccess(desc: SessionDescription?) = Unit
                override fun onCreateFailure(error: String?) = Unit
            }, desc)
        }

    private suspend fun waitForIceGatheringComplete(pc: PeerConnection) {
        if (pc.iceGatheringState() == PeerConnection.IceGatheringState.COMPLETE) return
        val deferred = CompletableDeferred<Unit>()
        iceGatheringDeferred = deferred
        deferred.await()
        iceGatheringDeferred = null
    }

    private suspend fun sendOfferAndGetAnswer(sessionUrl: String, offerSdp: String): String =
        withContext(Dispatchers.IO) {
            val body = offerSdp.toRequestBody("application/sdp".toMediaType())
            val request = Request.Builder()
                .url(sessionUrl)
                .post(body)
                .build()

            okHttp.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    val errorBody = response.body?.string()
                    throw IllegalStateException(
                        "Session request failed: HTTP ${response.code} ${response.message} ${errorBody.orEmpty()}".trim()
                    )
                }
                val responseText = response.body?.string().orEmpty()
                parseAnswerSdp(responseText)
            }
        }

    private fun parseAnswerSdp(responseText: String): String {
        if (responseText.isBlank()) {
            error("Empty SDP answer")
        }
        if (responseText.trimStart().startsWith("{")) {
            val json = JSONObject(responseText)
            return normalizeSdp(json.optString("sdp", ""))
        }
        return normalizeSdp(responseText)
    }

    private fun normalizeSdp(raw: String): String {
        val unified = raw.replace("\r\n", "\n").replace('\r', '\n').trim()
        if (unified.isBlank()) return ""
        return unified.lines().joinToString(separator = "\r\n") + "\r\n"
    }

    private suspend fun stopInternal() = withContext(Dispatchers.Default) {
        runCatching { dataChannel?.close() }
        dataChannel = null
        iceGatheringDeferred = null

        runCatching {
            localVideoCapturer?.let { capturer ->
                try {
                    capturer.stopCapture()
                } catch (_: InterruptedException) {
                    listener.onLog("Camera stop interrupted")
                }
                capturer.dispose()
            }
        }
        localVideoCapturer = null

        surfaceTextureHelper?.dispose()
        surfaceTextureHelper = null

        localVideoTrack?.dispose()
        localVideoTrack = null
        localVideoSource?.dispose()
        localVideoSource = null

        localAudioTrack?.dispose()
        localAudioTrack = null
        localAudioSource?.dispose()
        localAudioSource = null

        peerConnection?.close()
        peerConnection?.dispose()
        peerConnection = null

        Log.d(TAG, "Peer resources released")
    }
}
