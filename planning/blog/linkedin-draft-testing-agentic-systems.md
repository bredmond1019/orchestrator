# LinkedIn Draft — Testing Agentic Systems: Four Bugs That Almost Made It to Production

**Status:** Draft (Block C complete — publish after all tests pass)
**Target:** LinkedIn `[LI]`
**Hook:** Why an untested orchestration core is a liability — the four bugs, what each could have caused, how I closed them.

---

## Draft Post

I spent a week writing tests for an agentic orchestration framework I built — and found four bugs I hadn't known were there.

Not edge cases. Not obscure race conditions. Four bugs that would have caused real production failures, none of which showed up during development.

Here's what they were:

---

**Bug 1: The existence check that always crashed**

I had a method for checking whether a record exists before creating a new one. It was using an old SQLAlchemy API removed in version 2. Every call to `exists()` raised an `AttributeError` — not "record not found," just a crash.

In production: any deduplication check would fail silently or return a 500. Depending on how it was caught, you'd get duplicate processing or an unexplained server error.

---

**Bug 2: The ghost row**

My API endpoint committed the database row first, then enqueued the background task. If the message queue was unavailable at that moment — Redis blip, deploy restart, anything — the row was committed and the task was never created.

In production: the HTTP request would appear to succeed. Data stored, response returned, no error. But nothing would ever process it. Silent loss with no alert, no audit trail, no retry path.

This is the kind of bug that's invisible until a user asks "wait, where did my request go?"

---

**Bug 3: Every import was a connection attempt**

The database engine and the task queue client were both initialized at module import time. So importing any module that touched the database would immediately try to open a live connection — even if you were just running a unit test.

In production: any cold start, restart, or test run without live infrastructure would fail at import with a connection timeout, not a clear error. The feedback loop on every deploy gets a second or two slower. In tests, the whole suite fails without explaining why.

---

**Bug 4: Routing failures with no context**

Router nodes looked up previous node outputs by hard-coded string keys. If the key was missing — wrong workflow ordering, renamed node, anything — you got a raw `KeyError` with the node name and nothing else.

In production: one misorder in the workflow schema would produce an opaque error with no indication of which router needed it, what workflow was running, or which nodes had actually completed. You'd be reading graph traversal code from scratch every time.

---

None of these showed up during development because I was testing with real infrastructure and happy paths only.

Writing targeted unit tests — the kind that use in-memory databases, mock the message queue, and deliberately trigger the failure cases — surfaced all four immediately.

The lesson isn't "write more tests." It's more specific than that: **infrastructure bugs in agentic systems don't announce themselves.** A hallucination is visible. A ghost row isn't. A routing miss during a quiet traffic period isn't. The only way to see them before your users do is to build the scaffolding that makes the unhappy paths easy to probe.

The four fixes took less time than the four bugs would have cost.

---

What does your testing strategy look like for agentic pipelines?

---

## Post Notes

- Word count: ~430
- Tone: personal, specific, educational — no company names, subject-on-you throughout
- The four bugs map exactly to the Block C known-bugs table in CLAUDE.md
- CTA is open-ended to invite replies without being salesy
- Can pair with a carousel post if engagement warrants deeper treatment
- Related longer-form piece queued: "Testing Agentic Systems: What's Actually Worth Testing (and What Isn't)" — see BLOG_IDEAS.md
