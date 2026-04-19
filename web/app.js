// HVAC Copilot — browser client.
//
// Voice strategy: Web Speech API for STT (same pattern as Wine_Voice_AI).
// Continuous listening with VAD-style silence detection. Transcribed text
// goes to the server as `multimodal` (with the latest camera keyframe) or
// plain `text`. Gemma 4 sees text + image in one forward pass; audio bytes
// never leave the browser.
//
// Output: progressive TTS — each complete sentence is queued to
// SpeechSynthesisUtterance as it arrives, so the assistant starts speaking
// while the model is still generating.

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
const stopBtn = $("stop-btn");
const rokidPreview = $("rokid-preview");
const rokidEmpty = $("rokid-empty");
const rokidUrl = $("rokid-url");
const rokidConnection = $("rokid-connection");
const rokidIce = $("rokid-ice");
const rokidControl = $("rokid-control");
const rokidSpeech = $("rokid-speech");
const rokidLastUser = $("rokid-last-user");
const rokidLastAssistant = $("rokid-last-assistant");
const rokidDisconnectBtn = $("rokid-disconnect");

let ws;
let currentAssistantMsg = null;
let videoStream = null;
let pendingFrameB64 = null;
let frameInterval = null;
let isGenerating = false;   // true from send → assistant_end
let rokidPreviewKey = "";

// ── Web Speech API (STT) ────────────────────────────────────
// Wine_Voice_AI pattern: Chrome does transcription in-browser. No PCM goes
// over the wire.
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let recognition = null;
let handsFree = false;           // user toggled hands-free mode on
let micListening = false;        // recognition actively listening right now
let suppressOnResult = false;    // true while TTS is speaking, to avoid self-hearing
let silenceTimer = null;
let interimTranscript = "";
let finalTranscript = "";
const SILENCE_MS = 1200;         // submit after 1.2s of silence (Wine_Voice_AI uses 1.6s)
const TTS_COOLDOWN_MS = 500;     // wait this long after TTS before re-enabling mic
const MIN_UTTERANCE_CHARS = 4;   // reject transcripts shorter than this (background noise)

// ── Progressive TTS ─────────────────────────────────────────
const speechQueue = [];
let isSpeaking = false;
let sentenceBuffer = "";
let selectedVoice = null;   // chosen SpeechSynthesisVoice (or null = browser default)
let allVoices = [];

// Ordered preference for voice names. First name in the list that's actually
// installed wins. Premium/Enhanced Apple voices top the list because they
// sound the most natural; the generic Samantha/Alex are solid fallbacks.
const VOICE_PRIORITY = [
  "Ava (Premium)",
  "Ava (Enhanced)",
  "Evan (Premium)",
  "Evan (Enhanced)",
  "Samantha (Enhanced)",
  "Serena (Premium)",
  "Serena (Enhanced)",
  "Allison (Premium)",
  "Allison (Enhanced)",
  "Google UK English Female",
  "Google UK English Male",
  "Samantha",
  "Karen",
  "Allison",
  "Ava",
  "Alex",
];

function pickBestVoice(voices) {
  if (!voices || voices.length === 0) return null;
  // Exact-name match on our priority list first.
  for (const pref of VOICE_PRIORITY) {
    const hit = voices.find(v => v.name === pref);
    if (hit) return hit;
  }
  // Loose: any English voice whose name mentions Premium/Enhanced.
  const enhanced = voices.find(v => /en[-_]/i.test(v.lang) && /(Premium|Enhanced)/i.test(v.name));
  if (enhanced) return enhanced;
  // Any en-US voice.
  const enUS = voices.find(v => /en[-_]US/i.test(v.lang));
  if (enUS) return enUS;
  return voices[0];
}

function loadVoicesAndPick() {
  allVoices = window.speechSynthesis.getVoices() || [];
  selectedVoice = pickBestVoice(allVoices);
  if (selectedVoice) {
    console.log(`[tts] selected voice: ${selectedVoice.name} (${selectedVoice.lang})`);
  }
  // Populate the dropdown if it's there.
  const sel = document.getElementById("voice-select");
  if (sel && allVoices.length) {
    sel.innerHTML = "";
    allVoices
      .filter(v => /^en/i.test(v.lang))
      .forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.name;
        opt.textContent = `${v.name} · ${v.lang}${v.default ? " (default)" : ""}`;
        if (selectedVoice && v.name === selectedVoice.name) opt.selected = true;
        sel.appendChild(opt);
      });
  }
}

