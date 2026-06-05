export const meta = {
  name: 'brain2-milestone',
  description: 'Build one Brain2 backend milestone end-to-end: TDD build, parallel review, triage, fix',
  whenToUse: 'Driving a single milestone of the Brain2 backend from docs/spec.md',
  phases: [
    { title: 'Build', detail: 'TDD implementation of the milestone deliverables' },
    { title: 'Review', detail: '3 parallel lenses: correctness, edge-cases, SOLID/simplicity' },
    { title: 'Triage', detail: 'dedup findings, drop over-engineering, keep actionable' },
    { title: 'Fix', detail: 'apply actionable findings, re-run tests' },
  ],
}

// ----- args: the milestone definition (passed via Workflow `args`) -----
const m = typeof args === 'string' ? JSON.parse(args) : args
if (!m || !m.number) throw new Error('args must be a milestone object with a `number`')

const SHARED_CONTEXT = `
You are working on **Brain2**, an open-source personal memory store. The full, authoritative
product spec is at docs/spec.md and repo conventions are in AGENTS.md (READ BOTH as needed).
The Python + FastAPI backend lives under backend/ and is managed with **uv** (Python pinned to 3.12).

Repo coding standards (from AGENTS.md) you MUST honor:
- Clean, modular, DRY, YAGNI, SOLID. No speculative features. No over-engineering.
- Meaningful names, small focused modules, comments only where they add clarity.
- Do NOT delete unrelated files/code. Backend secrets (GEMINI_API_KEY, GOOGLE_CLIENT_ID/SECRET)
  live in the repo-root .env (gitignored) — read via config, never hardcode, never commit them.

External services are built behind provider interfaces (dependency inversion) with fake/stub
implementations so logic stays unit-testable WITHOUT live API keys. Real keys are read from env
when present. Milestones 1-2 need NO external calls at all.
`

// ---------------- Schemas ----------------
const BUILD_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['summary', 'filesCreated', 'filesModified', 'testsAdded', 'testCommand', 'testStatus', 'deviations'],
  properties: {
    summary: { type: 'string', description: 'What was implemented this milestone' },
    filesCreated: { type: 'array', items: { type: 'string' } },
    filesModified: { type: 'array', items: { type: 'string' } },
    testsAdded: { type: 'array', items: { type: 'string' }, description: 'Test names/files added' },
    testCommand: { type: 'string', description: 'Exact command to run the tests' },
    testStatus: { type: 'string', enum: ['all_pass', 'some_fail', 'not_run'] },
    testOutputTail: { type: 'string', description: 'Last ~20 lines of the test run output' },
    deviations: { type: 'array', items: { type: 'string' }, description: 'Where you deviated from spec/plan and why' },
    followups: { type: 'array', items: { type: 'string' }, description: 'Things intentionally left for a later milestone' },
  },
}

const FINDINGS_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['severity', 'title', 'location', 'problem', 'suggestion', 'confidence'],
        properties: {
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
          title: { type: 'string' },
          location: { type: 'string', description: 'file:line or function' },
          problem: { type: 'string' },
          suggestion: { type: 'string' },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
        },
      },
    },
  },
}

const TRIAGE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['actionable', 'rejected'],
  properties: {
    actionable: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'location', 'problem', 'fix', 'severity'],
        properties: {
          title: { type: 'string' },
          location: { type: 'string' },
          problem: { type: 'string' },
          fix: { type: 'string', description: 'Concrete change to make' },
          severity: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
        },
      },
    },
    rejected: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'reason'],
        properties: { title: { type: 'string' }, reason: { type: 'string' } },
      },
    },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['applied', 'testStatus'],
  properties: {
    applied: { type: 'array', items: { type: 'string' } },
    skipped: { type: 'array', items: { type: 'string' } },
    testStatus: { type: 'string', enum: ['all_pass', 'some_fail', 'not_run'] },
    testOutputTail: { type: 'string' },
    notes: { type: 'string' },
  },
}

// ---------------- Phase 1: Build (TDD) ----------------
phase('Build')
const deliverables = (m.deliverables || []).map((d, i) => `  ${i + 1}. ${d}`).join('\n')
const skillRefs = (m.skillRefs || []).map(s => `  - ${s}`).join('\n') || '  (none required this milestone)'

const build = await agent(
  `${SHARED_CONTEXT}

# Milestone ${m.number}: ${m.title}

## Goal
${m.goal}

## Deliverables (implement ALL)
${deliverables}

## Relevant spec sections
${(m.specSections || []).join(', ') || 'see docs/spec.md'}

## Skill references to READ before coding (they hold the current best-practice API)
${skillRefs}

## Build notes / constraints
${m.buildNotes || '(none)'}

## How to work — TEST-DRIVEN DEVELOPMENT (non-negotiable)
1. Read docs/spec.md (the sections above), AGENTS.md, and backend/ARCHITECTURE.md if it exists.
   Read the listed skill reference files. For library specifics (MCP SDK, google-genai,
   sqlite-vec, FastAPI), use the context7 MCP docs tools (resolve-library-id then query-docs)
   rather than guessing from memory.
2. For each behavior: write a failing pytest test FIRST, run it, watch it fail for the right
   reason, then write the MINIMAL code to pass. Repeat. Do not write production code before its test.
3. Keep modules small and single-responsibility. Put external-service calls behind interfaces with
   fakes so tests never need live keys. Do not over-engineer beyond the deliverables (YAGNI).
4. Run the FULL test suite at the end with: \`cd backend && uv run pytest -q\`. It MUST be green.
5. If you created/changed the backend's directory layout, update backend/ARCHITECTURE.md so later
   milestones stay coherent. If you changed tech stack / scripts / structure, update AGENTS.md.

Return the structured build report. Be honest about testStatus — if anything fails, say some_fail
and include the failing output tail.`,
  { label: `build:M${m.number}`, phase: 'Build', schema: BUILD_SCHEMA },
)

