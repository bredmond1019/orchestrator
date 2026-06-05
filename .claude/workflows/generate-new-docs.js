export const meta = {
  name: 'generate-new-docs',
  description: 'Discover project structure, plan docs, generate in parallel, validate each doc against source',
  whenToUse: 'Use on any project type (Rust, Python uv, Node, etc.) to generate a docs/ directory from scratch or rebuild stale docs. For targeted updates to existing docs use /update-docs instead.',
  phases: [
    { title: 'Discover', detail: 'Survey repo, read existing docs and architecture, identify project type' },
    { title: 'Plan', detail: 'Decide which documents to create and what each must cover' },
    { title: 'Generate', detail: 'Write each doc in parallel — agents read source directly' },
    { title: 'Review', detail: 'Validate each doc against source code, surface inaccuracies' },
  ],
}

// ── Schemas ────────────────────────────────────────────────────────────────────

const DISCOVERY_SCHEMA = {
  type: 'object',
  required: ['projectRoot', 'projectType', 'techStack', 'existingDocFiles',
             'keySourceFiles', 'architectureSummary', 'entryPoints',
             'hasReadme', 'hasClaudeMd'],
  properties: {
    projectRoot: {
      type: 'string',
      description: 'Absolute path to the project root (output of pwd)',
    },
    projectType: {
      type: 'string',
      description: 'e.g. rust-cli, rust-lib, python-uv-cli, python-uv-lib, node-cli, node-lib',
    },
    techStack: {
      type: 'array',
      items: { type: 'string' },
      description: 'Key languages, frameworks, and libraries in use',
    },
    existingDocFiles: {
      type: 'array',
      items: { type: 'string' },
      description: 'Absolute paths of any existing docs (docs/*.md, README.md, CLAUDE.md, etc.)',
    },
    keySourceFiles: {
      type: 'array',
      items: { type: 'string' },
      description: 'Absolute paths of the most important source files: entry points, core modules, main types/traits/classes',
    },
    entryPoints: {
      type: 'array',
      items: { type: 'string' },
      description: 'Main entry point files (e.g. src/main.rs, src/main.py, index.ts)',
    },
    hasReadme: { type: 'boolean' },
    hasClaudeMd: { type: 'boolean' },
    architectureSummary: {
      type: 'string',
      description: '3-6 sentences covering: project purpose, key modules, main types/classes, notable design patterns',
    },
  },
}

const DOC_PLAN_SCHEMA = {
  type: 'object',
  required: ['documents', 'updateReadme', 'updateClaudeMd', 'rationale'],
  properties: {
    documents: {
      type: 'array',
      items: {
        type: 'object',
        required: ['outputPath', 'title', 'purpose', 'sourceFilesToRead', 'sections'],
        properties: {
          outputPath: {
            type: 'string',
            description: 'Absolute path for the output .md file under docs/',
          },
          title: {
            type: 'string',
            description: 'Short display title (e.g. "Architecture", "CLI Reference")',
          },
          purpose: {
            type: 'string',
            description: 'One sentence: what this doc is for and who reads it',
          },
          sourceFilesToRead: {
            type: 'array',
            items: { type: 'string' },
            description: 'Absolute paths of source files the writing agent must read before writing',
          },
          sections: {
            type: 'array',
            items: { type: 'string' },
            description: 'Specific top-level section headings the doc must contain (not vague — e.g. "Voice enum and MIDI note assignments", not "Details")',
          },
        },
      },
    },
    updateReadme: {
      type: 'boolean',
      description: 'Whether README.md should get a Documentation section added or refreshed',
    },
    updateClaudeMd: {
      type: 'boolean',
      description: 'Whether CLAUDE.md should get a Documentation section added or refreshed',
    },
    rationale: {
      type: 'string',
      description: 'Why these specific documents were chosen for this project type',
    },
  },
}

const REVIEW_SCHEMA = {
  type: 'object',
  required: ['docFile', 'passed', 'issues', 'summary'],
  properties: {
    docFile: { type: 'string', description: 'Absolute path of the doc reviewed' },
    passed: {
      type: 'boolean',
      description: 'True if no errors found (warnings and suggestions are OK)',
    },
    issues: {
      type: 'array',
      items: {
        type: 'object',
        required: ['severity', 'description'],
        properties: {
          severity: {
            type: 'string',
            enum: ['error', 'warning', 'suggestion'],
            description: 'error=factually wrong, warning=incomplete/misleading, suggestion=minor improvement',
          },
          description: { type: 'string' },
          location: {
            type: 'string',
            description: 'Section heading or approximate location within the doc',
          },
        },
      },
    },
    summary: {
      type: 'string',
      description: 'One or two sentences summarising the review outcome',
    },
  },
}

// ── Phase 1: Discover ─────────────────────────────────────────────────────────

phase('Discover')

