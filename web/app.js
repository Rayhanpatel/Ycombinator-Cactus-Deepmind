// HVAC Copilot — browser client for the Mac-local Cactus server.

const $ = (id) => document.getElementById(id);

const statusEl = $("status");
const kbBadge = $("kb-badge");
const ttftBadge = $("ttft-badge");
const transcriptEl = $("transcript");
const textInput = $("text-input");
const composer = $("composer");
const micBtn = $("mic-btn");
const toolLog = $("tool-log");
const findingsCount = $("findings-count");
const safetyCount = $("safety-count");
const scopeCount = $("scope-count");
const sessionJson = $("session-json");
const resetBtn = $("reset-btn");
const safetyBanner = $("safety-banner");
const safetyDetail = $("safety-detail");
const camEl = $("cam");
const camBtn = $("cam-btn");
const camCanvas = $("cam-canvas");

let ws;
let currentAssistantMsg = null;
let mediaRecorder = null;
let audioStream = null;
let videoStream = null;
let pendingFrameB64 = null;          // last-captured JPEG keyframe (reserved for later turns)
let frameInterval = null;

function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

function addMessage(role, text = "") {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  transcriptEl.appendChild(div);
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
  return div;
}

function appendToAssistant(token) {
  if (!currentAssistantMsg) currentAssistantMsg = addMessage("assistant", "");
  currentAssistantMsg.textContent += token;
  transcriptEl.scrollTop = transcriptEl.scrollHeight;
}

function finishAssistant(finalText, stats) {
  if (currentAssistantMsg) {
    // Use the final text from the server (it has tool-call syntax stripped).
    if (finalText) currentAssistantMsg.textContent = finalText;
    currentAssistantMsg = null;
  } else if (finalText) {
    addMessage("assistant", finalText);
  }
  if (stats && stats.ttft_ms) {
    ttftBadge.textContent = `TTFT ${Math.round(stats.ttft_ms)}ms · ${stats.decode_tps ? Math.round(stats.decode_tps) : "-"} tok/s`;
  }
  setStatus("ready", "connected");

  // Speak the assistant's response via browser TTS for the voice-agent demo feel.
  if (finalText && "speechSynthesis" in window) {
    const u = new SpeechSynthesisUtterance(finalText);
    u.rate = 1.05;
    u.pitch = 1.0;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }
}

function toolEntry(payload) {
  const { name, arguments: args, result } = payload;
  const div = document.createElement("div");
  div.className = "tool-entry " + ({
    query_kb: "kb",
    log_finding: "finding",
    flag_safety: "safety",
    flag_scope_change: "scope",
    close_job: "close",
  }[name] || "");

  const head = document.createElement("div");
  head.className = "tool-name";
  head.textContent = name;
  div.appendChild(head);

  if (name === "query_kb" && result && result.results) {
    result.results.forEach((hit) => {
      const row = document.createElement("div");
      row.className = "tool-kb-hit";
      row.innerHTML = `<span class="id">${hit.id}</span> · score ${hit.score}<br><span class="dx">${hit.diagnosis || ""}</span>`;
      div.appendChild(row);
    });
  } else if (name === "log_finding" && result && result.finding) {
    const f = result.finding;
    const row = document.createElement("div");
    row.className = "tool-kb-hit";
    row.innerHTML = `<span class="id">${f.location}</span> · ${f.severity}<br><span class="dx">${f.issue}${f.part_number ? " · " + f.part_number : ""}</span>`;
    div.appendChild(row);
  } else if (name === "flag_safety" && result && result.alert) {
    const a = result.alert;
    const row = document.createElement("div");
    row.className = "tool-kb-hit";
    row.innerHTML = `<span class="id">${a.level.toUpperCase()}: ${a.hazard}</span><br><span class="dx">${a.immediate_action}</span>`;
    div.appendChild(row);
  } else if (name === "flag_scope_change" && result && result.scope_change) {
    const c = result.scope_change;
    const row = document.createElement("div");
    row.className = "tool-kb-hit";
    row.innerHTML = `<span class="id">${c.original_scope} → ${c.new_scope}</span><br><span class="dx">${c.reason}${c.estimated_extra_time_minutes ? " · +" + c.estimated_extra_time_minutes + " min" : ""}</span>`;
    div.appendChild(row);
  } else if (name === "close_job" && result && result.closure) {
    const c = result.closure;
    const row = document.createElement("div");
    row.className = "tool-kb-hit";
    row.innerHTML = `<span class="id">JOB CLOSED</span><br><span class="dx">${c.summary}<br>Parts: ${c.parts_used.join(", ") || "(none)"}${c.follow_up_required ? " · follow-up required" : ""}</span>`;
    div.appendChild(row);
  } else {
    const row = document.createElement("div");
    row.className = "tool-kb-hit";
    row.innerHTML = `<span class="dx">${JSON.stringify(args)}</span>`;
    div.appendChild(row);
  }

  toolLog.prepend(div);
}

function updateSession(state) {
  findingsCount.textContent = state.findings.length;
  safetyCount.textContent = state.safety_alerts.length;
  scopeCount.textContent = state.scope_changes.length;
  sessionJson.textContent = JSON.stringify(state, null, 2);

  if (state.is_stopped && state.safety_alerts.length > 0) {
    const a = state.safety_alerts[state.safety_alerts.length - 1];
    safetyDetail.textContent = `${a.hazard} — ${a.immediate_action}`;
    safetyBanner.classList.remove("hidden");
  } else if (state.safety_alerts.length === 0) {
    safetyBanner.classList.add("hidden");
  }
}

