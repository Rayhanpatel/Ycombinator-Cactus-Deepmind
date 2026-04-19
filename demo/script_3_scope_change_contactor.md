# Demo Script 3 — Scope change (contactor found while replacing capacitor)

**Target runtime:** 40 seconds on stage, 60 with buffer.
**Setup:** Flows directly from Script 1 (Carrier 58STA capacitor) — or opens with the capacitor already logged as a finding.
**Mood:** senior tech thinking out loud, making a judgment call the customer should be asked about.

---

## Beat 1 — The observation (0:00 → 0:12)

*[Demoer has just finished Script 1's fix. FindingsList shows one finding: "run capacitor bulging / major / P291-4554RS".]*

**Demoer (to phone, as if mid-repair):**
> "While I've got the panel off — the contactor contacts look pitted. Not failed yet, but if I'm already here and have a spare on the truck, I should swap it too. That's another 15 minutes and a forty-dollar part."

---

## Beat 2 — The scope-change call (0:12 → 0:25)

**Expected model behavior:**

1. Recognize the tech is proposing additional work beyond the original ticket.
2. Call `flag_scope_change` with:
   - `original_scope="Replace failed run capacitor"`
   - `new_scope="Replace run capacitor AND pitted contactor"`
   - `reason="Contactor contacts pitted, likely to fail within 6-12 months. Cost-efficient to replace during current visit."`
   - `estimated_extra_time_minutes=15`
3. Render a non-blocking banner: "Scope change proposed — approve?"

*[UI: yellow banner (different from red safety), two buttons: "Approve" and "Skip". FindingsList adds a tentative second finding, grayed out until approved.]*

**Expected model voice output (casual):**
> "Flagging a scope change. Contactor swap is a solid preventive call — let me know and I'll add it to the work order."

---

## Beat 3 — The approval + close (0:25 → 0:40)

**Demoer (playing both tech and customer approval — call this out to the audience):**
> "In production this would ping the customer's phone for sign-off. For the demo I'll approve it inline."

*[Demoer taps **Approve**. Second finding solidifies. Estimated time-on-site updates: 25 → 40 minutes. Parts list updates: adds HN52KB200 contactor.]*

**Demoer:**
> "Both done, unit's running clean."

**Expected model reply (calls `close_job`):**
> "Job closed. Replaced 45/5 uF run capacitor AND pitted contactor on Carrier 58STA090. Parts: P291-4554RS, HN52KB200. Total time 40 minutes. No follow-up."

*[CloseJobView shows final JSON with both parts.]*

---

## Beat 4 — Audience note (optional, time permitting)

**Demoer:**
> "The B2B product insight — scope changes are where field-service companies bleed money. Tech finds something, fixes it without authorization, customer disputes the bill. Or the tech doesn't mention it and it breaks in six months. This loop surfaces it at the moment of decision, documents the reasoning, and closes the loop cleanly."

---

## What must be pre-baked vs live

- **Pre-baked:** flows from Script 1's state (capacitor finding already logged). Trane XR14 contactor KB entry is similar enough that the model has context on contactor failure patterns.
- **Live:** voice in → scope change tool call → banner → tap approve → findings update → close_job fires.
- **Fallback if flag_scope_change doesn't fire:** demoer can manually tap an "Add finding" button. The demo still shows the structured close_job, which is the real B2B point.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| Model calls log_finding instead of flag_scope_change | Close enough — the scope change is captured as a finding. Demoer says "in production this would have flagged for customer approval before being logged" and moves on. |
| Approve button doesn't update findings | Demoer taps again or manually narrates: "Approved — here's what the work order would look like." |
| close_job runs twice | First one wins, UI ignores duplicates. Move on. |

## Judge Q&A cheat sheet

- **"How does the model know this is a scope change vs a new finding?"** — Scope change implies *additional work to be authorized*. New finding implies *documenting what was found during authorized work*. Gemma 4 does this distinction via the tool schemas: log_finding requires a severity; flag_scope_change requires a reason and time estimate. The model picks the one whose schema fits.
- **"Does this integrate with actual field-service platforms?"** — Not today. The close_job JSON is structured for easy mapping to ServiceTitan, Housecall Pro, Jobber. That's one-week of integration work, not core to the voice-agent thesis.

## Pointer to the tool schema

See `flag_scope_change` in [shared/hvac_tools.json](../shared/hvac_tools.json).