// Chrome loads voices asynchronously — the onvoiceschanged event fires once
// they're ready. Load them again if the user returns to the tab.
if ("speechSynthesis" in window) {
  window.speechSynthesis.onvoiceschanged = loadVoicesAndPick;
  loadVoicesAndPick();  // in case they're already cached
}

function splitBySentence(text) {
  if (window.Intl && Intl.Segmenter) {
    try {
      const seg = new Intl.Segmenter("en", { granularity: "sentence" });
      return [...seg.segment(text)].map(s => s.segment).filter(s => s.trim());
    } catch {}
  }
  return text.split(/(?<=[.!?])\s+(?=[A-Z])/).filter(s => s.trim());
}

function queueSpeech(text) {
  const t = text.trim();
  if (!t) return;
  speechQueue.push(t);
  playNext();
}

function playNext() {
  if (isSpeaking) return;
  if (speechQueue.length === 0) {
    // Done speaking; re-enable mic after a short cooldown to avoid echo pickup.
    if (handsFree) {
      setTimeout(() => {
        suppressOnResult = false;
        startRecognition();
      }, TTS_COOLDOWN_MS);
    }
    return;
  }
  const sentence = speechQueue.shift();
  const u = new SpeechSynthesisUtterance(sentence);
  if (selectedVoice) u.voice = selectedVoice;
  u.rate = 1.0;
  u.pitch = 1.0;
  u.onstart = () => {
    isSpeaking = true;
    // Barge-in enabled: re-enable the mic the moment TTS starts so the user
    // can cut in. The onresult handler watches `isSpeaking` and, when it
    // catches a meaningful transcript, cancels TTS and treats it as the
    // next turn. Chrome's echoCancellation filters most TTS echo; the
    // MIN_UTTERANCE_CHARS gate filters the rest.
    setStatus("speaking…", "thinking");
    if (handsFree) {
      suppressOnResult = false;
      startRecognition();
    }
  };
  u.onend = () => {
    isSpeaking = false;
    playNext();
  };
  u.onerror = () => {
    isSpeaking = false;
    playNext();
  };
  window.speechSynthesis.speak(u);
}

function flushSentenceBuffer(force = false) {
  if (!sentenceBuffer) return;
  const pieces = splitBySentence(sentenceBuffer);
  if (force) {
    for (const p of pieces) queueSpeech(p);
    sentenceBuffer = "";
    return;
  }
  if (pieces.length > 1) {
    // All but the last are complete sentences; the last may still be mid-sentence.
    for (let i = 0; i < pieces.length - 1; i++) queueSpeech(pieces[i]);
    sentenceBuffer = pieces[pieces.length - 1];
  }
}

// ── Display helpers ─────────────────────────────────────────
function setStatus(text, cls = "") {
  statusEl.textContent = text;
  statusEl.className = "status " + cls;
}

function setGenerating(on) {
  isGenerating = on;
  if (stopBtn) stopBtn.classList.toggle("hidden", !on);
}

function sendCancel() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  // Cut TTS, clear any queued sentences, tell the server to cactus_stop.
  window.speechSynthesis.cancel();
  speechQueue.length = 0;
  isSpeaking = false;
  sentenceBuffer = "";
  ws.send(JSON.stringify({ type: "cancel" }));
  addMessage("system-note", "[stopped]");
  setGenerating(false);
  setStatus(handsFree ? "hands-free · listening" : "ready", "connected");
  currentAssistantMsg = null;
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
  sentenceBuffer += token;
  flushSentenceBuffer(false);
}

function finishAssistant(finalText, stats) {
  // If tokens already streamed into a bubble, KEEP the streamed text —
  // do NOT overwrite with server's final_text. The server sometimes
  // concatenates multiple passes (tool-call follow-ups) into final_text
  // and that'd visually replace what the user has already read.
  if (currentAssistantMsg) {
    currentAssistantMsg = null;
  } else if (finalText) {
    addMessage("assistant", finalText);
  }
  if (stats && stats.ttft_ms) {
    ttftBadge.textContent = `TTFT ${Math.round(stats.ttft_ms)}ms · ${stats.decode_tps ? Math.round(stats.decode_tps) : "-"} tok/s`;
  }
  // Flush any remaining partial sentence to speech.
  flushSentenceBuffer(true);
  if (!isSpeaking && speechQueue.length === 0) {
    setStatus(handsFree ? "hands-free · listening" : "ready", "connected");
    if (handsFree) {
      setTimeout(() => {
        suppressOnResult = false;
        startRecognition();
      }, TTS_COOLDOWN_MS);
    }
  }
}

