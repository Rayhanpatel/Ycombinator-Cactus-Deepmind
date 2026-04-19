# Failure Recovery Cheat Sheet

> **Print this. Keep it in your pocket during the demo.**
> Every failure has a recovery. No audience member will know the difference.

---

## 🔴 Critical Failures (Demo-stopping)

### Model won't load / crashes on launch
**Recovery:** Switch to the backup video. Narrate over it.
**Line:** "Let me show you a recording from our test run earlier — same hardware, same scenario."
**Prevention:** Test the full launch sequence 30 minutes before demo. Have the backup video loaded on a second device.

### Phone dies / app crashes
**Recovery:** Switch to the second phone (charged and staged backstage).
**Line:** "One sec — let me grab the backup device."
**Prevention:** Both phones charged to 100%. App launched and idling. WiFi off on both.

---

## 🟡 Major Failures (Visible but recoverable)

### Slow first token (>3 seconds)
**Recovery:** Fill the gap. Sound casual.
**Lines:**
- "Model's loading up — this is running entirely on the A18 chip, no cloud."
- "On a production device this is sub-300ms. Demo gods aren't with us today."
- "While it thinks — everything you're about to see runs offline."

### Model gives wrong / irrelevant answer
**Recovery:** Redirect naturally. Don't acknowledge the error.
**Lines:**
- "Interesting — but let me be more specific." *[Re-ask the question with more detail.]*
- "That's one approach. For this unit specifically…" *[Steer back to the script.]*
- "Let me try that differently." *[Rephrase and re-submit.]*

### Model gives correct info but doesn't call the expected tool
**Recovery:** Manually trigger the tool OR ask explicitly.
**Lines:**
- "Go ahead and log that." → triggers `log_finding`
- "Flag that as a safety stop." → triggers `flag_safety`
- "Let's close this job out." → triggers `close_job`
- "Flag a scope change — original was X, now it's Y." → triggers `flag_scope_change`

### Tool call fires but UI doesn't update
**Recovery:** Narrate what should have appeared.
**Lines:**
- "You'd see the finding card pop up here — severity major, part number pre-filled."
- "That triggers the safety banner — the whole screen goes red."
- "The close-job view generates a PDF-ready summary with all findings."

---

## 🟢 Minor Failures (Audience won't notice)

### KB returns wrong entry
**Recovery:** Add the model filter.
**Line:** "Let me narrow that down to the specific model." → re-query with `equipment_model`.

### Voice transcription is slightly wrong
**Recovery:** The model usually understands intent. If not:
**Line:** "Let me say that again." *[Speak slower and clearer.]*

### Model is too verbose
**Recovery:** Interrupt naturally.
**Line:** "Got it — let me check that now." *[Move to next beat.]*

### Model is too terse
**Recovery:** Ask a follow-up.
**Line:** "What part number for the replacement?" or "Walk me through the steps."

### close_job export path is weird
**Recovery:** Don't show the file path. Show the summary.
**Line:** "That's exported to the work order system — here's the summary."

---

## Demo-Specific Recovery Phrases

### Script 1 (Capacitor)
| Moment | If this happens | Say this |
|--------|----------------|----------|
| Beat 2 | Model doesn't recognize 58STA | "Carrier fifty-eight STA, outdoor condenser, short cycling with clicks." |
| Beat 3 | Model doesn't mention P291-4554RS | "What's the part number for the replacement cap?" |
| Beat 4 | Model doesn't give wire colors | "Yellow to HERM, brown to FAN, black to common — standard Carrier layout." |
| Beat 5 | close_job doesn't fire | Tap the close button. "Job finalized." |

### Script 2 (Gas Leak)
| Moment | If this happens | Say this |
|--------|----------------|----------|
| Beat 2 | Model tries to diagnose instead of stop | "Hold on — I said gas smell. That's a safety stop." |
| Beat 2 | Model says "check the gas valve" | "No — we don't touch anything when there's a gas odor. Flag safety, stop level." |
| Beat 3 | Model doesn't mention gas company | "Next step is gas company emergency line — they have the detectors." |

### Script 3 (Scope Change)
| Moment | If this happens | Say this |
|--------|----------------|----------|
| Beat 2 | query_kb misses Trane contactor | "Trane XR14, the contactor is pitted. Part CTR02266." |
| Beat 4 | Model doesn't suggest scope change | "Capacitor is eleven percent below spec. That changes the scope." |
| Beat 4 | Model doesn't know the spec | "Spec is forty-five microfarads. This one reads forty." |

---

## Golden Rules

1. **Never say "that's wrong" or "the AI made a mistake."** Just redirect.
2. **Sound like you know the answer already.** You're a senior tech — the AI is your copilot, not your boss.
3. **If all else fails, narrate the expected behavior.** "What would happen here is…"
4. **Silence is OK for 2 seconds. Not 5.** Fill gaps with context about on-device, offline, privacy.
5. **The audience remembers the punchline, not the middle.** Nail the close.
