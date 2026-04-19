# Demo Script 1 — Carrier 58STA capacitor (happy path)

**Target runtime:** 2m 30s on stage, 3m with buffer.
**Setup:** Demoer holding phone. Backdrop image: Carrier 58STA outdoor unit, pre-loaded.
**Mood:** senior tech on an after-hours call, confident and fast.

---

## Beat 1 — Setup (0:00 → 0:20)

**Demoer (to audience):**
> "Senior HVAC tech, 9pm call, 102 degrees outside, customer's AC is cycling on and off. I'm not walking in with a laptop. I put an earbud in, open the app, point my phone at the unit."

*[Demoer taps mic button. Red ring activates.]*

---

## Beat 2 — First exchange (0:20 → 0:50)

**Demoer (to phone, casual):**
> "Carrier 58STA, ninety series. Unit's short cycling and I'm hearing clicks."

**Expected model reply (streaming, ~1-2s TTFT):**
> "Classic run capacitor failure on that series. Point the camera at the outdoor access panel — four screws, right side. I'll check the cap."

*[Hypothesis card appears: "Failed run capacitor — 60% confidence"]*

---

## Beat 3 — Camera attach (0:50 → 1:20)

*[Demoer points phone at the Carrier 58STA image on the backdrop. Frame captured.]*

**Demoer:**
> "Cover's off."

**Expected model reply:**
> "I see the dual-run capacitor top-left of the compartment. Top looks bulged — that's your failure. Measure it: forty-five and five microfarads, plus or minus six percent. If it's off, swap in a P291-4554RS."

*[Hypothesis confidence jumps to 87%. Finding appears in the log: "run capacitor bulging at the top / major / P291-4554RS"]*

---

## Beat 4 — The fix (1:20 → 1:50)

**Demoer:**
> "Discharged. Measuring — thirty-eight on the compressor side."

**Expected model reply:**
> "Confirmed failure. Replacing. Discharge first — twenty-k ohm resistor across HERM and C. Yellow goes to HERM, brown to FAN, black to common. I'll hold while you swap."

*[Optional: demoer mimes the swap, or jumps forward: "…capacitor replaced, power restored."]*

---

## Beat 5 — Close (1:50 → 2:20)

**Demoer:**
> "Unit's running clean. Three full cycles, no clicking."

**Expected model reply (calls `close_job`):**
> "Job closed. Summary: replaced 45/5 uF run capacitor on Carrier 58STA090. Parts used: P291-4554RS. No follow-up needed. Sending to the work order."

*[CloseJobView appears with summary + parts pre-filled. Demoer taps "Finalize & send."]*

---

## Beat 6 — The punchline (2:20 → 2:30)

**Demoer (to audience):**
> "Offline. On device. No cloud. No five-minute ticket scroll. From truck to done in two and a half minutes."

---

## What must be pre-baked vs live

- **Pre-baked:** KB entry for 58STA loaded. Backdrop image of the unit visible. WiFi **off** on phone to prove offline.
- **Live:** voice in, streaming tokens, tool call → `log_finding`, tool call → `close_job`, UI updates.
- **If multimodal misses the T+6h gate:** fall back to text-only, demoer narrates "I can see the capacitor is bulged" as their own observation rather than the model detecting it. Still works.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| Model doesn't load | Backup video plays. Demoer narrates over it. |
| Slow first token (>3s) | Demoer adds filler: "Model's thinking — on device this is all running on the A18 chip." |
| Tool call doesn't fire | Demoer taps the button manually. Nobody notices. |
| Unexpected reply | Demoer pivots: "That's an interesting take, but let me steer it back…" and asks the expected question again. |

## Script variants (create next)

- `script_2_safety.md` — gas smell → `flag_safety` → STOP banner → evacuate
- `script_3_scope_change.md` — contactor pitted AND capacitor weak → `flag_scope_change` → customer callback