const discovery = await agent(`
Survey this project and return a structured discovery object.

Steps to execute IN ORDER:
1. Run: pwd
2. Run: find . -type f | grep -vE '/(target|node_modules|\.git|__pycache__|\.mypy_cache|\.pytest_cache|dist|build|\.venv|venv|planning|docker/volumes|\.claude|playground|alembic/versions)/' | grep -v '\.pyc$' | sort
3. If README.md exists at the project root, read it.
4. If CLAUDE.md exists at the project root, read it.
5. If a docs/ directory exists, list and read any existing .md files in it.
6. Read the top-level manifest file (Cargo.toml, pyproject.toml, package.json, go.mod, etc.).
7. Read the main entry point file(s).
8. Read 2-4 of the most architecturally significant source files to understand
   the core types, modules, and design patterns.

For keySourceFiles: include entry points plus the files that define the most
important types, classes, traits, or functions — the ones a new developer would
need to read first. Include absolute paths only.

For architectureSummary: write 3-6 sentences covering the project's purpose,
key modules or crates, main data types or classes, and any notable design
patterns (e.g. trait-based polymorphism, event-driven, layered architecture).

IMPORTANT notes specific to this repo:
- Files under planning/ are strategy/planning documents, NOT source code. Do NOT
  include them in keySourceFiles or existingDocFiles.
- The file docs/app-architecture-overview.md (if present) IS an existing doc —
  include it in existingDocFiles and read it.
- The three primary entry points are: app/main.py (FastAPI), app/worker/config.py
  (Celery worker), and app/core/commands/init_workflow.py (createworkflow CLI).
- app/workflows/customer_care_workflow* is a frozen reference implementation —
  note this in architectureSummary; it is useful as a code example but is not a
  pattern to extend.
`, {
  label: 'discover',
  schema: DISCOVERY_SCHEMA,
})

log(`Project: ${discovery.projectType} at ${discovery.projectRoot}`)
log(`Stack: ${discovery.techStack.join(', ')}`)
log(`Source files identified: ${discovery.keySourceFiles.length} | Existing docs: ${discovery.existingDocFiles.length}`)

// ── Phase 2: Plan ─────────────────────────────────────────────────────────────

phase('Plan')

const plan = await agent(`
You have surveyed this project. Decide which documentation files to create.

Project root: ${discovery.projectRoot}
Project type: ${discovery.projectType}
Tech stack: ${discovery.techStack.join(', ')}
Architecture: ${discovery.architectureSummary}
Entry points: ${discovery.entryPoints.join(', ')}
Key source files: ${discovery.keySourceFiles.join(', ')}
Existing doc files: ${discovery.existingDocFiles.join(', ') || 'none'}
Has README.md: ${discovery.hasReadme}
Has CLAUDE.md: ${discovery.hasClaudeMd}

Planning rules:
- Every project gets architecture.md unless a thorough one already exists.
- A CLI tool gets cli-reference.md covering every subcommand and flag.
- A library gets api-reference.md covering the public API surface.
- A project with non-obvious dev setup (venv, build steps, test commands) gets development.md.
- A project with config files or environment variables gets configuration.md.
- A project with domain-specific algorithms or data formats gets a domain doc
  (e.g. groove-generation.md, protocol.md, data-model.md).
- Do NOT re-create a doc that already exists and is substantially complete —
  if it is partial or stale, include it to be rewritten.
- Do NOT create docs that duplicate content already well-covered in README.md
  or CLAUDE.md unless they warrant a dedicated reference file.
- Output paths must be absolute paths under ${discovery.projectRoot}/docs/.
- sourceFilesToRead must be absolute paths that actually exist (use the key
  source files list; do not invent paths).
- sections must be specific headings, not vague labels. Bad: "Details".
  Good: "GrooveBackend trait definition", "MIDI note assignments table",
  "Velocity constants and their musical purpose".

Set updateReadme=true if README.md exists but lacks a Documentation section.
Set updateClaudeMd=true if CLAUDE.md exists but lacks a Documentation section.

Additional rules specific to this repo:
- docs/app-architecture-overview.md already exists and is thorough (~280 lines of
  detailed component analysis). Do NOT recreate it as architecture.md or overwrite
  it. The "every project gets architecture.md" rule is satisfied by this file — skip
  it unless the review finds it substantially stale.
- CLAUDE.md already covers in detail: build/test/run commands, the createworkflow
  scaffold workflow, adding a new workflow step-by-step, known bugs, and standing
  rules. Do NOT create a development.md or workflow-creation guide that just
  restates what is already in CLAUDE.md. Cross-reference CLAUDE.md instead.
- NEVER list any file under planning/ as a sourceFilesToRead. Those are strategy
  documents, not source code.
- app/workflows/customer_care_workflow* is frozen reference-only — never the
  subject of a "how to extend" guide. It may appear as a sourceFilesToRead only
  when providing concrete code examples for a general workflow authoring doc.
- The createworkflow CLI (app/core/commands/init_workflow.py) is the primary
  scaffold tool for this project. Any workflow authoring documentation must
  include how to invoke it and what it generates.
- The documented gaps in this repo that are not yet covered by any existing doc:
  (1) A precise class-level API reference for the core engine abstractions
  (Workflow, Node, AgentNode, ParallelNode, RouterNode, TaskContext,
  WorkflowSchema, NodeConfig, WorkflowValidator, PromptManager, GenericRepository)
  that a developer needs when writing a new workflow.
  (2) A configuration reference covering every environment variable (from
  app/.env.example and docker/.env.example), the Docker service topology, and
  how Redis/Postgres connection strings are assembled at runtime.
  Propose docs for these gaps. Keep the total count minimal — 2-3 new docs maximum.
`, {
  label: 'plan',
  schema: DOC_PLAN_SCHEMA,
})

