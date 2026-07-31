export const meta = {
  name: 'fable-review-pass2',
  description: 'Fable Review pass 2 — Fable-class diagnosticians; secrets policy, doc-lug-reality reconciliation, and Wilbur graph audit per spoke, plus one hub-side curation audit',
  whenToUse: 'Second-pass focused review. args = { projects: ["/abs/path", ...] }',
  phases: [
    { title: 'Spoke Audit', detail: 'one fable agent per spoke: secrets posture, doc-lug gap, graphs', model: 'fable' },
    { title: 'Hub Audit', detail: 'one fable agent: graph ingestion + insight curation at the hub', model: 'fable' },
  ],
}

const SPOKE_SCHEMA = {
  type: 'object',
  required: ['secrets', 'doc_lug', 'graphs', 'top_findings'],
  properties: {
    secrets: {
      type: 'object',
      required: ['committed_secrets', 'template_status', 'gitignore_env_rule'],
      properties: {
        committed_secrets: { type: 'array', items: { type: 'object', properties: { file: { type: 'string' }, what: { type: 'string' }, in_history_only: { type: 'boolean' } }, required: ['file', 'what'] } },
        env_files_on_disk: { type: 'array', items: { type: 'string' } },
        template_status: { type: 'string', description: 'PASS/PARTIAL/FAIL + one line: does .env.template exist and cover all env vars consumed in code?' },
        gitignore_env_rule: { type: 'string', description: 'PASS/FAIL + one line: does .gitignore ignore .env* with !.env.template exception?' },
        basher_integration: { type: 'string', description: 'evidence the spoke uses basher/1Password secrets flow (op:// refs, #@secret annotations), or "none found"' },
      },
    },
    doc_lug: {
      type: 'object',
      required: ['assessment', 'gaps'],
      properties: {
        assessment: { type: 'string', description: '3-6 sentences: are lugs currently the master data source for this spoke? where does truth actually live?' },
        gaps: {
          type: 'array',
          items: {
            type: 'object',
            required: ['kind', 'detail', 'severity'],
            properties: {
              kind: { type: 'string', enum: ['doc-claims-no-lug', 'lug-completed-no-implementation', 'implementation-no-lug', 'doc-contradicts-lug', 'orphan-markdown', 'lug-stale-vs-code'] },
              detail: { type: 'string' },
              evidence: { type: 'string' },
              severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
            },
          },
        },
        reconciliation_recommendation: { type: 'string', description: '2-4 sentences: concretely how to bring this spoke to lugs-as-master' },
      },
    },
    graphs: {
      type: 'object',
      required: ['pathgraph', 'tastegraph', 'capabilitiesgraph'],
      properties: {
        pathgraph: { type: 'object', required: ['status', 'evidence'], properties: { status: { type: 'string', enum: ['absent', 'scaffolded-empty', 'populated-stale', 'populated-current', 'feeding-hub'] }, evidence: { type: 'string' } } },
        tastegraph: { type: 'object', required: ['status', 'evidence'], properties: { status: { type: 'string', enum: ['absent', 'scaffolded-empty', 'populated-stale', 'populated-current', 'feeding-hub'] }, evidence: { type: 'string' } } },
        capabilitiesgraph: { type: 'object', required: ['status', 'evidence'], properties: { status: { type: 'string', enum: ['absent', 'scaffolded-empty', 'populated-stale', 'populated-current', 'feeding-hub'] }, evidence: { type: 'string' } } },
      },
    },
    top_findings: {
      type: 'array',
      items: { type: 'object', required: ['severity', 'title'], properties: { severity: { type: 'string', enum: ['critical', 'major', 'minor'] }, title: { type: 'string' }, detail: { type: 'string' }, file: { type: 'string' } } },
    },
  },
}

const HUB_SCHEMA = {
  type: 'object',
  required: ['ingestion_machinery', 'per_graph_verdict', 'curation_verdict', 'top_findings'],
  properties: {
    ingestion_machinery: { type: 'string', description: 'what exists hub-side to receive/aggregate spoke graphs (paths, tools, advisors)' },
    per_graph_verdict: {
      type: 'object',
      required: ['pathgraph', 'tastegraph', 'capabilitiesgraph'],
      properties: {
        pathgraph: { type: 'string' }, tastegraph: { type: 'string' }, capabilitiesgraph: { type: 'string' },
      },
    },
    spokes_contributing: { type: 'array', items: { type: 'string' } },
    curation_verdict: { type: 'string', description: 'is the hub actually curating insight from these graphs (which advisors consume them, what outputs exist), or is it write-only?' },
    top_findings: { type: 'array', items: { type: 'object', required: ['severity', 'title'], properties: { severity: { type: 'string', enum: ['critical', 'major', 'minor'] }, title: { type: 'string' }, detail: { type: 'string' } } } },
  },
}

