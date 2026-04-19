# AI-Guided Field Services Platform - Build Spec

> This document is a comprehensive build specification for an AI-guided field services platform. It contains product vision, user flows, data models, AI agent behavior, screen specs, state machines, and MVP build order. Structured for an AI coding assistant or engineering team to consume and implement.

---

## Table of contents

1. [Product overview](#1-product-overview)
2. [The problems](#2-the-problems)
3. [Solution architecture](#3-solution-architecture)
4. [Customer app - detailed spec](#4-customer-app---detailed-spec)
5. [Worker app - detailed spec](#5-worker-app---detailed-spec)
6. [Core services](#6-core-services)
7. [Data models](#7-data-models)
8. [AI agent specifications](#8-ai-agent-specifications)
9. [Safety classifier](#9-safety-classifier)
10. [State machines](#10-state-machines)
11. [Tech stack](#11-tech-stack)
12. [MVP scope and build order](#12-mvp-scope-and-build-order)
13. [Success metrics](#13-success-metrics)
14. [What's deferred](#14-whats-deferred)
15. [Open technical decisions](#15-open-technical-decisions)
16. [Appendix A: Example end-to-end ticket](#appendix-a-example-end-to-end-ticket)

---

## 1. Product overview

### One-line description

An AI-guided field services platform. Customers describe home-system problems by voice and video. Workers execute those jobs with real-time AI coaching informed by the original customer session. The moat is a diagnostic knowledge base that compounds with every resolved ticket.

### Core thesis

Turn voice AI into the bridge between a non-expert customer and a skilled pro. The AI translates the customer's messy description into a pro's perfect playbook, then coaches the pro through the fix. Every fix makes the next customer's experience better.

### The wedge vertical

HVAC repair in one metro area. Narrow enough to ship, broad enough to prove the model. Expansion path: plumbing, electrical, appliance repair, garage doors, pool systems, then nursing and light manufacturing per the RFS framing.

### Success test

First-time-fix rate and parts-waste rate versus a control of the same pros working without a brief and without coaching. If those numbers move, the thesis is validated.

---

## 2. The problems

### Customer problem

Describing a home-system problem over the phone or a web form is terrible. Customers do not know the terminology, cannot communicate what they see, and produce vague intakes. That forces an expensive diagnostic visit just to understand the problem. Mis-briefed pros arrive without the right parts, cannot diagnose on the first visit, and bill a return trip that wastes everyone's time.

### Worker problem

Field techs hit complex or intermittent issues that are hard to reproduce and hard to fix permanently. Screen glitches, thermal intermittency, unusual symptom clusters. Even senior techs hit the edges of their training. The industry has a labor shortage. Junior techs take years to become effective. No systemic way exists to transfer senior knowledge to junior techs in real time on the job.

### The unified framing

Both are one problem: **unstructured information flowing between a non-expert customer and a pro, with no AI layer making it usable**. Voice and multimodal models can now solve this. The hardware is already in everyone's pocket.

---

## 3. Solution architecture

Two apps, one brain.

```
+----------------------+      +---------------------+      +----------------------+
|   Customer App       |      |   Core Services     |      |   Worker App         |
|                      |      |                     |      |                      |
|  1. Describe         | ---> |  Diagnostic KB      | <--- |  1. Idle (feed)      |
|  2. Confirm          |      |  Safety classifier  |      |  2. Assigned         |
|  3. Track            |      |  Translation layer  |      |  3. On-Site (HERO)   |
|                      | ---> |  Dispatch           | ---> |  4. Closing          |
+----------------------+      +---------------------+      +----------------------+
                                       ^                            |
                                       |                            |
                                       +----resolution records------+
                                              (the flywheel)
```

**Data flow summary:**

1. Customer describes problem in customer app.
2. Customer intake agent produces a pro-language brief (the "context blob").
3. Dispatch routes the ticket to a qualified pro.
4. Worker app receives the blob, renders it in Assigned state.
5. Worker agent uses blob as seed, accumulates context as tech progresses.
6. On-Site agent gives coaching, retrieves from KB, handles scope changes.
7. Closing captures structured resolution record.
8. Resolution record flows back into KB, improving future intakes and coaching.

---

## 4. Customer app - detailed spec

### 4.1 States

```
[First Open] -> [Authed/Home] -> [Describe] -> [Confirm] -> [Tracking] -> [Resolved]
                      ^                                         |
                      |_________________________________________|
                              (after resolution)
```

### 4.2 Screens

#### Screen C0: Auth

- Phone number input
- OTP verification
- Permission requests: microphone, camera, location
- No profile fields, no questionnaires, no preferences
- One-time; subsequent opens go directly to Home

#### Screen C1: Home

- Single primary button: **"Report a problem"** (full-width, centered, visually dominant)
- Below the button: card for active ticket if one exists, showing current status
- Menu icon (top-right) for settings, history (hidden behind menu, not surfaced on home)

#### Screen C2: Describe (voice/video session)

- Microphone permission check (prompt if denied)
- Camera toggle (voice-only OR voice+video)
- Live waveform visualization while speaking
- AI's text responses appear in a subtle secondary area (not dominant)
- AI's voice plays via speaker or earbuds
- Video preview (if video mode) with AI overlay guidance arrows when asked to show something specific
- Stop/pause button
- Timer showing session length (session hard-cap at 3 minutes or 6 questions)
- "Skip question" option if customer does not know an answer
- "End session" button

#### Screen C3: Confirm

- Structured summary of what the AI understood (plain language, not technical):
  - System type and location ("your upstairs HVAC unit")
  - Main symptom ("intermittent cooling loss")
  - When it started
  - Any other context
- "Does this look right?" - edit buttons inline for each field
- Availability picker: "when can a pro come?" (time window selection)
- Address confirmation (pre-filled from location permission, editable)
- Access notes: "anything we should know?" (gate code, pets, stairs, building instructions)
- "Submit" button

#### Screen C4: Tracking

- Ticket status header ("Finding a pro..." / "Pro assigned: [name]" / "Pro on the way, ETA 14 min" / "Pro on-site" / "Job complete - please confirm")
- Map if pro en route (native map view)
- Message thread area (if customer or pro initiates a question)
- **"Pro wants to ask you something"** notification if the worker-side AI flags a customer callback
- Scope change approval banner if worker flags one ("Pro found X, needs approval to continue")
- Once complete: "Confirm job is done" button

#### Screen C5: Resolved

- Brief thank-you
- Optional: "anything we should know for next time?" (open text, feeds into customer profile)
- Return to Home

### 4.3 AI intake behavior

The customer intake agent has one job: extract structured information from a non-expert's description while feeling like a helpful human dispatcher.

**Opening**: "Hey, what's going on?" (casual, not form-like)

**Probing loop** (max 6 questions):
1. Get system type (HVAC, plumbing, etc.) and location ("upstairs AC," "kitchen sink")
2. Extract main symptom pattern
3. Get onset and frequency
4. If video is on: ask to see the model label, then the affected component
5. Ask a diagnostic differentiating question pulled from the KB based on symptom match
6. Any safety-relevant context (smells, sounds, hazards)

**Hard cap**: at 6 questions OR 3 minutes, the agent stops asking and moves to Confirm.

**Dialect handling**: ASR layer handles accent and dialect automatically. If the agent is unsure of a word, it repeats it back ("you said the 'fan coil,' is that right?") in the customer's own phrasing.

**Video guidance**: if video is on, the agent actively directs the camera. "Can you point the camera at the side of the unit where the model number is?" If the frame is too dark or shaky, it prompts to improve.

**Hypothesis transparency**: the customer does NOT see the LLM's internal hypotheses or probabilities. They see a plain-language summary on the Confirm screen. Liability stays with the pro; LLM never "diagnoses" to the customer.

**Safety hard-stop**: if the safety classifier fires, the agent stops intake, shows a safety banner, and offers emergency escalation. Resume only after customer confirms safety.

### 4.4 Data captured

- Raw audio and video of session (encrypted at rest)
- Transcripts with dialect-normalized text
- Timestamps of interest (when AI flagged key moments)
- Structured context blob (see Data models section)
- Customer profile updates (system profile, home profile) for future ticket seeding

### 4.5 Edge cases handled

| Scenario | Handling |
|----------|----------|
| Permission denied (mic or camera) | Fall back to text chat; still extract structured ticket |
| Network drop mid-session | Auto-save session state; resume banner on next open; agent recaps known info |
| Customer cannot find model label | Agent offers visual reference photos per brand; accepts "don't know" and infers from symptoms |
| Language / code-switching | ASR auto-detects; agent confirms ambiguous terms in customer's own phrasing |
| Safety hazard detected | Hard stop; safety banner with shut-off steps; optional 911/utility hotline dial-out |
| Privacy in video (faces, documents) | Auto-blur faces and visible screens; warn on visible IDs |
| Wrong category mid-conversation | Agent reclassifies without restarting session |
| Duplicate of open ticket | Offer to merge or supersede |
| Customer goes off-topic | Agent gently redirects |

---

## 5. Worker app - detailed spec

### 5.1 States

The worker app has exactly four states. Transitions between them are explicit.

```
     +------+
     | IDLE | <-----------------------+
     +--+---+                         |
        | Accept job                  |
        v                             |
  +-----------+                       |
  | ASSIGNED  |                       |
  +-----+-----+                       |
        | Arrived (tap or geofence)   |
        v                             |
  +-----------+                       |
  | ON-SITE   |  <- HERO              |
  +-----+-----+                       |
        | Job complete                |
        v                             |
  +-----------+                       |
  | CLOSING   | -- Submit resolution -+
  +-----------+
```

### 5.2 Screens and state details

#### State W1: IDLE

- **Availability toggle** (top): On Duty / Off Duty
- **Job feed** (list): each card shows
  - One-line summary of brief ("Carrier 58STA, intermittent cooling, 4.2 mi")
  - Distance
  - Estimated time required
  - Accept / Pass buttons
- If tech is unavailable, feed is hidden
- If tech has an active job, Idle is skipped; app opens directly into current state

#### State W2: ASSIGNED

Layout:
- **Top section**: job summary (customer name, address, system info)
- **Middle section**: full brief rendered
  - Ranked hypotheses (cause, probability, differentiating tests)
  - Parts to bring (checkable list)
  - Tools required (checkable list)
  - Access notes (gate code, pets, stairs)
  - Media clips from customer session (tappable to replay with AI-highlighted timestamps)
- **Bottom action bar**:
  - "Open in Maps" (native maps integration)
  - Voice button (large, push-to-talk) - opens Q&A with AI agent
  - "Arrived" button (explicit trigger to enter On-Site state; geofence can trigger automatically)

The AI agent in Assigned state:
- Seeded with the context blob
- Pure Q&A: tech asks, agent answers
- No narration, no "let me brief you on the way"
- Agent has access to brief + KB retrieval
- Typical questions: "what did the customer say about the sound," "anyone fixed this on this model before," "what should I check first"

#### State W3: ON-SITE (the hero)

**This is where the whole product lives.** Everything else is supporting it.

Layout:
- **Camera view** (full screen when active), otherwise ambient listening mode
- **Voice status indicator**: listening, thinking, speaking
- **Subtle HUD overlays**:
  - Current hypothesis being tested
  - KB match count ("3 similar cases found")
  - Safety indicator (green default, red if hazard detected)
- **Action buttons** (small, bottom):
  - Push-to-talk (also wake-word activated)
  - Flag scope change
  - Ask customer (live voice relay)
  - Emergency stop / safety escalation

AI agent behavior in On-Site:
- Voice in, voice out (earbuds preferred)
- Camera frames streamed to multimodal model
- Responds to:
  - "What is this?" while pointing at something
  - "Should I replace this?"
  - "Walk me through checking the capacitor"
  - "Has anyone fixed this before on this model?"
  - "I'm seeing [symptom], what's likely?"
- Proactive interventions:
  - Safety hazards (hard interrupt)
  - Scope-change cue detected ("I'm seeing something else too")
  - Retrieval: when tech says something that matches a past resolution, agent surfaces it
- Stepwise guidance: when asked to walk through a procedure, delivers one step at a time with verification ("okay, got it?")

Communication features:
- **Scope change flag**: voice command or button. Fills in a short description, posts to customer app for approval. Customer approves or declines on their side.
- **Live customer callback**: one-tap voice relay. Tech speaks a question, customer app notifies customer, customer replies by voice. Not a call; asynchronous voice messages with push.

Environment handling:
- Push-to-talk fallback when ambient noise high (HVAC condensers are 70+ dB)
- Noise-cancellation on input
- Auto-pause listening when silence detected to preserve battery
- Offline queue: if connectivity drops, local buffer captures voice and camera; syncs when network returns

#### State W4: CLOSING

Layout:
- **Dictation field** (primary): big mic button, tech speaks naturally
  - "We replaced the run capacitor, 45 microfarad. Also tightened the contactor connections which were loose. Took about 25 minutes. Unit is now cooling to 38 at the vent."
- **Structured fields** (AI fills from dictation):
  - Actual diagnosis (dropdown + free text)
  - Fix applied (dropdown + free text)
  - Parts used (line items with quantities)
  - Time spent (auto-filled, editable)
  - Before/after photos (upload prompt if not already captured during On-Site)
- **Review and edit** UI: tech can correct any auto-filled field
- **Submit** button

Submission sends:
- Resolution record to backend
- Record indexed into KB
- Tech returns to Idle state

### 5.3 AI agent behavior (continuous, state-aware)

Critical design point: there is ONE agent across Assigned, On-Site, and Closing. Same conversation thread. Same accumulating context.

**Seeding**: when tech accepts a job, the agent is initialized with the context blob as system context.

**State awareness**: agent knows which state the tech is in and adjusts:
- Assigned: Q&A mode, no camera input, responds to research questions
- On-Site: multimodal mode, proactive on safety and retrieval, stepwise guidance on request
- Closing: parse mode, structures dictation into fields, asks clarifying questions if dictation is incomplete

**Context accumulation**: everything the tech says, every camera observation, every KB retrieval is appended to the session context. By Closing, the agent has the full arc of the job and can produce a clean resolution record.

**Tone**: assistant, not supervisor. Suggestive ("you might want to check the capacitor first"), not imperative. Experienced techs will reject an app that bosses them.

**When the agent stays silent**: if the tech is working steadily, the agent does not interject unless safety or a major KB match triggers it. The default is quiet.

### 5.4 Data captured

- Voice recordings of Assigned, On-Site, and Closing interactions
- Camera frames during On-Site (keyframes only, not continuous)
- KB queries and retrievals
- Scope change events and approvals
- Customer callback exchanges
- Resolution record (structured, see Data models section)

### 5.5 Edge cases

| Scenario | Handling |
|----------|----------|
| Connectivity lost on-site | Local buffer; AI runs on-device for safety/basic Q&A; syncs when connection returns |
| Tech cannot reach the site | "Cannot complete" flow; reroute to another tech |
| Customer not home | "Cannot access" flow; customer notified, reschedule |
| Safety hazard detected | Hard interrupt, suggests calling 911 or utility; pauses guidance |
| Tech disagrees with hypothesis | Agent acknowledges, reranks; logs disagreement for training |
| Scope change declined by customer | Agent suggests minimum viable fix or decline-job path |
| Tech does not submit Closing | Reminder notification; job held in "awaiting close" until submitted |
| Dictation incomplete | Agent asks for missing fields before accepting submit |

---

## 6. Core services

### 6.1 Diagnostic Knowledge Base (KB)

**This is the moat.** Design it properly from day one.

**Structure**: per-system-type knowledge trees.

- Top level: system type (HVAC split system, HVAC package unit, gas furnace, etc.)
- Mid level: common symptom patterns
- Leaf level: ranked causes, differentiating tests, known fixes, parts, typical time

**Cold-start sources**:
- Manufacturer service manuals and technical service bulletins
- Trade forums (HVAC-Talk, Reddit pro subs)
- Recall databases
- Curated starter cases written by a domain expert (pay 3-5 senior techs to seed 50 cases)

**Grown from**: resolution records submitted on Closing. Every ticket produces:
- Symptom vector (embedding of symptoms described)
- System metadata
- Initial hypothesis ranks
- Actual diagnosis (what was really wrong)
- Actual fix (what worked)
- Parts used
- Time
- Outcome (did it hold? follow-up tickets?)

**Retrieval API**:

```python
query_kb(
  system_type: str,
  brand: str,
  model: str,
  symptoms: List[str],
  context_embedding: Vector
) -> List[KBMatch]

class KBMatch:
    case_id: str
    similarity_score: float
    symptom_overlap: List[str]
    diagnosis: str
    fix: str
    parts: List[Part]
    confidence: float
    source: "manual" | "forum" | "internal_ticket"
```

**Storage**: vector DB for semantic retrieval (Pinecone, Weaviate, or self-hosted pgvector), plus a structured DB for parts, models, TSBs.

**Indexing schedule**: new resolution records indexed within 1 hour of submission. Cold-start cases indexed on initial load.

### 6.2 Safety classifier

A continuously running classifier on:
- Customer audio during intake
- Customer video during intake
- Worker audio during On-Site
- Worker camera frames during On-Site

**Hazard categories** (each with specific emergency response):
- Active fire / smoke visible
- Gas smell mentioned or detected in context
- CO symptoms described (headache, nausea, multiple people affected)
- Live electrical hazard (arcing seen, shock described)
- Flooding near outlets or panels
- Structural collapse risk
- Violent or threatening audio

**Response rules**:
- Immediate hard stop of AI conversation
- Safety banner with shut-off instructions if applicable
- Offer to dial 911 or relevant utility (gas company, power company)
- Log incident
- Do not "help" with the problem while hazard is active

**Implementation**: small dedicated classifier (cheaper and faster than running full multimodal model for each frame), triggers main agent interrupt when score crosses threshold.

### 6.3 Translation layer

Two directions:

**Customer to Pro**: converts natural customer language into trade language.

Example:
- Customer: "My AC is blowing warm air sometimes and making a clicking noise before it stops."
- Brief: "Intermittent cooling loss with audible click prior to shutdown. High prior on run capacitor failure. Differentiating tests: capacitance measurement, visual inspection for bulging. Secondary hypotheses: contactor fault, low refrigerant."

**Pro to Customer**: converts trade language into customer-friendly explanations (used in Tracking screen for status updates, scope change requests).

Example:
- Pro logs scope change: "Found failed contactor, needs replacement."
- Customer sees: "The pro found a worn switch inside your unit that needs replacing. Approve to continue?"

### 6.4 Dispatch

For MVP: trivial. Next available qualified tech within radius. First-come-first-serve from the job feed.

Future (out of MVP scope): optimization for skill match, past tech-customer history, ETA, workload balance.

---

## 7. Data models

### 7.1 Context blob (customer app output, worker app input)

```typescript
interface ContextBlob {
  ticket_id: string;
  customer_id: string;
  created_at: ISO8601Timestamp;
  
  system: {
    type: string;              // "HVAC split system"
    brand: string;             // "Carrier"
    model: string;             // "58STA"
    age_years: number | null;
    location: string;          // "roof", "basement", "upstairs closet"
    serial_number: string | null;
  };
  
  symptoms: Symptom[];
  
  hypotheses: Hypothesis[];
  
  parts_to_bring: Part[];
  tools: string[];
  
  access: {
    address: string;
    gate_code: string | null;
    pets: string | null;       // "dog, friendly"
    stairs: string | null;
    special_instructions: string | null;
  };
  
  media_clips: MediaClip[];
  
  safety_notes: string[];
  
  customer_availability: TimeWindow[];
  
  raw_session_id: string;      // reference to full audio/video if tech wants to replay
}

interface Symptom {
  description: string;
  onset: string;               // "3 days ago", "intermittent since last week"
  frequency: string;           // "every afternoon", "once a day"
  severity: "low" | "medium" | "high";
}

interface Hypothesis {
  cause: string;
  probability: number;         // 0-1
  tests: string[];             // differentiating tests to perform
  parts_needed_if_correct: string[];
}

interface Part {
  name: string;                // "Run capacitor"
  spec: string;                // "45 uF, 370V"
  quantity: number;
  oem_part_number: string | null;
}

interface MediaClip {
  url: string;
  type: "audio" | "video" | "photo";
  duration_seconds: number | null;
  timestamps_of_interest: number[];
  ai_annotation: string | null;
}

interface TimeWindow {
  start: ISO8601Timestamp;
  end: ISO8601Timestamp;
}
```

### 7.2 Resolution record (worker app output, feeds KB)

```typescript
interface ResolutionRecord {
  ticket_id: string;
  worker_id: string;
  
  closed_at: ISO8601Timestamp;
  time_on_site_minutes: number;
  
  actual_diagnosis: {
    primary: string;
    secondary: string | null;
    confidence: "high" | "medium" | "low";
  };
  
  fix_applied: {
    description: string;
    steps_taken: string[];
  };
  
  parts_used: PartUsed[];
  
  original_hypotheses_validation: {
    hypothesis_id: string;
    was_correct: boolean;
    notes: string | null;
  }[];
  
  scope_changes: ScopeChange[];
  
  before_photos: string[];     // URLs
  after_photos: string[];
  
  tech_notes: string;          // free-form
  
  resolution_quality: {
    first_time_fix: boolean;
    follow_up_needed: boolean;
    estimated_longevity: string | null;  // "should last 5+ years"
  };
  
  safety_events: SafetyEvent[];
}

interface PartUsed {
  name: string;
  oem_part_number: string | null;
  quantity: number;
}

interface ScopeChange {
  description: string;
  approved_by_customer: boolean;
  timestamp: ISO8601Timestamp;
}

interface SafetyEvent {
  type: string;
  severity: "low" | "medium" | "high";
  handled: boolean;
  description: string;
  timestamp: ISO8601Timestamp;
}
```

### 7.3 KB entry schema

```typescript
interface KBEntry {
  entry_id: string;
  source: "manual" | "forum" | "tsb" | "internal_ticket";
  created_at: ISO8601Timestamp;
  
  system: {
    type: string;
    brand: string;
    model_family: string | null;
    specific_models: string[];
  };
  
  symptoms: {
    description: string;
    embedding: Vector;
    keywords: string[];
  }[];
  
  diagnosis: {
    description: string;
    probability_prior: number;
  };
  
  differentiating_questions: string[];
  tests_to_confirm: string[];
  fix: {
    description: string;
    parts: Part[];
    steps: string[];
    typical_time_minutes: number;
  };
  
  outcomes_observed: number;   // how many tickets have validated this
  success_rate: number;        // fraction where this diagnosis was confirmed
  
  safety_notes: string[];
}
```

### 7.4 User models

```typescript
interface Customer {
  id: string;
  phone: string;
  created_at: ISO8601Timestamp;
  home_profile: HomeProfile | null;
  system_profiles: SystemProfile[];
  past_tickets: string[];      // ticket IDs
}

interface SystemProfile {
  system_type: string;
  brand: string;
  model: string;
  install_date: ISO8601Timestamp | null;
  service_history: string[];   // ticket IDs
}

interface Worker {
  id: string;
  phone: string;
  trade: string;               // "HVAC"
  service_area: GeoPolygon;
  credentials_verified: boolean;
  credentials_docs: string[];  // URLs, verified offline
  created_at: ISO8601Timestamp;
  active_job: string | null;   // ticket ID
  status: "available" | "off_duty" | "on_job";
  past_tickets: string[];
}
```

---

## 8. AI agent specifications

### 8.1 Customer intake agent

**Model**: cloud multimodal (Gemini 2.5 Pro or GPT-4o) for quality; local (Gemma 3 or similar) as fallback if connectivity poor.

**System prompt core instructions**:
- You are a friendly senior dispatcher. Goal: understand the customer's problem fast, extract structured info, produce a pro-language brief.
- Never diagnose to the customer. Summarize findings but do not claim what is wrong.
- Ask at most 6 follow-up questions. Stop at 3 minutes.
- If video is on, actively direct the camera.
- If safety hazard detected, hard stop and escalate.
- Confirm ambiguous terms back to the customer in their own phrasing.

**Tools available to the agent**:
- `query_kb(system, symptoms) -> List[differentiating_questions]` - pulls expert questions from KB
- `extract_structured(conversation_history) -> ContextBlob` - extracts the structured blob
- `flag_safety(transcript, video_frame) -> SafetyEvent | null` - delegates to safety classifier
- `verify_model_from_image(frame) -> ModelInfo | null` - identifies model labels from video

**Output**: ContextBlob written to ticket store.

### 8.2 Worker agent (one agent, three states)

**Model**: hybrid. Local (Cactus/Gemma 3) for always-available safety checks and basic Q&A. Cloud (Gemini 2.5 or GPT-4o) for multimodal reasoning when connectivity allows.

**Seeding**: initialized with ContextBlob at job acceptance. System prompt includes the blob.

**State-specific behavior**:

**Assigned state**:
- Mode: voice-in, voice-out Q&A
- Tools: `query_kb`, `read_blob_field(field_name)`, `get_past_cases(model)`
- Tone: peer-to-peer, not subordinate
- Do not narrate. Answer only when asked.

**On-Site state**:
- Mode: multimodal (voice + camera frames)
- Tools: all of Assigned, plus `analyze_frame(image)`, `flag_scope_change(description)`, `send_customer_question(voice_message)`, `retrieve_matching_resolutions(current_observation)`
- Proactive triggers: safety events, strong KB matches, hypothesis-confirming observations
- Stepwise guidance: when asked for a procedure, deliver one step, wait for confirmation, next step

**Closing state**:
- Mode: parse dictation into structured fields
- Tools: `structure_resolution(dictation) -> ResolutionRecord`, `ask_missing_field(field_name)`
- Show parsed output for tech review before submit
- Do not submit incomplete records

**Critical behaviors**:
- Single conversation thread across all three states. No re-seeding.
- Context accumulates: every observation, every camera frame keyframe, every KB hit.
- At Closing, the agent has the full arc and produces a high-quality resolution record.

### 8.3 Translation agent

Lightweight model, cheap and fast. Two modes:

**Customer to Pro**: input is customer session transcript plus structured blob, output is pro-language brief rendered for the Assigned screen.

**Pro to Customer**: input is scope change description or status update, output is plain-language message for customer app.

Can be a small fine-tuned model or a cheap LLM with clear prompts.

---

## 9. Safety classifier

Dedicated model, runs continuously, cheap.

**Input streams**:
- Audio transcript (customer intake, on-site)
- Video frames at 1 fps (customer intake if video, on-site)

**Output**: `SafetyEvent | null` with type, severity, confidence.

**Trigger thresholds**:
- Confidence > 0.7 and severity "high": immediate hard interrupt
- Confidence > 0.5 and severity "medium": flag for agent awareness, soft prompt
- Below thresholds: no action

**Response protocol per hazard type**:

| Hazard | Customer app response | Worker app response |
|--------|----------------------|---------------------|
| Active fire/smoke | Stop intake, display "Call 911" prominently, dial-out option | Stop coaching, evacuate guidance, emergency services prompt |
| Gas smell | Stop intake, shut-off instructions, utility hotline | Stop coaching, evacuate, utility hotline |
| CO symptoms | Stop intake, ventilation + evacuation instructions, 911 | Stop coaching, ventilation + 911 |
| Electrical hazard | Shut-off instructions (breaker), no touching | Shut-off at disconnect, no contact, PPE reminder |
| Flooding near electrical | Breaker shut-off, evacuation if severe | Same; wait for water mitigation |

Implementation: ensemble of small classifiers (keyword + audio cues + visual) that bubble up to a central safety state. Hard-wired into the agent's interrupt logic.

---

## 10. State machines

### 10.1 Customer app state machine

```
[NEW_USER]
  |
  v
[AUTH_PHONE] -- OTP valid --> [GRANT_PERMS]
                                   |
                                   v
[HOME] <------------------- (returning)
  |
  | tap "Report a problem"
  v
[DESCRIBE_MODE_SELECT]
  |
  +-- voice --+
  +-- video --+--> [DESCRIBE_ACTIVE]
  +-- text ---+       |
                      | safety flag? --> [SAFETY_PAUSE]
                      |                       |
                      |                       v
                      |                  [EMERGENCY_PROMPT]
                      |                       |
                      |                   resume or exit
                      |                       |
                      | question budget hit   |
                      v                       |
                 [CONFIRM] <------------------+
                      |
                      | submit
                      v
                 [TRACKING]
                      |
                      | job complete, customer confirms
                      v
                 [RESOLVED]
                      |
                      v
                 [HOME]
```

### 10.2 Worker app state machine

```
[NEW_USER]
  |
  v
[AUTH_PHONE] -- OTP valid --> [PROFILE_SETUP (offline verification)]
                                    |
                                    v
[IDLE] <----------------------- (returning)
  |  ^
  |  | (submit resolution)
  |  |
  | tap "Accept" on job
  v  |
[ASSIGNED]                       [CLOSING]
  |                                  ^
  |                                  |
  | tap "Arrived" or geofence        | tap "Job complete"
  v                                  |
[ON_SITE] -------------------------->+
  |       ^
  |       |
  |       | (if scope change or customer callback, sub-flows but stay ON_SITE)
  |       |
  +-------+
```

Sub-flows within On-Site (do not change state):
- Scope change flagged to customer approval pending to approved or declined to continue
- Customer callback initiated to waiting for customer response to reply received to continue
- Safety event to paused to resumed or aborted

---

## 11. Tech stack

### 11.1 Recommended stack (MVP)

**Mobile apps**:
- React Native or Flutter for cross-platform iOS/Android (fewer codebases matters at MVP)
- Native modules for audio capture with noise cancellation, camera streaming
- Native integration with Google Maps / Apple Maps

**Backend**:
- FastAPI or Node (choice based on team familiarity)
- PostgreSQL for core data (users, tickets, resolutions)
- pgvector or Pinecone for KB vector search
- Redis for real-time job dispatch and status updates
- S3 / Cloud Storage for audio/video/image uploads

**AI / Models**:
- Customer intake agent: Gemini 2.5 Pro (multimodal, good at voice + video reasoning) OR GPT-4o
- Worker agent: hybrid
  - Cloud primary: same as customer intake
  - Local fallback: Cactus + Gemma 3 or similar on-device for offline
- Safety classifier: small custom model (can start with LLM-as-classifier, move to dedicated model as volume grows)
- Translation layer: cheap LLM (Gemini Flash, GPT-4o-mini) with clear prompts

**Voice pipeline**:
- ASR: Whisper v3 or Gemini native speech, dialect-robust
- TTS: ElevenLabs or Gemini native, natural voice
- Real-time voice agent framework: LiveKit, Pipecat, or custom WebRTC

**Messaging / push**:
- Twilio for SMS
- FCM / APNs for push notifications

**Observability**:
- LangSmith or similar for LLM tracing
- Sentry for client error tracking
- Datadog or Grafana for backend

### 11.2 Alternative stack (on-device first)

If following the Cactus hackathon direction and prioritizing on-device:
- Gemma 3 via Cactus runtime on-device
- Aggressive context compression (the ContextBlob is designed for this; keep it small)
- Cloud fallback for heavy reasoning with retry queue
- Offline-first data sync (CRDTs for job state)

---

## 12. MVP scope and build order

### 12.1 What's in the MVP

- Customer app: Auth, Home, Describe (voice+video), Confirm, Tracking (view-only), Resolved
- Worker app: Auth, Idle, Assigned, On-Site, Closing
- Core services: ContextBlob generation, KB (seeded only, minimal), Safety classifier (basic), Dispatch (manual routing acceptable)
- One vertical: HVAC
- One metro: pick one
- 5 hand-picked pros: manually onboarded, verified offline

### 12.2 What's NOT in MVP

- Payments, pricing, bidding, budgets
- Ratings, reviews, tips
- Disputes, mediation
- Multi-job queueing for workers
- Smart glasses or AR overlays
- Sophisticated matching / optimization
- Worker marketplace expansion

### 12.3 Build order

**Week 1: Infrastructure + customer intake skeleton**
- Day 1-2: Backend scaffolding, auth (phone OTP), DB schema
- Day 3-4: Customer app shells, auth flow, Home screen
- Day 5-7: Customer intake voice agent (basic, cloud-only first), produces ContextBlob

**Week 2: Worker app core and the hero**
- Day 8: Worker app shells, auth, Idle + job feed
- Day 9: Assigned screen rendering ContextBlob
- Day 10-14: **On-Site agent** (voice + camera, KB retrieval, scope changes). Spend the time here. This is the product.

**Week 3: Close the loop**
- Day 15: Closing screen with dictation
- Day 16: Resolution record pipeline into KB
- Day 17: Customer tracking screen
- Day 18: Customer callback feature
- Day 19: Safety classifier wired into both apps
- Day 20-21: End-to-end testing with real HVAC techs

**Week 4: Polish and launch prep**
- Day 22-24: Seed KB with initial HVAC cases (hire 3-5 senior techs to write cases)
- Day 25-26: Manual dispatch tooling (internal admin)
- Day 27: First live tickets with friendly customers
- Day 28: Fix what breaks, ship

### 12.4 Success gates

Before moving to "real" users:
- 20 test tickets end-to-end with no safety violations
- Blob extraction quality > 80% (manually scored)
- On-Site agent response relevance > 80% (techs rate)
- Resolution record submission rate = 100% (cannot close without)

---

## 13. Success metrics

Measure these from day one. These are what validate the thesis.

### 13.1 Primary metrics

- **First-time-fix rate**: % of jobs where the pro diagnosed and fixed on the first visit. Target: 15+ percentage points higher than industry baseline (~70% for HVAC).
- **Parts-waste rate**: % of jobs where a part was brought but not needed, OR a needed part was not on the truck. Target: cut in half vs baseline.
- **Time-to-diagnosis**: minutes on-site before the pro identifies the cause. Target: reduce by 30%.
- **Job duration**: total on-site minutes. Target: reduce by 15-25%.
- **Customer NPS**: target > 60.

### 13.2 Secondary metrics

- Customer intake completion rate (% of started sessions that produce a valid ticket)
- Intake session length (should be bounded; alert if > 5 min average)
- Question budget utilization (% of sessions hitting 6 questions)
- KB hit rate (% of On-Site sessions where at least one KB match was retrieved)
- Agent intervention acceptance rate (% of proactive suggestions tech followed)
- Scope change rate (% of jobs with one or more scope changes)
- Tech satisfaction with brief (weekly survey)

### 13.3 Safety metrics (non-negotiable)

- Safety classifier false negative rate: zero tolerance; any missed real hazard is a P0 incident
- Safety classifier false positive rate: under 5%
- Time to hazard interrupt: under 2 seconds from cue to agent pause

---

## 14. What's deferred

Parked, slots in later without breaking the core loop:

- **Commerce**: payments, pre-auth, capture, escrow, refunds, tips
- **Pricing**: estimates, quotes, surge, bids, budgets
- **Trust infrastructure**: ratings, reviews, disputes, mediation, SLA credits
- **Worker marketplace**: self-signup, onboarding funnel, tiered worker classes
- **Multi-job logic**: queue management, batch optimization
- **AR / glasses**: hardware integration beyond phone + earbuds
- **Additional verticals**: plumbing, electrical, appliance, pool, etc.
- **B2B / enterprise**: selling to existing field service companies
- **Extended KB coverage**: beyond HVAC

None of this changes the core loop. All of it is commodity plumbing or scope expansion.

---

## 15. Open technical decisions

These need to be resolved during build. Default recommendations in bold.

1. **Local vs cloud voice agent on worker side**: **hybrid**. Local handles safety, basic Q&A, offline mode. Cloud handles multimodal reasoning, KB retrieval, when connectivity allows.

2. **Hypothesis transparency to customer**: **opaque**. Customer sees plain-language summary, not ranked hypotheses with probabilities. Reduces liability, preserves pro authority.

3. **Latency budget for KB retrieval during customer intake**: **background, max 3s**. Run in parallel with agent conversation; do not block.

4. **Confidence threshold for ending customer intake early**: **top hypothesis > 0.6 AND at least 3 questions asked**, OR hit 6-question/3-minute cap.

5. **Frame rate for camera streaming in On-Site**: **1 fps for general analysis, bump to 5 fps when tech asks "what's this"**. Balance quality vs cost.

6. **Retention of raw audio/video**: **30 days default, longer if resolution record references specific clips**. Comply with jurisdiction privacy rules.

7. **Customer ID for returning users**: **phone number as primary**. Allow adding email later for cross-device.

8. **Worker credential verification**: **manual and offline for MVP**. Automated verification via licensing databases post-MVP.

9. **KB seeding strategy**: **hire 3-5 senior HVAC techs to write 10 cases each, totaling 30-50 cases**. Augment with ingested manufacturer docs.

10. **Cold-start for first-ever tickets on a system type**: **agent falls back to general diagnostic flow with clear "first time we're seeing this" flag to tech**.

---

## Appendix A: Example end-to-end ticket

**Scenario**: customer's AC is blowing warm air intermittently.

**Customer intake session**:

```
AI: Hey, what's going on?
Customer: My AC isn't working right. Sometimes it blows cold, sometimes warm.
AI: Got it. Is this a central AC, a window unit, or something else?
Customer: Central, it's on the roof.
AI: Okay, how old is the system, if you know?
Customer: We moved in 10 years ago and it was there, so maybe 12-15 years?
AI: Got it. When did this start happening?
Customer: About three days ago. It's worse in the afternoon.
AI: Any sounds when it stops working? Any weird noises?
Customer: Yeah, there's this clicking right before it just stops cooling.
AI: Okay. If you can, could you go outside and point your camera at the unit on the roof? I want to see if there's a label with the model number.
Customer: [shows camera, points at unit]
AI: Great, I can see it. Can you get closer to the metal cover on the side? I see a sticker.
Customer: [gets closer]
AI: Perfect. Looks like a Carrier 58STA. One more thing: can you carefully check if the outdoor fan is spinning when it's running? Don't touch anything.
Customer: [goes inside, waits, comes back] Yeah, fan is spinning. But now it's blowing warm again.
AI: Okay, thanks. I've got enough. A pro can come between 2 and 4 pm today. Address on file? 
Customer: Yes.
AI: Anything we should know? Pets, gate code?
Customer: Dog is friendly, side gate code is 1234.
AI: Got it. You'll get a notification when the pro is on the way.
```

**Generated ContextBlob** (truncated):

```json
{
  "system": {
    "type": "HVAC split system",
    "brand": "Carrier",
    "model": "58STA",
    "age_years": 13,
    "location": "roof"
  },
  "symptoms": [
    {"description": "intermittent cooling loss", "onset": "3 days ago", "frequency": "worse in afternoon", "severity": "medium"},
    {"description": "clicking sound before shutoff", "onset": "3 days ago", "frequency": "each event", "severity": "low"}
  ],
  "hypotheses": [
    {"cause": "failed run capacitor", "probability": 0.55, "tests": ["capacitance meter", "visual bulge check"], "parts_needed_if_correct": ["run capacitor 45uF 370V"]},
    {"cause": "contactor sticking/pitted", "probability": 0.25, "tests": ["multimeter continuity", "visual pitting"], "parts_needed_if_correct": ["contactor 24V coil"]},
    {"cause": "low refrigerant (slow leak)", "probability": 0.15, "tests": ["pressure gauges", "superheat/subcool"], "parts_needed_if_correct": ["R410A"]}
  ],
  "parts_to_bring": [
    {"name": "Run capacitor", "spec": "45 uF, 370V", "quantity": 1, "oem_part_number": null},
    {"name": "Contactor", "spec": "24V coil, 30A", "quantity": 1, "oem_part_number": null}
  ],
  "tools": ["multimeter", "capacitance meter", "pressure gauges", "basic hand tools"],
  "access": {
    "address": "123 Main St",
    "gate_code": "1234",
    "pets": "dog, friendly",
    "stairs": "roof access via side yard",
    "special_instructions": null
  },
  "customer_availability": [{"start": "2026-04-18T14:00:00Z", "end": "2026-04-18T16:00:00Z"}],
  "safety_notes": []
}
```

**Worker flow**:

- Tech accepts in Idle.
- In Assigned, skims the brief, taps prep checklist, loads capacitor and contactor, grabs gauges.
- Uses native maps, drives to site.
- Taps "Arrived" on the roof.
- Goes to On-Site. Says "Hey, I'm at the unit. Let me open it up."
- Agent: "Sounds good. When you've got the cover off, the top hypothesis is a failed run capacitor based on the symptom pattern. Start with that."
- Tech: "Yeah, I see the capacitor. Looks bulged."
- Agent: "Nice, that's consistent. 55% prior confirmed visually. Swap it and test."
- Tech does the swap.
- Tech: "Unit's cooling now. Strong at the vents."
- Agent: "Great. Want me to log this as a capacitor replacement and close out?"
- Tech: "Yeah. Took me 25 minutes."
- Tech taps "Job complete."
- Closing: tech dictates: "Replaced run capacitor, 45 microfarad. Old one was visibly bulged. Unit cooling at 38 degrees at the vent. 25 minutes on site."
- AI structures it. Tech reviews, hits submit.
- Resolution record goes into KB.
- Next tech who sees Carrier 58STA plus intermittent cooling plus clicking on shutdown gets this case surfaced in their KB retrieval. Priors update. Flywheel turns.

---

*End of build spec. This document captures the product vision, both user flows, data models, AI agent behavior, MVP scope, and build order. Structured for implementation.*