// ── Tool activity log ───────────────────────────────────────
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

function updateRokidState(state) {
  if (!state) return;
  rokidConnection.textContent = state.connection_state || "idle";
  rokidIce.textContent = state.ice_connection_state || "new";
  rokidControl.textContent = state.control_channel_state || "closed";
  rokidSpeech.textContent = state.speech_state || "idle";
  rokidLastUser.textContent = state.last_user_text || "—";
  rokidLastAssistant.textContent = state.last_assistant_text || "—";

  const examples = Array.isArray(state.session_url_examples) ? state.session_url_examples : [];
  rokidUrl.textContent = examples.length
    ? `Wearable URL: ${examples[0]}`
    : (state.dependency_error ? `Rokid unavailable: ${state.dependency_error}` : "Wearable URL unavailable");

  const streamUrl = state.preview_stream_url;
  const nextKey = `${streamUrl || ""}|${state.session_started_at || ""}|${state.preview_sequence || 0}`;
  if (streamUrl && state.session_active && state.preview_sequence > 0) {
    if (rokidPreviewKey !== nextKey) {
      rokidPreview.src = `${streamUrl}?session=${encodeURIComponent(state.session_started_at || "idle")}`;
      rokidPreviewKey = nextKey;
    }
    rokidPreview.classList.remove("hidden");
    rokidEmpty.classList.add("hidden");
  } else {
    rokidPreview.classList.add("hidden");
    rokidEmpty.classList.remove("hidden");
    rokidEmpty.textContent = state.session_active ? "Waiting for first camera frame…" : "Waiting for Rokid glasses…";
  }
}

// ── WS client ───────────────────────────────────────────────
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
        setStatus(handsFree ? "hands-free · listening" : "ready", "connected");
        if (evt.kb_entries != null) kbBadge.textContent = `${evt.kb_entries} KB entries`;
        break;
      case "rokid_state":
        updateRokidState(evt.state);
        break;
      case "user_turn":
        if (evt.source === "rokid" && evt.text) {
          addMessage("user", evt.text);
        }
        break;
      case "token":
        if (currentAssistantMsg === null) {
          setStatus("thinking…", "thinking");
          // As soon as ANY response token arrives, pause listening so the
          // model's reply (streaming + TTS) can't trigger a rogue new turn
          // via ambient audio / echo pickup. Resume after assistant_end.
          suppressOnResult = true;
          stopRecognition();
          if (turnT0 && !turnFirstTokenT) {
            turnFirstTokenT = performance.now();
            console.log(`first token @ ${((turnFirstTokenT - turnT0) / 1000).toFixed(2)}s`);
          }
        }
        appendToAssistant(evt.token);
        break;
      case "tool_call":
        console.log("tool_call:", evt.name, evt.arguments);
        toolEntry(evt);
        break;
      case "session":
        updateSession(evt.state);
        break;
      case "assistant_end":
        if (turnT0) {
          const total = ((performance.now() - turnT0) / 1000).toFixed(2);
          console.log(`assistant_end @ ${total}s  ttft=${evt.ttft_ms}ms  decode=${evt.decode_tps}tok/s`);
          console.groupEnd();
          turnT0 = 0;
        }
        setGenerating(false);
        finishAssistant(evt.text, { ttft_ms: evt.ttft_ms, decode_tps: evt.decode_tps });
        break;
      case "error":
        addMessage("system-note", `[${evt.message}]`);
        setStatus(handsFree ? "hands-free · listening" : "ready", "connected");
        setGenerating(false);
        currentAssistantMsg = null;
        // If we were suppressed from TTS, resume listening.
        if (handsFree) {
          setTimeout(() => {
            suppressOnResult = false;
            startRecognition();
          }, 300);
        }
        break;
      case "pong":
        break;
    }
  };
}

let turnNum = 0;
let turnT0 = 0;
let turnFirstTokenT = 0;

