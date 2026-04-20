"""
HVAC Copilot — FastAPI server running Gemma 4 via Cactus.

Serves:
  GET  /                    → static web UI
  GET  /healthz             → liveness + model / Rokid state
  WS   /ws/session          → shared assistant event stream for browser clients
  POST /session             → Rokid WebRTC SDP offer endpoint
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.assistant_runtime import SharedAssistantRuntime
from src.cactus import cactus_complete, cactus_destroy, cactus_init, cactus_prefill, cactus_reset, cactus_stop
from src.config import cfg
from src.kb_store import get_kb_store
from src.rokid_bridge import RokidBridgeManager
from src.session_log import log_event, log_file_name, log_file_path, recent_events, summary as log_summary
from src.tools import get_tools_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hvac.main")

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"
WEIGHTS_DIR = REPO_ROOT / "cactus" / "weights" / "gemma-4-e4b-it"

SYSTEM_PROMPT = (
    "You are HVACCopilot — an on-device coach for HVAC field technicians running on Gemma 4. "
    "You see what the tech sees and hear what they describe. Be concise — they are working with their hands.\n\n"
    "Tool-use rules (follow strictly):\n"
    "1. The MOMENT a tech describes ANY symptom with a brand/model, CALL query_kb FIRST. "
    "Do NOT ask clarifying questions first. Do NOT guess. Call query_kb, then summarize the top match.\n"
    "2. If the tech mentions gas smell, sulfur, rotten-egg smell, arcing, electrical burning, smoke, or CO symptoms "
    "(headache, dizziness, nausea near the unit), CALL flag_safety with level='stop' IMMEDIATELY — even before query_kb.\n"
    "3. When the tech confirms a diagnosis (e.g. 'capacitor is bulged', 'contactor is pitted'), "
    "CALL log_finding to record it.\n"
    "4. When the tech spots additional work beyond the ticket (e.g. 'contactor also needs replacing'), "
    "CALL flag_scope_change.\n"
    "5. When the tech says they're done ('job's finished', 'cooling is normal', 'unit's running'), CALL close_job.\n"
    "6. ANY time the tech says 'look online', 'check Reddit', 'look it up', 'any field reports', "
    "'search the forums', or similar phrasing — CALL search_online_hvac with a tight 5-10 word query. "
    "Do NOT ask clarifying questions first. Do NOT say you cannot browse — you can, via this tool.\n\n"
    "Tools available:\n"
    "  • query_kb(query, equipment_model?) — curated HVAC KB.\n"
    "  • log_finding(location, issue, severity, part_number?, notes?)\n"
    "  • flag_safety(hazard, immediate_action, level)\n"
    "  • flag_scope_change(original_scope, new_scope, reason, estimated_extra_time_minutes?)\n"
    "  • close_job(summary, parts_used, follow_up_required, follow_up_notes?)\n"
    "  • search_online_hvac(query) — online HVAC technician forums (Reddit).\n\n"
    "After any tool call returns, summarize the result for the tech in 1-2 sentences. "
    "Name the part, the confirming test, and the first safety step. Do not dump the raw JSON. "
    "Never fabricate tool results — if you did not call a tool, do not invent its output."
)

GEN_OPTIONS = {
    "max_tokens": min(cfg.MAX_TOKENS, 220),
    "temperature": cfg.TEMPERATURE,
}


class EngineHandle:
    def __init__(self) -> None:
        self._handle: int | None = None
        self._lock = asyncio.Lock()

    def load(self, model_path: Path) -> None:
        logger.info("Loading Gemma 4 E4B from %s…", model_path)
        self._handle = cactus_init(str(model_path), None, False)
        if self._handle is None:
            raise RuntimeError("cactus_init returned None")
        logger.info("Loaded model successfully")

    def prefill_system(self) -> None:
        if self._handle is None:
            raise RuntimeError("Cactus handle not initialized")
        cactus_prefill(
            self._handle,
            json.dumps([{"role": "system", "content": SYSTEM_PROMPT}]),
            json.dumps(GEN_OPTIONS),
            get_tools_json(),
            None,
        )

    def unload(self) -> None:
        if self._handle is not None:
            cactus_destroy(self._handle)
            self._handle = None

    def reset_and_rewarm(self) -> None:
        if self._handle is None:
            return
        try:
            cactus_reset(self._handle)
        except Exception as exc:
            logger.warning("cactus_reset failed: %s", exc)
        try:
            self.prefill_system()
        except Exception as exc:
            logger.warning("prefill after reset failed: %s", exc)

    @property
    def handle(self) -> int:
        if self._handle is None:
            raise RuntimeError("Cactus handle not initialized")
        return self._handle

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock


engine = EngineHandle()
assistant_runtime = SharedAssistantRuntime(
    engine=engine,
    system_prompt=SYSTEM_PROMPT,
    gen_options=GEN_OPTIONS,
    cactus_complete=cactus_complete,
    cactus_stop=cactus_stop,
)
rokid_bridge = RokidBridgeManager(assistant_runtime)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_kb_store()
    engine.load(WEIGHTS_DIR)
    engine.prefill_system()
    speech_prewarm = asyncio.create_task(rokid_bridge.prewarm())
    try:
        yield
    finally:
        speech_prewarm.cancel()
        with contextlib.suppress(Exception):
            await speech_prewarm
        await rokid_bridge.disconnect()
        engine.unload()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return JSONResponse({
        "ok": True,
        "kb_entries": get_kb_store().entry_count,
        "model_loaded": engine._handle is not None,
        "model": "gemma-4-E4B-it",
        "rokid": rokid_bridge.snapshot(),
    })


@app.get("/logs/summary")
async def logs_summary():
    return JSONResponse(log_summary())


@app.get("/logs/recent")
async def logs_recent(n: int = 100):
    return JSONResponse({"file": log_file_name(), "events": recent_events(n)})


@app.get("/logs/download")
async def logs_download():
    return FileResponse(
        path=str(log_file_path()),
        media_type="application/x-ndjson",
        filename=log_file_name(),
    )


@app.get("/api/rokid/state")
async def rokid_state():
    return JSONResponse(rokid_bridge.snapshot())


@app.get("/api/rokid/preview/latest.jpg")
async def rokid_latest_preview():
    jpeg_bytes = await rokid_bridge.latest_preview()
    if jpeg_bytes is None:
        return Response(status_code=404)
    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/rokid/preview/stream.mjpg")
async def rokid_preview_stream():
    return StreamingResponse(
        rokid_bridge.iter_mjpeg_preview(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.post("/api/rokid/control")
async def rokid_control(request: Request):
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON object body required")
    command_type = str(payload.get("type", "")).strip()
    if command_type not in {"display_text", "status", "clear_display", "ping"}:
        raise HTTPException(status_code=400, detail="Unsupported control type")
    try:
        await rokid_bridge.send_control(payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("rokid control failed")
        raise HTTPException(status_code=500, detail="Failed to send control") from exc
    return JSONResponse({"ok": True})


@app.post("/api/rokid/session/disconnect")
async def rokid_disconnect():
    await rokid_bridge.disconnect()
    return JSONResponse({"ok": True})


@app.post("/session")
async def rokid_session(request: Request):
    raw_body = (await request.body()).decode()
    try:
        answer_sdp = await rokid_bridge.handle_offer(raw_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PlainTextResponse(answer_sdp, media_type="application/sdp")


@app.websocket("/ws/session")
async def ws_session(ws: WebSocket) -> None:
    sid = hex(id(ws))[-8:]
    log_event("ws_connect", sid=sid)
    try:
        await assistant_runtime.connect_websocket(ws)
        await ws.send_text(json.dumps({"type": "rokid_state", "state": rokid_bridge.snapshot()}))
        while True:
            msg_raw = await ws.receive_text()
            try:
                msg = json.loads(msg_raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "Bad JSON"}))
                continue
            await assistant_runtime.handle_browser_message(msg)
    except WebSocketDisconnect:
        log_event("ws_disconnect", sid=sid)
    except Exception as exc:
        logger.exception("WS error: %s", exc)
        log_event("ws_error", sid=sid, error=str(exc))
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps({"type": "error", "message": str(exc)}))
    finally:
        await assistant_runtime.disconnect_websocket(ws)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