function connect() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws/session`);

  ws.onopen = () => setStatus("connecting…");
  ws.onclose = () => setStatus("disconnected", "error");
  ws.onerror = () => setStatus("error", "error");

  ws.onmessage = (e) => {
    let evt;
    try { evt = JSON.parse(e.data); } catch { return; }

    switch (evt.type) {
      case "ready":
        setStatus("ready", "connected");
        if (evt.kb_entries != null) kbBadge.textContent = `${evt.kb_entries} KB entries`;
        break;
      case "token":
        if (currentAssistantMsg === null) setStatus("thinking…", "thinking");
        appendToAssistant(evt.token);
        break;
      case "tool_call":
        toolEntry(evt);
        break;
      case "session":
        updateSession(evt.state);
        break;
      case "assistant_end":
        finishAssistant(evt.text, { ttft_ms: evt.ttft_ms, decode_tps: evt.decode_tps });
        break;
      case "error":
        addMessage("system-note", `[${evt.message}]`);
        setStatus("ready", "connected");
        micBtn.classList.remove("listening");
        currentAssistantMsg = null;
        break;
      case "pong":
        break;
    }
  };
}

function sendText(content) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  addMessage("user", content);
  setStatus("thinking…", "thinking");
  ws.send(JSON.stringify({ type: "text", content }));
  currentAssistantMsg = null;
}

function sendAudioPcm(pcmBase64) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  setStatus("thinking…", "thinking");
  // If the camera is enabled and we have a recent keyframe, ship both in one
  // Gemma 4 multimodal forward pass. Otherwise fall back to audio-only.
  if (videoStream && pendingFrameB64) {
    ws.send(JSON.stringify({
      type: "multimodal",
      pcm_b64: pcmBase64,
      jpeg_b64: pendingFrameB64,
    }));
  } else {
    ws.send(JSON.stringify({ type: "audio", pcm_b64: pcmBase64 }));
  }
  currentAssistantMsg = null;
}

// ── composer ────────────────────────────────────────────────
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = textInput.value.trim();
  if (!v) return;
  sendText(v);
  textInput.value = "";
});

resetBtn.addEventListener("click", () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "reset" }));
  transcriptEl.innerHTML = "";
  toolLog.innerHTML = "";
  safetyBanner.classList.add("hidden");
  addMessage("system-note", "Session reset.");
});

// ── Camera ──────────────────────────────────────────────────
camBtn.addEventListener("click", async () => {
  if (videoStream) {
    videoStream.getTracks().forEach(t => t.stop());
    videoStream = null;
    camEl.srcObject = null;
    if (frameInterval) { clearInterval(frameInterval); frameInterval = null; }
    pendingFrameB64 = null;
    camBtn.textContent = "Enable camera";
    return;
  }
  try {
    videoStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    camEl.srcObject = videoStream;
    camBtn.textContent = "Disable camera";
    frameInterval = setInterval(captureKeyframe, 1000);
  } catch (err) {
    addMessage("system-note", `Camera blocked: ${err.message}`);
  }
});

function captureKeyframe() {
  if (!videoStream || camEl.videoWidth === 0) return;
  camCanvas.width = 320;
  camCanvas.height = Math.round(camCanvas.width * (camEl.videoHeight / camEl.videoWidth));
  const ctx = camCanvas.getContext("2d");
  ctx.drawImage(camEl, 0, 0, camCanvas.width, camCanvas.height);
  pendingFrameB64 = camCanvas.toDataURL("image/jpeg", 0.7);
  // Server doesn't consume frames yet — captured for future multimodal wiring.
}

// ── Mic (push-to-talk) ──────────────────────────────────────
async function ensureAudioStream() {
  if (audioStream) return audioStream;
  audioStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, sampleRate: 16000, echoCancellation: true, noiseSuppression: true },
  });
  return audioStream;
}

async function startRecording() {
  try {
    const stream = await ensureAudioStream();
    const ctx = new AudioContext({ sampleRate: 16000 });
    const src = ctx.createMediaStreamSource(stream);
    const processor = ctx.createScriptProcessor(4096, 1, 1);
    const chunks = [];
    processor.onaudioprocess = (e) => {
      chunks.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    src.connect(processor);
    processor.connect(ctx.destination);

    mediaRecorder = { stop: async () => {
      src.disconnect();
      processor.disconnect();
      await ctx.close();
      // Concatenate to one float32 buffer
      const total = chunks.reduce((n, c) => n + c.length, 0);
      const merged = new Float32Array(total);
      let offset = 0;
      for (const c of chunks) { merged.set(c, offset); offset += c.length; }
      // Convert to PCM16 LE bytes
      const pcm16 = new Int16Array(merged.length);
      for (let i = 0; i < merged.length; i++) {
        const s = Math.max(-1, Math.min(1, merged[i]));
        pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      const bytes = new Uint8Array(pcm16.buffer);
      let bin = "";
      const CHUNK = 0x8000;
      for (let i = 0; i < bytes.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
      }
      const b64 = btoa(bin);
      addMessage("user", "🎙️ (voice)");
      sendAudioPcm(b64);
    }};
    micBtn.classList.add("listening");
    setStatus("listening…", "thinking");
  } catch (err) {
    addMessage("system-note", `Mic blocked: ${err.message}`);
  }
}

async function stopRecording() {
  if (!mediaRecorder) return;
  await mediaRecorder.stop();
  mediaRecorder = null;
  micBtn.classList.remove("listening");
}

micBtn.addEventListener("mousedown", startRecording);
micBtn.addEventListener("touchstart", (e) => { e.preventDefault(); startRecording(); });
micBtn.addEventListener("mouseup", stopRecording);
micBtn.addEventListener("mouseleave", () => { if (mediaRecorder) stopRecording(); });
micBtn.addEventListener("touchend", (e) => { e.preventDefault(); stopRecording(); });

// ── boot ────────────────────────────────────────────────────
connect();
