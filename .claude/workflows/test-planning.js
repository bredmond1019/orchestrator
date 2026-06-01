
export const meta = {
  name: 'test-planning',
  description: 'Review codebase across multiple dimensions and produce a test-writing plan',
  whenToUse: 'Run against any Python project to audit subsystems, identify missing tests, and generate a prioritized test plan with detailed specs. Pass a list of subsystems via args, or edit SUBSYSTEMS inline for the target project.',
  phases: [
    { title: 'Explore', detail: 'Parallel agents read each subsystem' },
    { title: 'Analyze', detail: 'Synthesize coverage gaps and test needs' },
    { title: 'Plan', detail: 'Produce a structured test plan document' },
  ],
}

// ─── Phase 1: Parallel codebase exploration ───────────────────────────────────
phase('Explore')

const SUBSYSTEMS = [
  {
    key: 'core',
    label: 'Core framework (workflow/task/schema/nodes)',
    files: [
      'app/core/workflow.py',
      'app/core/task.py',
      'app/core/schema.py',
      'app/core/validate.py',
      'app/core/nodes/base.py',
      'app/core/nodes/agent.py',
      'app/core/nodes/router.py',
      'app/core/nodes/parallel.py',
      'app/core/commands/init_workflow.py',
    ],
  },
  {
    key: 'api',
    label: 'API layer (endpoints/router)',
    files: [
      'app/api/endpoint.py',
      'app/api/router.py',
      'app/main.py',
    ],
  },
  {
    key: 'database',
    label: 'Database layer (models/repository/session)',
    files: [
      'app/database/event.py',
      'app/database/repository.py',
      'app/database/session.py',
      'app/database/database_utils.py',
    ],
  },
  {
    key: 'workflows',
    label: 'Customer-care workflow and nodes',
    files: [
      'app/workflows/customer_care_workflow.py',
      'app/workflows/workflow_registry.py',
      'app/workflows/customer_care_workflow_nodes/validate_ticket_node.py',
      'app/workflows/customer_care_workflow_nodes/determine_intent_ticket_node.py',
      'app/workflows/customer_care_workflow_nodes/ticket_router_node.py',
      'app/workflows/customer_care_workflow_nodes/filter_spam.py',
      'app/workflows/customer_care_workflow_nodes/analyze_ticket_node.py',
      'app/workflows/customer_care_workflow_nodes/generate_response_node.py',
      'app/workflows/customer_care_workflow_nodes/send_reply_node.py',
      'app/workflows/customer_care_workflow_nodes/escalate_ticket_node.py',
      'app/workflows/customer_care_workflow_nodes/close_ticket_node.py',
      'app/workflows/customer_care_workflow_nodes/process_invoice_node.py',
    ],
  },
  {
    key: 'worker',
    label: 'Worker / Celery tasks',
    files: [
      'app/worker/tasks.py',
      'app/worker/config.py',
    ],
  },
  {
    key: 'services',
    label: 'Services and schemas',
    files: [
      'app/services/prompt_loader.py',
      'app/schemas/customer_care_schema.py',
    ],
  },
]

const SUBSYSTEM_SCHEMA = {
  type: 'object',
  required: ['key', 'summary', 'public_interface', 'logic_branches', 'external_deps', 'existing_tests', 'testability_notes'],
  properties: {
    key: { type: 'string' },
    summary: { type: 'string', description: 'What this subsystem does in 2-3 sentences' },
    public_interface: {
      type: 'array',
      items: { type: 'string' },
      description: 'List of public classes/functions/endpoints that callers depend on',
    },
    logic_branches: {
      type: 'array',
      items: { type: 'string' },
      description: 'Meaningful conditional paths, state transitions, or business rules',
    },
    external_deps: {
      type: 'array',
      items: { type: 'string' },
      description: 'External dependencies (DB, LLM, Celery, HTTP, etc.) that need mocking',
    },
    existing_tests: {
      type: 'array',
      items: { type: 'string' },
      description: 'Any existing test files or test functions found',
    },
    testability_notes: {
      type: 'string',
      description: 'Obstacles or design notes that affect how tests should be structured',
    },
  },
}

const explorations = await parallel(
  SUBSYSTEMS.map(sub => () =>
    agent(
      `You are a senior Python test engineer auditing the "${sub.label}" subsystem of a FastAPI + Celery agentic workflow application.

Read the following files from the project at /Users/brandon/Dev/ai-event-quickstart:
${sub.files.map(f => `  - ${f}`).join('\n')}

Then fill in the structured output:
- summary: What this subsystem does
- public_interface: Every public class, function, or HTTP endpoint a caller would depend on
- logic_branches: Every meaningful conditional path, routing decision, retry/error path, or business rule
- external_deps: Every external dependency (database, LLM API, Celery, Redis, HTTP calls) that tests would need to mock or stub
- existing_tests: Any test files or test functions you find in or near these files (check for test_*.py or *_test.py)
- testability_notes: Any design patterns that make testing hard (e.g., tight coupling, global state, no dependency injection)

Be specific — name actual function names, class names, route paths, and branch conditions from the real code. Do not guess; only report what you observe.`,
      { label: `explore:${sub.key}`, phase: 'Explore', schema: SUBSYSTEM_SCHEMA }
    ).then(result => ({ ...result, key: sub.key, label: sub.label }))
  )
)

