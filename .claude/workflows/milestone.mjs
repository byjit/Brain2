export const meta = {
  name: 'brain2-milestone',
  description: 'Build one Brain2 backend milestone end-to-end: TDD build, parallel review, triage, fix',
  whenToUse: 'Driving a single milestone of the Brain2 backend from docs/spec.md',
  phases: [
    { title: 'Build', detail: 'TDD implementation of the milestone deliverables' },
    { title: 'Review', detail: '2 parallel lenses: correctness+edge-cases, SOLID/simplicity' },
    { title: 'Triage & Fix', detail: 'one agent verifies/dedups findings then applies fixes' },
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

const TRIAGE_FIX_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['applied', 'rejected', 'testStatus'],
  properties: {
    applied: {
      type: 'array',
      items: { type: 'string' },
      description: 'Fixes applied — each entry says what changed and where (file:line)',
    },
    rejected: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['title', 'reason'],
        properties: { title: { type: 'string' }, reason: { type: 'string' } },
      },
      description: 'Findings deliberately NOT fixed (false positive, out of scope, over-engineering) with the reason',
    },
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
    key: 'correctness-edge-cases',
    prompt: `Hunt for both CORRECTNESS BUGS and EDGE-CASE / ROBUSTNESS gaps in the milestone ${m.number}
changes (run \`git diff main...HEAD\` or \`git diff\` to see them).
Correctness: logic errors, wrong SQL, broken async, race conditions in the worker queue, mishandled
None/empty, off-by-one, incorrect URL normalization, dedup/upsert mistakes, wrong status transitions,
uncommitted transactions, resource leaks (unclosed DB connections), RRF/ranking math errors, vector
dimension handling, tag canonicalization/co-occurrence math.
Edge cases: malformed/missing URLs, huge inputs, unicode, missing fields, duplicate/concurrent saves
to the same per-user DB, WAL/locking, retry-ceiling/backoff boundaries, empty search queries, FTS5
special characters, sqlite-vec dimension mismatches, partial failures mid-pipeline. For each issue,
name the concrete input that breaks it and verify against docs/spec.md. Only report real issues you
can point to in the code; check error messages are actionable.`,
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

const reviewFocus = m.reviewFocus ? `\n\nEXTRA FOCUS THIS MILESTONE: ${m.reviewFocus}` : ''
const reviews = await parallel(
  LENSES.map(l => () =>
    agent(
      `${SHARED_CONTEXT}\n\nYou are a code reviewer. ${l.prompt}${reviewFocus}\n\nReturn structured findings. If you find nothing real, return an empty findings array — do NOT invent issues.`,
      { label: `review:${l.key}`, phase: 'Review', schema: FINDINGS_SCHEMA },
    ),
  ),
)
const allFindings = reviews.filter(Boolean).flatMap(r => r.findings || [])

// ---------------- Phase 3: Triage & Fix (single agent) ----------------
phase('Triage & Fix')
let resolve = { applied: [], rejected: [], testStatus: build.testStatus, notes: 'No findings; nothing to triage or fix.' }
if (allFindings.length > 0) {
  resolve = await agent(
    `${SHARED_CONTEXT}

Two reviewers examined the milestone ${m.number} changes. Here are their raw findings as JSON:

${JSON.stringify(allFindings, null, 2)}

Do BOTH triage and fix in this single pass:

1. TRIAGE — inspect the actual code (\`git diff\`, Read files) to VERIFY each finding is real. Merge
   duplicates. Drop false positives, out-of-scope-for-this-milestone items, and OVER-ENGINEERING
   suggestions that would violate YAGNI — record each dropped item in \`rejected\` with a one-line
   reason. Be ruthless about not gold-plating: abstraction/config/flexibility that nothing currently
   needs belongs in rejected.
2. FIX — for each remaining real, in-scope finding, apply the MINIMAL change. For any behavior change
   follow TDD: add/adjust a failing test first, watch it fail, then fix. Do not introduce abstractions
   beyond what the fix needs. Do NOT delete unrelated files or code.
3. After applying, run \`cd backend && uv run pytest -q\` and ensure it is fully green.

Return the structured report: applied (what changed and where), rejected (with reasons), final
testStatus + output tail.`,
    { label: `triage-fix:M${m.number}`, phase: 'Triage & Fix', schema: TRIAGE_FIX_SCHEMA },
  )
}

// ---------------- Report ----------------
log(`Milestone ${m.number} done — build:${build.testStatus}, findings:${allFindings.length}, applied:${resolve.applied.length}, final:${resolve.testStatus}`)
return {
  milestone: m.number,
  title: m.title,
  build,
  reviewFindingCount: allFindings.length,
  resolve,
  finalTestStatus: resolve.testStatus,
}
