# Demo Script 2 — Gas smell safety interrupt

**Target runtime:** 30 seconds on stage, 45 with buffer.
**Setup:** Demoer already holding phone, "On-Site mode" already active from Script 1 flow OR freshly opened.
**Mood:** calm, fast, deadly serious — the pitch is that AI *prevents* the wrong next action.

---

## Beat 1 — The trigger (0:00 → 0:08)

**Demoer (to audience, one sentence of framing):**
> "Different call. Furnace service. Tech walks in."

*[Demoer taps mic. Red ring on.]*

**Demoer (to phone, offhanded — this is the key pedagogical moment: techs in the field report things *while working*, not as emergencies):**
> "I'm in the basement at the furnace, smelling gas near the inducer."

---

## Beat 2 — The interrupt (0:08 → 0:18)

**Expected model behavior (instant, no back-and-forth):**

1. Stop the normal conversation flow.
2. Call `flag_safety` with `hazard="suspected natural gas leak"`, `level="stop"`, `immediate_action="Leave the building. Call the gas utility from outside. Do not operate any switches."`
3. Render the STOP banner — red full-width, single headline, three-line action list.

*[UI: red banner slides down from the top, covering the transcript. Phone vibrates once (short haptic). Audio: spoken TTS of the immediate action at 1.25× rate.]*

**Expected model voice output (streaming):**
> "Stop. Leave the building now. Do not touch switches, do not plug or unplug anything. From outside, call your gas utility's emergency line."

---

## Beat 3 — The explanation to the audience (0:18 → 0:30)

**Demoer (to audience, taking the phone off-mode — this is the punchline):**
> "Notice what just happened. The tech said 'I'm smelling gas' as one of five things they were about to say. The model didn't wait, didn't summarize, didn't ask a follow-up. Safety classifier runs inside the same Gemma 4 forward pass — same model, same weights, zero extra latency. And because it's on-device, this still works if the basement has no signal."

*[Optional: demoer taps the banner, shows the `flag_safety` tool-call JSON that fired.]*

---

## What must be pre-baked vs live

- **Pre-baked:** generic_gas_furnace_gas_smell KB entry loaded. System prompt is the real one (not tuned for this demo).
- **Live:** voice in, tool call fires, banner renders, TTS reads out, haptic fires.
- **If TTS fails:** the on-screen banner is sufficient — demoer reads the text aloud while pointing to it.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| Model doesn't flag_safety, treats it as a normal finding | Demoer pauses the mic, says "and just in case the model didn't catch it live — here's what the tool call looks like when it does fire" and shows the pre-recorded banner screenshot. |
| Banner renders but TTS doesn't read aloud | Demoer reads the banner aloud — that's literally what a tech would do on the phone anyway. |
| Tool call fires twice (duplicate) | Nobody will notice. Move on. |

## Judge Q&A cheat sheet

- **"How do you know it's not just keyword matching on 'gas'?"** — Gemma 4 does full language understanding. It would not flag "I turned the gas valve off before starting the repair" as an emergency. We can demo that edge case if they ask.
- **"What stops the model from flagging everything?"** — The `flag_safety` tool schema requires a specific hazard type and an immediate action. The model has to *commit* to an action, which acts as a natural filter. Also — we'd rather over-trigger than miss a real leak.
- **"Why not a separate safety model?"** — Past hackathon projects ran a safety classifier *after* the primary model. That adds latency, more memory, more failure modes. Gemma 4 is good enough that one forward pass does both.

## Pointer to the actual KB entry

[kb/generic_gas_furnace_gas_smell.json](../kb/generic_gas_furnace_gas_smell.json)