const validExplorations = explorations.filter(Boolean)
log(`Explored ${validExplorations.length}/${SUBSYSTEMS.length} subsystems`)

// ─── Phase 2: Coverage gap analysis ───────────────────────────────────────────
phase('Analyze')

const GAP_SCHEMA = {
  type: 'object',
  required: ['subsystem_key', 'unit_tests', 'integration_tests', 'e2e_tests', 'priority'],
  properties: {
    subsystem_key: { type: 'string' },
    unit_tests: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'description', 'what_to_mock', 'why_important'],
        properties: {
          name: { type: 'string', description: 'Short test name like test_router_routes_spam_to_filter' },
          description: { type: 'string' },
          what_to_mock: { type: 'array', items: { type: 'string' } },
          why_important: { type: 'string' },
        },
      },
    },
    integration_tests: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'description', 'components_involved', 'why_important'],
        properties: {
          name: { type: 'string' },
          description: { type: 'string' },
          components_involved: { type: 'array', items: { type: 'string' } },
          why_important: { type: 'string' },
        },
      },
    },
    e2e_tests: {
      type: 'array',
      items: {
        type: 'object',
        required: ['name', 'description', 'why_important'],
        properties: {
          name: { type: 'string' },
          description: { type: 'string' },
          why_important: { type: 'string' },
        },
      },
    },
    priority: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
  },
}

const gapAnalyses = await pipeline(
  validExplorations,
  sub =>
    agent(
      `You are a senior Python test engineer. Based on the following audit of the "${sub.label}" subsystem, identify every test that is MISSING.

SUBSYSTEM AUDIT:
${JSON.stringify(sub, null, 2)}

For each missing test, classify it as:
- unit_tests: Tests a single function/class in isolation with mocked dependencies
- integration_tests: Tests 2+ components working together (e.g., API + DB, workflow + node)
- e2e_tests: Tests a complete user-facing flow end-to-end (e.g., POST /event → full workflow → DB record)

Rules:
1. Only list tests that are MISSING — if existing_tests shows it's covered, skip it.
2. Name each test with pytest naming convention (test_<what>_<condition>_<expected>).
3. For unit tests, list exactly what needs to be mocked (class/function names from the actual code).
4. Assign the subsystem a priority: critical (core logic with no tests), high (tested but with major gaps), medium (partial coverage), low (mostly covered).
5. Be specific — reference actual function names, classes, and conditions you observed in the audit.`,
      { label: `gaps:${sub.key}`, phase: 'Analyze', schema: GAP_SCHEMA }
    )
)

const validGaps = gapAnalyses.filter(Boolean)
log(`Gap analysis complete for ${validGaps.length} subsystems`)

// ─── Phase 3: Synthesize into a test plan document ────────────────────────────
phase('Plan')

const plan = await agent(
  `You are a senior Python test architect. Below are the results of a codebase audit and gap analysis for an AI event-processing application built with FastAPI, Celery, SQLAlchemy, and Claude LLM workflows.

EXPLORATION RESULTS (what each subsystem does):
${JSON.stringify(validExplorations, null, 2)}

GAP ANALYSIS (what tests are missing):
${JSON.stringify(validGaps, null, 2)}

Produce a comprehensive, actionable test plan in well-structured Markdown. The plan must include:

1. **Executive Summary** — current state of test coverage, biggest risks, overall recommendation.

2. **Test Infrastructure Requirements** — what pytest plugins, fixtures, factories, and test helpers need to be created before any tests can be written (e.g., pytest-asyncio, httpx TestClient, SQLite in-memory DB fixture, Celery test config, mock LLM fixture).

3. **Recommended Test File Structure** — a directory tree showing where each test file should live (tests/unit/, tests/integration/, tests/e2e/).

4. **Prioritized Test Backlog** — a table grouped by priority (Critical → Low), with columns:
   | Priority | Test Name | Subsystem | Type | What It Verifies |

5. **Detailed Test Specifications** for each CRITICAL and HIGH priority test — enough detail that a developer could write the test without reading the source code themselves. Include:
   - Arrange: what state/fixtures to set up
   - Act: what to call
   - Assert: what to check
   - Mocks: what to patch and with what values

6. **Suggested Implementation Order** — numbered phases (e.g., "Phase 1: Test infrastructure; Phase 2: Core unit tests; ...") with rationale.

7. **Estimated Test Count Summary** — a table:
   | Subsystem | Unit | Integration | E2E | Total |

Be concrete. Use the actual function and class names from the audit. Do not invent abstractions — only reference things that exist in the codebase.`,
  { label: 'synthesize-plan', phase: 'Plan' }
)

return { plan, explorationCount: validExplorations.length, gapCount: validGaps.length }