// ---------------- Phase 2: Review (3 parallel lenses) ----------------
phase('Review')
const LENSES = [
  {
    key: 'correctness',
    prompt: `Hunt for CORRECTNESS BUGS in the milestone ${m.number} changes (run \`git diff main...HEAD\` or
\`git diff\` to see them). Focus: logic errors, wrong SQL, broken async, race conditions in the worker
queue, mishandled None/empty, off-by-one, incorrect URL normalization, dedup/upsert mistakes, wrong
status transitions, transactions left uncommitted, resource leaks (unclosed DB connections). Verify
claims against docs/spec.md. Only report real bugs you can point to in the code.`,
  },
  {
    key: 'edge-cases',
    prompt: `Hunt for EDGE CASES and ROBUSTNESS gaps in the milestone ${m.number} changes (see \`git diff\`).
Focus: malformed/missing URLs, huge inputs, unicode, missing fields, duplicate saves, concurrent
writes to the same per-user DB, WAL/locking, retry-ceiling boundaries, empty search queries, FTS5
special characters, sqlite-vec dimension mismatches, partial failures mid-pipeline. For each gap,
state the concrete input that breaks it. Check error messages are actionable.`,
  },
  {
    key: 'solid-simplicity',
    prompt: `Review the milestone ${m.number} changes (see \`git diff\`) for SOLID adherence AND for
OVER-ENGINEERING. Two-sided: flag genuine SRP/DIP/ISP violations, tight coupling, duplication (DRY),
leaky abstractions — BUT ALSO flag speculative generality, premature abstraction, unused params,
config knobs nothing uses, and anything beyond the milestone's deliverables (YAGNI). The bar is
"clean and maintainable without gold-plating". Be specific with file:line.`,
  },
]

const reviews = await parallel(
  LENSES.map(l => () =>
    agent(
      `${SHARED_CONTEXT}\n\nYou are a code reviewer. ${l.prompt}\n\nReturn structured findings. If you find nothing real, return an empty findings array — do NOT invent issues.`,
      { label: `review:${l.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
    ),
  ),
)
const allFindings = reviews.filter(Boolean).flatMap(r => r.findings || [])

// ---------------- Phase 3: Triage ----------------
phase('Triage')
let triage = { actionable: [], rejected: [] }
if (allFindings.length > 0) {
  triage = await agent(
    `${SHARED_CONTEXT}

Three reviewers examined the milestone ${m.number} changes. Here are their raw findings as JSON:

${JSON.stringify(allFindings, null, 2)}

Inspect the actual code (\`git diff\`, Read files) to VERIFY each finding is real. Then produce a
triaged list:
- actionable: real, in-scope problems worth fixing now (true bugs, real edge cases, real SOLID
  violations). Merge duplicates. Give a concrete fix for each.
- rejected: false positives, out-of-scope-for-this-milestone items, and OVER-ENGINEERING suggestions
  that would violate YAGNI — with the reason.

Be ruthless about not gold-plating. A suggestion to add abstraction/config/flexibility that nothing
currently needs belongs in rejected. Return the structured triage.`,
    { label: `triage:M${m.number}`, phase: 'Triage', schema: TRIAGE_SCHEMA },
  )
}

// ---------------- Phase 4: Fix ----------------
phase('Fix')
let fix = { applied: [], skipped: [], testStatus: build.testStatus, notes: 'No actionable findings; nothing to fix.' }
if (triage.actionable && triage.actionable.length > 0) {
  fix = await agent(
    `${SHARED_CONTEXT}

Apply these triaged, actionable fixes to the milestone ${m.number} code:

${JSON.stringify(triage.actionable, null, 2)}

Rules:
- For any behavior change, follow TDD: add/adjust a failing test first, then fix.
- Make the minimal change that resolves each item. Do not introduce new abstractions beyond what
  the fix needs.
- After applying, run \`cd backend && uv run pytest -q\` and ensure it is fully green.
Return the structured fix report with the final testStatus and output tail.`,
    { label: `fix:M${m.number}`, phase: 'Fix', schema: FIX_SCHEMA },
  )
}

// ---------------- Report ----------------
log(`Milestone ${m.number} done — build:${build.testStatus}, findings:${allFindings.length}, actionable:${triage.actionable.length}, fix:${fix.testStatus}`)
return {
  milestone: m.number,
  title: m.title,
  build,
  reviewFindingCount: allFindings.length,
  triage,
  fix,
  finalTestStatus: fix.testStatus,
}