log(`Plan: ${plan.documents.length} docs — ${plan.documents.map(d => d.title).join(', ')}`)
log(`Rationale: ${plan.rationale}`)

// ── Phase 3: Generate ─────────────────────────────────────────────────────────

phase('Generate')

const WRITING_RULES = `
Write clean GitHub-flavored Markdown. No emojis. Use headings, tables, and
code blocks. Be precise and technical. Derive ALL facts from the source files
you read — do not invent API signatures, type names, default values, or behavior.
Use tables for reference material (type fields, CLI flags, config keys).
Show real code excerpts where they clarify the doc.
Do not pad with generic filler — every sentence must help a developer working
in this codebase. Write ONLY the file content using the Write tool.
`

await parallel(plan.documents.map(doc => () => agent(`
${WRITING_RULES}

You are writing: ${doc.title}
Output path: ${doc.outputPath}
Purpose: ${doc.purpose}

First, read each of these source files:
${doc.sourceFilesToRead.map(f => `- ${f}`).join('\n')}

Then write ${doc.outputPath} containing these top-level sections (in this order,
expanding each into full content derived from the source):
${doc.sections.map((s, i) => `${i + 1}. ${s}`).join('\n')}
`, { label: doc.title, phase: 'Generate' })))

// Build a relative-path table for README / CLAUDE index sections
const docTableRows = plan.documents
  .map(d => {
    const rel = d.outputPath.replace(discovery.projectRoot + '/', '')
    return `| [${rel}](${rel}) | ${d.purpose} |`
  })
  .join('\n')

if (plan.updateReadme && discovery.hasReadme) {
  await agent(`
Read ${discovery.projectRoot}/README.md.

Add or update a "## Documentation" section. If it already exists, replace only
the table inside it. If it does not exist, insert it before the last major
section (before "## What's next", "## Contributing", or "## License" if any
of those exist; otherwise append to the end of the file).

The section must be exactly:

## Documentation

| File | Contents |
|---|---|
${docTableRows}

Use the Read and Edit tools.
`, { label: 'update README.md', phase: 'Generate' })
}

if (plan.updateClaudeMd && discovery.hasClaudeMd) {
  await agent(`
Read ${discovery.projectRoot}/CLAUDE.md.

Add or update a "## Documentation" section. If it already exists, replace only
the table inside it. If it does not exist, append it at the very end of the file.

The section must be exactly:

## Documentation

Developer reference docs in \`docs/\`:

| File | Contents |
|---|---|
${docTableRows}

Use the Read and Edit tools.
`, { label: 'update CLAUDE.md', phase: 'Generate' })
}

// ── Phase 4: Review ───────────────────────────────────────────────────────────

phase('Review')

const reviews = (await parallel(plan.documents.map(doc => () => agent(`
You are a technical reviewer. Find inaccuracies by checking the doc against
the source code it describes. Be thorough but fair — flag real problems only,
not stylistic preferences.

Doc to review: ${doc.outputPath}
Source files to check against:
${doc.sourceFilesToRead.map(f => `- ${f}`).join('\n')}

Steps:
1. Read the doc file.
2. Read each source file listed above.
3. For every factual claim in the doc — type names, field names, function
   signatures, CLI flags, default values, step indices, formula constants,
   config keys — verify it matches the source exactly.
4. Check that the required sections are present: ${doc.sections.join(', ')}.
5. Flag anything wrong, missing, or misleading.

Severity:
- error: factually wrong (wrong name, wrong value, nonexistent flag or type)
- warning: incomplete or misleading (important case missing, ambiguous description)
- suggestion: minor improvement (a useful example is absent, phrasing could be clearer)
`, {
  label: `review: ${doc.title}`,
  schema: REVIEW_SCHEMA,
  phase: 'Review',
})))).filter(Boolean)

// Surface errors so the caller can act on them
const errors   = reviews.flatMap(r => r.issues.filter(i => i.severity === 'error'))
const warnings = reviews.flatMap(r => r.issues.filter(i => i.severity === 'warning'))

log(`Review: ${errors.length} errors, ${warnings.length} warnings across ${reviews.length} docs`)

return {
  projectRoot:   discovery.projectRoot,
  projectType:   discovery.projectType,
  docsWritten:   plan.documents.map(d => d.outputPath),
  reviewResults: reviews.map(r => ({
    file:         r.docFile,
    passed:       r.passed,
    errors:       r.issues.filter(i => i.severity === 'error').length,
    warnings:     r.issues.filter(i => i.severity === 'warning').length,
    summary:      r.summary,
  })),
  errors,
}