function sendUtterance(text) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  const clean = (text || "").trim();
  if (!clean) return;
  addMessage("user", clean);
  setStatus("thinking…", "thinking");
  currentAssistantMsg = null;
  // Clear any lingering SR state so a delayed partial doesn't queue a
  // duplicate turn, and pause the mic while the model replies.
  finalTranscript = "";
  interimTranscript = "";
  if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
  suppressOnResult = true;
  stopRecognition();

  turnNum += 1;
  turnT0 = performance.now();
  turnFirstTokenT = 0;
  const hasImage = !!(videoStream && pendingFrameB64);
  setGenerating(true);
  console.groupCollapsed(`🌵 turn ${turnNum} — ${hasImage ? "multimodal" : "text"} — "${clean.slice(0, 60)}"`);
  console.log("send @", new Date().toISOString(), "hasImage:", hasImage);

  // If the camera is enabled, bundle the latest keyframe in a multimodal
  // message so Gemma 4 can reason over image + text in one forward pass.
  if (hasImage) {
    ws.send(JSON.stringify({ type: "multimodal", content: clean, jpeg_b64: pendingFrameB64 }));
  } else {
    ws.send(JSON.stringify({ type: "text", content: clean }));
  }
}

// ── Speech recognition lifecycle ────────────────────────────
function initRecognition() {
  if (!SpeechRecognition) return null;
  const r = new SpeechRecognition();
  r.continuous = true;
  r.interimResults = true;
  r.lang = "en-US";
  r.onresult = (e) => {
    if (suppressOnResult) return;
    interimTranscript = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const res = e.results[i];
      if (res.isFinal) finalTranscript += res[0].transcript + " ";
      else interimTranscript += res[0].transcript;
    }
    const merged = (finalTranscript + interimTranscript).trim();

    // Barge-in: if TTS is speaking AND the user has said something
    // substantial enough to be real speech (not a short echo), cut TTS
    // immediately. The silence timer will submit the full transcript a
    // moment later in the normal flow.
    if (isSpeaking && merged.length >= MIN_UTTERANCE_CHARS) {
      console.log("[barge-in] cancelling TTS on mid-speak transcript:", merged.slice(0, 60));
      window.speechSynthesis.cancel();
      speechQueue.length = 0;
      isSpeaking = false;
      sentenceBuffer = "";
    }

    // Any new audio resets the silence timer.
    if (silenceTimer) clearTimeout(silenceTimer);
    silenceTimer = setTimeout(submitIfReady, SILENCE_MS);
    if (merged) {
      setStatus(`listening: "${merged.slice(-60)}"`, "thinking");
    }
  };
  r.onend = () => {
    micListening = false;
    // Chrome's SR stops on its own after ~60s of quiet or each final result;
    // restart on a short delay so the user never has to re-enable hands-free.
    if (handsFree && !isSpeaking && !suppressOnResult) {
      setTimeout(() => {
        if (!handsFree || isSpeaking || suppressOnResult || micListening) return;
        try {
          r.start();
          micListening = true;
        } catch {}
      }, 150);
    }
  };
  r.onerror = (e) => {
    micListening = false;
    if (e.error === "not-allowed" || e.error === "service-not-allowed") {
      addMessage("system-note", `[mic: ${e.error}]`);
      handsFree = false;
      micBtn.classList.remove("listening");
      micBtn.textContent = "🎙️";
      setStatus("ready", "connected");
    }
  };
  return r;
}

function submitIfReady() {
  const text = (finalTranscript + interimTranscript).trim();
  finalTranscript = "";
  interimTranscript = "";
  if (!text) return;
  // Gate: short transcripts are almost always background noise or
  // misfires (SR hearing "testing face" from ambient conversation).
  if (text.length < MIN_UTTERANCE_CHARS) return;
  // Don't submit echoes of our own TTS.
  if (isSpeaking || suppressOnResult) return;
  sendUtterance(text);
}

function startRecognition() {
  if (!recognition) recognition = initRecognition();
  if (!recognition || micListening || isSpeaking || suppressOnResult) return;
  try {
    recognition.start();
    micListening = true;
  } catch {
    // already started
  }
}

function stopRecognition() {
  if (!recognition || !micListening) return;
  try { recognition.stop(); } catch {}
  micListening = false;
  if (silenceTimer) { clearTimeout(silenceTimer); silenceTimer = null; }
}