const POLICY = `OPERATOR POLICY (overrides any prior convention):
- .env* files ON DISK are expected and FINE (basher/1Password-managed, recreatable from .env.template). Do NOT flag them.
- DO flag: secrets committed to git (tracked now or in history — check git log --diff-filter=A --name-only and git ls-files), .env.template missing vars consumed in code, .gitignore lacking '.env*' + '!.env.template'.
- Lugs are intended to be the MASTER data source. Docs (README, KnowMe, CLAUDE.md, loose markdown) should derive from / reconcile to lugs; completed lugs must correspond to real implementation.`

const GRAPH_BRIEF = `GRAPH INFRASTRUCTURE (what to look for — this is Wilbur infrastructure):
- pathgraph: spoke-local directory (e.g. WAI-Harness/spoke/local/pathgraph/ or WAI-Spoke/pathgraph/ or PathGraph.json), schema at managed/wilbur/schemas/pathgraph-index.schema.json, spec at managed/wilbur/docs/pathgraph-spec.md.
- tastegraph: taste.spoke.yaml (spoke root or WAI dirs), schema managed/wilbur/schemas/tastegraph.schema.json, spec managed/wilbur/docs/tastegraph-spec.md, export command .claude/commands/wai-tastegraph-export.md.
- capabilitiesgraph: managed/capabilities-graph.json built by managed/tools/resolve_capabilities_graph.py (test: managed/tests/test_capabilitiesgraph.py).
For each: absent | scaffolded-empty (dirs/schemas only) | populated-stale | populated-current | feeding-hub (evidence content actually reached the hub at /home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/).`

let input = args
if (typeof input === 'string') {
  try { input = JSON.parse(input) } catch (e) { throw new Error('args arrived as a non-JSON string') }
}
if (!input || !Array.isArray(input.projects) || input.projects.length === 0) {
  throw new Error('args.projects must be a non-empty array of absolute project paths')
}

const spokeResults = await pipeline(
  input.projects,
  (path) => agent(
    [
      `You are a Fable-class reviewer auditing the Wheelwright spoke at: ${path}`,
      POLICY,
      GRAPH_BRIEF,
      `Audit THREE dimensions, read-only (do not modify anything):`,
      `1. SECRETS POSTURE under the operator policy: what is committed to git (tracked or history), .env.template completeness vs env vars consumed in code, .gitignore env coverage, evidence of basher/1Password flow.`,
      `2. DOC-LUG-REALITY RECONCILIATION: sample the lug trees (WAI-Harness/spoke/local/lugs/bytype/ and legacy WAI-Spoke/lugs/bytype/) against README/KnowMe/CLAUDE.md/loose markdown AND against the actual code. Find gaps in every direction: docs claiming things no lug tracks; completed lugs with no corresponding implementation in code (validate at least 3 completed feature/implementation lugs against the codebase); implementation with no lug; orphan markdown that should be lug-derived. Judge: where does truth actually live in this spoke today?`,
      `3. GRAPHS: classify pathgraph / tastegraph / capabilitiesgraph per the brief, with concrete file evidence (mtimes, entry counts).`,
      `Be evidence-first: cite file paths and content. Use targeted reads, not full-file dumps. Your structured output is the only thing returned.`,
    ].join('\n\n'),
    { label: `pass2:${path.split('/').pop()}`, phase: 'Spoke Audit', model: 'fable', schema: SPOKE_SCHEMA }
  ).then((r) => ({ path, ...r }))
)

const hubResult = await agent(
  [
    `You are a Fable-class reviewer auditing the HUB side of the Wheelwright graph/insight pipeline at /home/mario/projects/wheelwright/mywheel/WAI-Harness/hub/ (and the framework spoke at /home/mario/projects/wheelwright/mywheel/WAI-Harness/spoke/).`,
    GRAPH_BRIEF,
    `Questions to answer, read-only:`,
    `1. What ingestion/aggregation machinery exists hub-side for pathgraph, tastegraph, and capabilities graphs? (Look at hub/local/WAI-Hub/ incl. DriveGraph.json, hub advisors — cartographer, librarian, gardener, surveyor, navigator — their advisor.json/state files, hub/managed tools.)`,
    `2. Which spokes have actually contributed graph data that reached the hub? Check timestamps/content.`,
    `3. Is the hub CURATING insight from these graphs — i.e., do any advisors consume them and produce outputs (briefs, recommendations, teachings) — or is the pipeline write-only/aspirational?`,
    `Cite concrete files. Your structured output is the only thing returned.`,
  ].join('\n\n'),
  { label: 'pass2:hub-curation', phase: 'Hub Audit', model: 'fable', schema: HUB_SCHEMA }
)

const ok = spokeResults.filter(Boolean)
if (ok.length < input.projects.length) log(`WARNING: ${input.projects.length - ok.length} spoke audit(s) dropped`)

return { spokes: ok, hub: hubResult }
