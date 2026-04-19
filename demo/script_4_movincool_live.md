# Demo Script 4 — MovinCool Climate Pro X14 (live, in-room unit)

**Target runtime:** 2m on stage, 3m with buffer.
**Setup:** There's a real MovinCool Climate Pro X14 portable spot cooler in the demo room. Laptop with camera facing the unit at ~1 ft from the front badge. Display is OFF, exhaust duct lies on the floor.
**Mood:** on-site junior tech calling in the model on a field call — confident but thinks they need help.

---

## Why this demo matters more than the others

- **Real hardware in the room**, not a photo. Judges can SEE the unit.
- **Exact model is in our KB** (`kb/movincool_climate_pro_x14.json`). `query_kb` on "MovinCool Climate Pro X14" returns the top match with score ≥ 15.
- Proves the native-multimodal pitch: the model literally reads the badge off the live camera, routes to the KB entry, summarizes the diagnosis.
- Only works with the 448-px camera capture (landed this session). At 224 px the badge is unreadable.

---

## Beat 1 — Setup (0:00 → 0:15)

**Demoer (to audience):**
> "Portable AC down in our server room. I don't know the model, I don't know the history, I'm a new hire."

*[Click 🎙 to turn hands-free on. OR type the first message if SR struggles with "MovinCool".]*

---

## Beat 2 — Point and talk (0:15 → 0:45)

*[Position laptop camera ~1 ft from the MovinCool front badge, label visible.]*

**Demoer (to model, casual):**
> "Hey, what am I looking at? Display is dead, and it's not cooling."

**Expected model reply (streaming, TTFT ~5 s on first multimodal turn):**
> *"I can see the badge — this is a MovinCool Climate Pro X14, a portable spot cooler. Display being off usually means a power or control-board issue. Let me pull the service notes."*

*[`query_kb` fires with equipment_model "MovinCool Climate Pro X14". Top hit appears in the Tool Activity panel: `movincool_climate_pro_x14` · score 15.]*

**Model continues (pass 2):**
> *"Three things to check first, in order: confirm power supply matches the nameplate; inspect the condensate pump and drain line; clean the condenser coil — that grille looks dusty in the frame. Start with power."*

---

## Beat 3 — Pan to the duct (0:45 → 1:15)

*[Demoer tilts the camera down toward the exhaust duct on the floor.]*

**Demoer:**
> "Exhaust duct is just lying on the ground, not connected to anything."

**Expected model reply:**
> *"That's a problem on its own — dual-hose portable like this one needs both hoses routed outside. Restricted exhaust traps heat inside the unit, compressor can't reject it, and modern boards will latch off. Hook it up before you power-cycle."*

*[If the model calls `log_finding` automatically: appears in the side panel as "Exhaust duct disconnected · major". If not, demoer says the next line.]*

**Demoer (nudging):**
> "Log that as a finding."

**Expected:** `log_finding({location: "exhaust duct", issue: "disconnected from window kit", severity: "major"})` fires. Session findings counter ticks to 1.

---

## Beat 4 — Pretend fix + close (1:15 → 1:50)

**Demoer (miming reconnection):**
> "Okay, duct's reconnected to the window kit. Powered it up — display's live, compressor's running, cold air at the outlet."

**Expected model reply (calls `close_job`):**
> *"Good. Logging it as a ducting reconnect on the Climate Pro X14. No parts replaced. Follow-up is customer training: show them how the window kit latches so this doesn't happen again."*

*[`close_job` fires with structured JSON. Session "Findings: 1" visible. Full session JSON expandable.]*

---

## Beat 5 — The punchline (1:50 → 2:00)

**Demoer (to audience):**
> "From 'what the hell is this thing' to a logged resolution record in under two minutes. One Mac, no cloud, and the model just read the badge off that unit over there."

*[Point at the real MovinCool unit.]*

---

## What must be pre-baked vs live

- **Pre-baked**: our KB entry for MovinCool Climate Pro X14 is already loaded and scores highly on search. Camera at 448 px can resolve the badge text. Server has been warm-started with `cactus_prefill()` of system prompt.
- **Live**: camera reading the badge (Gemma 4 E4B vision), `query_kb` firing on the right model, streaming tokens, `log_finding`, `close_job`, UI updates, browser TTS speaking the replies.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| Chrome SR hears "movie in the pool" instead of "MovinCool" | Type the first prompt. The CAMERA reads the badge — SR doesn't have to. |
| Camera doesn't read the badge | Move closer (6 inches). Or say the model name aloud: *"This is a MovinCool Climate Pro X14."* |
| `query_kb` returns the wrong entry | Our score-15 match is dominant; unlikely. If it happens, say the model name again — second turn usually fixes it. |
| Model hallucinates specs | Remind it: *"Pull the notes from the KB, don't guess."* Often enough to re-trigger `query_kb`. |
| TTFT > 10 s (tool result bloating prefill across turns) | Click **Reset session** between beats to clear context. Demoer can say *"new job, fresh slate"* as natural cover. |
| Nothing works | Fall back to Demo A (Carrier capacitor) on text — pre-recorded backup video at `demo/backups/demo_a.mov`. |

## Why the KB entry makes this demo powerful

From [kb/movincool_climate_pro_x14.json](../kb/movincool_climate_pro_x14.json):
- `common_applications`: server room emergency cooling, event + tent cooling, warehouse spot cooling, temporary cooling during HVAC outage
- `common_faults`: condensate pump failure / clogged drain, dirty condenser coil, low refrigerant, thermistor failure, control board fault, compressor capacitor
- `diagnosis_steps`: error code → power supply → condensate → clean coil → measure capacitor → check thermistor
- `references`: links to the real MovinCool service manual PDFs

The model doesn't have to guess — the KB gives it the exact diagnostic tree for this unit. That's the moat: one curated entry turns a 4B-param model into a senior tech for this specific piece of equipment.