function toggleHandsFree() {
  handsFree = !handsFree;
  if (handsFree) {
    if (!SpeechRecognition) {
      addMessage("system-note", "[Browser doesn't support SpeechRecognition. Use Chrome.]");
      handsFree = false;
      return;
    }
    micBtn.classList.add("listening");
    micBtn.textContent = "⏹";
    micBtn.title = "Stop hands-free";
    startRecognition();
    setStatus("hands-free · listening", "thinking");
    // Prime SpeechSynthesis with a user gesture so the FIRST reply can speak.
    // (Chrome otherwise sometimes blocks autoplay on the initial utterance.)
    try {
      const prime = new SpeechSynthesisUtterance("");
      window.speechSynthesis.speak(prime);
    } catch {}
  } else {
    micBtn.classList.remove("listening");
    micBtn.textContent = "🎙️";
    micBtn.title = "Hands-free";
    stopRecognition();
    window.speechSynthesis.cancel();
    speechQueue.length = 0;
    isSpeaking = false;
    // If the model was still generating when the user disabled hands-free,
    // treat it as an intent to abort — send cancel so it stops mid-stream.
    if (isGenerating) {
      sendCancel();
    } else {
      setStatus("ready", "connected");
    }
  }
}

// ── composer ────────────────────────────────────────────────
composer.addEventListener("submit", (e) => {
  e.preventDefault();
  const v = textInput.value.trim();
  if (!v) return;
  sendUtterance(v);
  textInput.value = "";
});

resetBtn.addEventListener("click", () => {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  window.speechSynthesis.cancel();
  speechQueue.length = 0;
  isSpeaking = false;
  sentenceBuffer = "";
  ws.send(JSON.stringify({ type: "reset" }));
  transcriptEl.innerHTML = "";
  toolLog.innerHTML = "";
  safetyBanner.classList.add("hidden");
  addMessage("system-note", "Session reset.");
});

if (rokidDisconnectBtn) {
  rokidDisconnectBtn.addEventListener("click", async () => {
    try {
      const res = await fetch("/api/rokid/session/disconnect", { method: "POST" });
      if (!res.ok) throw new Error(`Disconnect failed: ${res.status}`);
    } catch (err) {
      addMessage("system-note", `[rokid disconnect failed: ${err.message}]`);
    }
  });
}

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
  // 224px wide is roughly what Gemma 4's vision encoder is trained on; going
  // larger just spends more vision tokens without extra recognition quality.
  camCanvas.width = 224;
  camCanvas.height = Math.round(camCanvas.width * (camEl.videoHeight / camEl.videoWidth));
  const ctx = camCanvas.getContext("2d");
  ctx.drawImage(camEl, 0, 0, camCanvas.width, camCanvas.height);
  pendingFrameB64 = camCanvas.toDataURL("image/jpeg", 0.6);
}

// ── Mic toggle: click to start/stop hands-free ─────────────
micBtn.addEventListener("click", toggleHandsFree);

// ── Stop button: cancels in-flight generation ───────────────
if (stopBtn) stopBtn.addEventListener("click", sendCancel);

// ── Spacebar kill switch ────────────────────────────────────
// When the model is generating (or TTS is speaking) and the user isn't typing
// in an input, pressing Space cancels everything. Guaranteed cut-off even
// when barge-in doesn't fire (e.g. noisy room, laptop speakers without
// echo cancellation headroom, or hands-free is disabled).
document.addEventListener("keydown", (e) => {
  if (e.key !== " " && e.code !== "Space") return;
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  if (!isGenerating && !isSpeaking) return;
  e.preventDefault();
  sendCancel();
});

// ── Voice dropdown: override which SpeechSynthesis voice is used ────
const voiceSelect = document.getElementById("voice-select");
if (voiceSelect) {
  voiceSelect.addEventListener("change", () => {
    const pick = allVoices.find(v => v.name === voiceSelect.value);
    if (pick) {
      selectedVoice = pick;
      console.log(`[tts] user picked voice: ${pick.name}`);
      // Demo the new voice so the user hears the switch immediately.
      const demo = new SpeechSynthesisUtterance("Voice set.");
      demo.voice = pick;
      demo.rate = 1.0;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(demo);
    }
  });
}

// ── boot ────────────────────────────────────────────────────
connect();
