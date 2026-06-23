---
type: Handoff
created: 2026-06-22
---

# Handoff — phase1-projectC complete; projectD is next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why

We are building the Python orchestration framework's Phase 1 workflow portfolio — a sequence of
production-quality AI pipelines (A through H) that demonstrate sellable agentic competence. This
session completed **phase1-projectC** (the Proposal Generator workflow) and did a post-merge test
coverage audit. The next block to start is **phase1-projectD** — Document Q&A + session memory
(RAG), which reinforces a proven Helpscout production pattern and moves us toward the Phase 1
competence checkpoint.

## Completed this session

- **phase1-projectC fully merged** — all 8 tasks shipped via `/sdlc-block`. DAG:
  `CompanyResearchNode → OpportunityIdentifierNode → ProposalWriterNode → ProposalReviewNode →
  ProposalReviewRouterNode → {StorageNode | ReviseNode → StorageNode}`. Composite scoring formula
  in prompt (not Python), dual-language PT/EN, review criteria with pass/revise routing, full
  registry wiring. 549 tests pass, pylint 10.00/10.
- **Manual conflict resolution** — tasks 3–6 all modified the same row in
  `docs/app-architecture-overview.md` (parallel tasks replacing instead of appending); resolved
  additively in sequence. Task 6 also had `storage_node.py` (add/add) and `docs/api-reference.md`
  (TOC renumbering) conflicts — all resolved by hand.
- **Post-merge test coverage audit** — agent review found two real bugs in
  `tests/workflows/test_proposal_review_router.py`:
  - Six test fixtures seeded `ProposalWriterNode` output as a raw dict instead of
    `{"result": raw_dict}` — the framework's actual `update_node` storage format. Tests passed
    silently because agents are mocked, but proved the wrong key contract.
  - Fixed all six, plus added an assertion in `test_revise_reads_writer_and_review_outputs`
    confirming the `"result"` wrapper is present.
- **CLAUDE.md rule 9 added** — documents the `{"result": ...}` wrapper pattern so future agents
  don't repeat this class of mistake (`CLAUDE.md` line 26, rule 9).
- **Uncommitted changes committed** — `CLAUDE.md` and `tests/workflows/test_proposal_review_router.py`
  are staged and ready to commit (not yet committed as of this handoff — do it first thing).

## Remaining work

- **Commit the two open files** — `CLAUDE.md` and `tests/workflows/test_proposal_review_router.py`
  are modified but not committed. Run `/commit` before anything else.
- **Start phase1-projectD** — Document Q&A + session memory (RAG). Spec is in
  `planning/master-plan.md` (Project D section). Run `/sdlc-block phase1-projectD` once the
  spec exists, or `/generate-tasks phase1-projectD` to scaffold it first.
- **Go-public checklist** (`planning/status.md` near the bottom) — still three open items:
  fix `customer_ticket_response.j2` Healthie references, exclude `planning/` from public history,
  update `README.md` test count. Non-blocking for projectD but worth a quick pass before any
  public demo.

## Open questions / choices

- **Medium findings from the coverage audit** — not fixed yet, low urgency:
  - `ProposalReviseNode` and `StorageNode` access `event.company_name` etc. via attribute access
    with no `isinstance(dict)` guard (unlike other nodes). Won't break at runtime given the current
    workflow runner, but the pattern is inconsistent (`proposal_revise_node.py:80–84`,
    `storage_node.py:126–127`).
  - `StorageNode` unit tests use `MagicMock` event rather than real `ProposalGeneratorEventSchema`.
  - No test for the case where `OpportunityIdentifierNode` exists but has no `"brief"` key (the
    `end_turn`-without-tool-submit path — the node handles it gracefully with `.get("brief", {})`
    but there's no test for it).
  These are logged here for awareness; address them before the first live run if desired.
- **api-reference.md missing sections for four Project C nodes** — `OpportunityIdentifierNode`,
  `ProposalReviewNode`, `ProposalReviseNode`, `ProposalReviewRouterNode` have no `##` section in
  `docs/api-reference.md`. `ProposalWriterNode` and `ProposalGenerator StorageNode` do (added in
  tasks 4 and 6). The gap is flagged but intentionally left — these nodes are documented in the
  architecture overview table and the api-reference write is non-trivial. Address before the
  repo goes public or before Project C is used as a reference pattern for Project D.

## Context the next agent needs

- **The `{"result": ...}` key contract (CLAUDE.md rule 9):** every `AgentNode` stores its output
  via `update_node(node_name=..., result=output)` → `task_context.nodes["NodeName"] = {"result": output}`.
  Tests that seed upstream nodes must mirror this. The pattern bit us twice (content pipeline, now
  proposal generator). Rule 9 is the standing reminder.
- **Parallel-task doc conflicts are expected** when multiple tasks update the same table in
  `docs/app-architecture-overview.md`. Each task replaces the predecessor's row rather than
  appending. The fix is a 30-second additive hand-resolution (keep both rows). Not a bug — just a
  known coordination cost of parallel task execution. No need to change the workflow engine for this.
- **Test suite baseline:** 549 passed, 7 skipped. Any projectD work should land at ≥ 549 tests.
- **status.md is current** — phase1-projectC is marked Done; Current focus is phase1-projectD.

## First command after `/prime`

`/commit` — commit the two open files (CLAUDE.md + test_proposal_review_router.py), then start projectD.
