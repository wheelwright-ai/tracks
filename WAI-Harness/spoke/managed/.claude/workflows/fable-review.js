export const meta = {
  name: 'fable-review',
  description: 'Fable Project Review Protocol — batch recon + diagnosis fan-out over a list of project paths',
  whenToUse: 'Invoked by /fable-review in REVIEW mode. args = { projects: ["/abs/path", ...], batch: "1 of 5", checklist: "<compliance checklist markdown>" }',
  phases: [
    { title: 'Recon', detail: 'one recon-scout per project (inventory only)', model: 'sonnet' },
    { title: 'Diagnose', detail: 'three dimension-group diagnosticians per project', model: 'sonnet' },
  ],
}

// Orchestrator (main loop) retains: mission assessment, priority judgment,
// cross-project patterns, remediation ordering, report authorship.
// This workflow does only the mechanical extraction.

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['findings', 'compliance'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['category', 'severity', 'effort', 'file', 'issue', 'suggested_action', 'risk'],
        properties: {
          category: { type: 'string', enum: ['codebase', 'git', 'files', 'tests', 'security', 'mission', 'copy-seo', 'docs', 'wheelwright'] },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
          effort: { type: 'string', enum: ['quick-win', 'refactor', 'architectural'] },
          file: { type: 'string' },
          issue: { type: 'string' },
          evidence: { type: 'string' },
          suggested_action: { type: 'string' },
          risk: { type: 'string' },
        },
      },
    },
    compliance: {
      type: 'array',
      items: {
        type: 'object',
        required: ['criterion', 'status', 'finding'],
        properties: {
          criterion: { type: 'string' },
          status: { type: 'string', enum: ['PASS', 'FAIL', 'PARTIAL'] },
          finding: { type: 'string' },
        },
      },
    },
  },
}

const DIMENSION_GROUPS = ['code', 'hygiene', 'intent']

let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (e) { throw new Error('args arrived as a non-JSON string') }
}
if (!input || !Array.isArray(input.projects) || input.projects.length === 0) {
  throw new Error('args.projects must be a non-empty array of absolute project paths')
}
const checklist = input.checklist || '(no checklist provided — mark all wheelwright criteria PARTIAL with note "checklist missing")'

log(`Fable review batch ${input.batch || '?'}: ${input.projects.length} project(s)`)

const results = await pipeline(
  input.projects,
  // Stage 1 — recon manifest (inventory only)
  (path) => agent(
    `Project path: ${path}\nBuild the Phase 1 recon manifest for this project per your instructions. Inventory only.`,
    { label: `recon:${path.split('/').pop()}`, phase: 'Recon', agentType: 'recon-scout' }
  ),
  // Stage 2 — diagnostic battery, three dimension groups in parallel per project
  (manifest, path) => parallel(DIMENSION_GROUPS.map((dim) => () =>
    agent(
      [
        `Project path: ${path}`,
        `DIMENSION GROUP: ${dim}`,
        dim === 'intent' ? `Wheelwright Compliance Checklist:\n${checklist}` : '',
        `Recon manifest:\n${manifest}`,
        `Diagnose only your dimension group. Return structured findings; compliance array must be empty unless your group is "intent".`,
      ].filter(Boolean).join('\n\n'),
      { label: `diag:${dim}:${path.split('/').pop()}`, phase: 'Diagnose', agentType: 'project-diagnostician', schema: FINDINGS_SCHEMA }
    )
  )).then((groups) => {
    const ok = groups.filter(Boolean)
    return {
      path,
      manifest,
      findings: ok.flatMap((g) => g.findings),
      compliance: ok.flatMap((g) => g.compliance),
      dropped_groups: DIMENSION_GROUPS.length - ok.length,
    }
  })
)

const completed = results.filter(Boolean)
const dropped = input.projects.length - completed.length
if (dropped > 0) log(`WARNING: ${dropped} project(s) dropped (agent failure) — list them as OPEN_QUESTIONS in the report`)
for (const r of completed) {
  if (r.dropped_groups > 0) log(`WARNING: ${r.path} lost ${r.dropped_groups} dimension group(s) — coverage incomplete`)
}

return {
  batch: input.batch || null,
  projects_requested: input.projects,
  projects_completed: completed.map((r) => r.path),
  results: completed,
}
