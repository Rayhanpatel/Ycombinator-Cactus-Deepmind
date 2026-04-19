# Demo Script 3 — Scope Change (contactor + weak capacitor)

**Target runtime:** 2m 45s on stage, 3m 15s with buffer.
**Setup:** Demoer holding phone. Backdrop: Trane XR14 outdoor condenser.
**Mood:** experienced tech, methodical — discovers more than expected.

---

## Beat 1 — Setup (0:00 → 0:15)

**Demoer (to audience):**
> "Dispatch says: 'Trane XR14, outdoor unit won't start, thermostat calling for cool.' Straightforward contactor swap — I've done five hundred of these. Let's see."

*[Demoer taps mic button. Red ring activates.]*

---

## Beat 2 — Initial diagnosis (0:15 → 0:50)

**Demoer (to phone):**
> "Trane XR14, model 4TTR4. Thermostat is calling, indoor blower is running. Outdoor unit is dead. I've got twenty-four volts at the Y terminal but nothing's happening."

**Expected model reply (calls `query_kb` → returns trane-xr14-contactor):**
> "That's a textbook failed contactor on the XR14. Common after five to eight years in humidity. Open the control compartment and check the contactor — look for pitted contacts, burn marks, or a coil that reads open. Should be ten to twenty ohms across the coil."

*[KB result card appears: Trane XR14 contactor, CTR02266]*

---

## Beat 3 — Contactor confirmed bad (0:50 → 1:15)

**Demoer:**
> "Yeah, contacts are pitted. Coil reads open — no continuity. This contactor is toast. I've got a CTR02266 on the truck."

**Expected model reply (calls `log_finding`):**
> "Logged. Failed contactor with open coil — major severity. Part: CTR02266. While you're in there, check the run capacitor too. On these XR14s they tend to go weak around the same time."

*[Finding logged: `[major] Failed 24V contactor — open coil / outdoor condenser`]*

---

## Beat 4 — The scope change (1:15 → 1:55)

**Demoer:**
> "Good call. Let me check the cap… measuring forty on the compressor side. Spec is forty-five. It's within tolerance but it's weak."

**Expected model reply (calls `flag_scope_change`):**
> "That cap is down about eleven percent — it'll fail within a season. I'd recommend replacing it now while you're here. That changes the scope: original work order was contactor only, now it's contactor plus run capacitor. Want me to flag the scope change for the customer?"

**Demoer:**
> "Yeah, flag it."

*[Scope change card appears:]*
```
🔄 SCOPE CHANGE
Original: Contactor replacement
New: Contactor + run capacitor replacement  
Reason: Capacitor at 40µF vs 45µF spec — 11% degraded, will fail within season
Extra time: ~15 minutes
```

---

## Beat 5 — Fix and close (1:55 → 2:30)

**Demoer:**
> "Both parts swapped. Unit's running clean, contactor pulls in, compressor starts. Pressures look good."

**Expected model reply (calls `log_finding` for capacitor, then `close_job`):**
> "Second finding logged — weak capacitor replaced preventively. Job closed. Summary: replaced failed 24V contactor CTR02266 and weak run capacitor on Trane XR14 4TTR4. Scope expanded from contactor-only to include preventive cap replacement. Parts: CTR02266, run capacitor. No follow-up needed."

*[CloseJobView appears with both findings, scope change documented, parts list. Demoer taps "Finalize & send."]*

---

## Beat 6 — The punchline (2:30 → 2:45)

**Demoer (to audience):**
> "Two things happened there. One: it found the contactor in the KB in under a second, on device. Two: it told me to check the capacitor — I didn't ask. That's the difference between a search engine and a copilot. It flagged the scope change so the customer isn't surprised on the invoice."

---

## What must be pre-baked vs live

- **Pre-baked:** KB entries for XR14 contactor AND Carrier 58STA capacitor loaded. Tool schemas registered.
- **Live:** voice in, `query_kb` → match, `log_finding` × 2, `flag_scope_change`, `close_job`, UI updates.
- **If the model doesn't suggest checking the cap:** demoer says "I'm also going to check the capacitor while I'm here." Then reports the weak reading and lets the model call flag_scope_change.

## Failure modes + recoveries

| Fails during demo | Recovery |
|---|---|
| query_kb returns wrong entry | Demoer: "Let me narrow it down — Trane XR14 contactor specifically." Re-queries with model filter. |
| Model doesn't suggest checking cap | Demoer checks it on their own. Narrates: "Good practice to check the cap too." Reports the reading. |
| flag_scope_change doesn't fire | Demoer: "Flag a scope change — original was contactor, now add capacitor." Explicit instruction. |
| close_job misses one finding | Demoer reviews the export JSON. "Both findings are in the log — the export captures everything." |
| Two findings merge into one | Acceptable — demoer mentions both parts in the close_job summary. |
