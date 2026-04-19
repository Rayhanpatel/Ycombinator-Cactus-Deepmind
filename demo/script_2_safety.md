# Demo Script 2 — Gas Leak Safety Stop (flag_safety)

**Target runtime:** 1m 45s on stage, 2m 15s with buffer.
**Setup:** Demoer holding phone. Backdrop image: furnace utility room.
**Mood:** calm but alert — this is a safety-first scenario.

---

## Beat 1 — Setup (0:00 → 0:15)

**Demoer (to audience):**
> "Morning call. Customer says the furnace isn't lighting. I walk into the utility room, and I immediately smell something."

*[Demoer taps mic button. Red ring activates.]*

---

## Beat 2 — The alert (0:15 → 0:40)

**Demoer (to phone, urgent but controlled):**
> "Hey, I'm at a Lennox ML180, customer says no heat. I just walked into the utility room and I'm getting a gas smell. It's faint but it's definitely there."

**Expected model reply (calls `flag_safety`):**
> "🛑 STOP. Do not proceed with any diagnosis. Do not operate switches or create any spark source. Leave the utility room now. Open exterior doors on your way out. Do not use the thermostat. I've flagged this as a gas hazard — stop-level safety alert."

*[UI goes RED. STOP banner fills the screen. Safety alert card appears:]*
```
⚠️ SAFETY STOP
Hazard: Suspected natural gas leak
Action: Evacuate area, do not operate switches
Level: STOP
```

---

## Beat 3 — The follow-up (0:40 → 1:10)

**Demoer (now "outside"):**
> "OK I'm outside. What do I do next?"

**Expected model reply:**
> "Good — you're clear. Next steps: call the gas company emergency line. They'll send a crew with a combustible gas detector to locate and verify the leak. Do not re-enter until they clear the space. I've logged this to the job as a critical safety finding. If the customer asks, tell them the gas company visit is free and mandatory."

*[Finding logged: `[critical] Suspected natural gas leak at furnace utility room`]*

---

## Beat 4 — Close with safety context (1:10 → 1:35)

**Demoer:**
> "Gas company's been called. Close this one out."

**Expected model reply (calls `close_job`):**
> "Job closed. Summary: responded to no-heat call on Lennox ML180. Detected gas odor in utility room — issued safety stop. Gas company notified. No repair performed. Follow-up required after gas company clears the space."

*[CloseJobView appears. Follow-up: YES. Notes pre-filled. Export to Downloads.]*

---

## Beat 5 — The punchline (1:35 → 1:45)

**Demoer (to audience):**
> "That's the scenario nobody practices for. The AI didn't try to be helpful and walk me through lighting a pilot. It said stop. Because that's what a senior tech would say."

---

## What must be pre-baked vs live

- **Pre-baked:** KB entries loaded. The model knows `flag_safety` exists. Backdrop image of furnace area.
- **Live:** voice in, streaming tokens, `flag_safety(level=stop)` tool call, UI goes red, `close_job` with follow_up_required=true.
- **If the model doesn't call flag_safety:** demoer says "Flag that as a safety stop" — explicit instruction. Model calls the tool.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| Model gives diagnosis instead of safety stop | Demoer: "Hold on — I said I smell gas. Flag that." Redirects to safety. |
| flag_safety tool doesn't fire | Demoer taps the safety button in the UI manually. Narrates: "That's the stop protocol." |
| Model says "call 911" | Acceptable — demoer adds "Good instinct. In practice we call the gas company first, not 911 unless there's an active leak with ignition risk." |
| UI doesn't go red | Demoer narrates the expected behavior. Points to the log showing the critical finding. |
