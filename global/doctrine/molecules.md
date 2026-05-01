# Molecules — Composed Workflows

## Definition

A **molecule** is a composed workflow that chains multiple **atoms** into a
directed acyclic graph (DAG) of execution steps. Data flows from atom outputs
into subsequent atom inputs via template expressions.

## Why Molecules

Atoms are single-tool wrappers. Molecules are multi-tool workflows — the
difference between a wrench and a power drill. A recon molecule combines
nmap + whatweb + nikto + gobuster into a single invocation, with results
merged into session memory.

## Schema

Molecules share the same card schema as atoms. The difference is in
`implementation.kind` and the presence of a `dag` field:

```yaml
kind: molecule
implementation:
  kind: compose
  dag:
    step_name:
      atom: <atom_id>
      inputs:
        <key>: <template_expression>
      depends_on:
      - <other_step>
```

## DAG Structure

Each step in the DAG has:

| Field | Required | Description |
|-------|----------|-------------|
| atom | Yes | ID of an existing atom (e.g., `kali.nmap`) |
| inputs | No | Step inputs, may contain template expressions |
| depends_on | No | List of step IDs that must complete first |

Steps without `depends_on` run first (root nodes). Steps with dependencies
run after their prerequisites complete (leaf nodes).

## Template Resolution

Molecule steps use two template syntaxes:

| Syntax | Resolves To | Example |
|--------|-------------|---------|
| `{{inputs.X}}` | Molecule input | `{{inputs.target}}` → `"scanme.nmap.org"` |
| `{{steps.X.result}}` | Full JSON string of step output | `{{steps.scan.result}}` → `'{"hosts": [...]}'` |
| `{{steps.X.result.Y}}` | Individual field from step output | `{{steps.scan.result.hosts}}` → `"[{...}]"` |

Template resolution is recursive: dicts and lists are traversed, and all
string values are processed for template expressions.

## Execution Model

1. **Topological Sort**: The DAG is sorted into execution order. Cycles
   cause immediate failure.
2. **Step Resolution**: For each step in order, template expressions are
   resolved against molecule inputs and previous step results.
3. **Atom Dispatch**: Each step dispatches its resolved atom with resolved
   inputs. The atom runs exactly as if dispatched individually.
4. **Result Collection**: Successful step results are stored. On failure,
   the molecule aborts and returns the failure.
5. **Final Output**: The molecule output is the result of the last step
   in the execution order (typically a merge/cleanup step).

## Error Handling

- **DAG Invalid**: Missing step dependency or cycle → immediate failure
- **Atom Not Found**: Referenced atom doesn't exist in CARDS → failure
- **Step Failure**: First failed step aborts the molecule; previous
  steps' results are still collected but the molecule returns failure
- **Timeout**: Per-atom timeouts apply; if a step times out, the
  molecule fails but doesn't roll back completed steps

## Best Practices

### 1. Use a Merge Step as the Last DAG Node

The final step should always be a merge/cleanup atom (e.g.,
`mem.write_session`) that collects all previous results. This ensures:
- The molecule has a clean, structured output
- All data is persisted to session memory
- The last step's result is the molecule's output

### 2. Minimize Parallel Fan-out

Too many parallel branches increase execution time and complexity.
Group related atoms into sub-molecules if the DAG exceeds 6-8 steps.

### 3. Use Distinct Input Variations for Trials

When trialing molecules, use distinct flag combinations to generate
unique `inputs_hash` values. The scope gate strips scheme/port, so
different targets on the same hostname may produce identical hashes.

### 4. Set Appropriate Timeouts

Molecules can be long-running. Set the molecule's `execution.timeout_seconds`
to account for the sum of all step timeouts plus merge overhead.

### 5. Document Side Effects

Molecules may trigger multiple side effects (network probes, file writes).
List all in `side_effects` for the promotion gate.

## Example: Full Recon Molecule

```yaml
id: recon.host.full
implementation:
  kind: compose
  dag:
    nmap_scan:
      atom: kali.nmap
      inputs:
        flags: -sV -Pn -T3
        target: '{{inputs.target}}'
    whatweb_scan:
      atom: web.whatweb
      inputs:
        target: '{{inputs.target}}'
      depends_on:
      - nmap_scan
    nikto_scan:
      atom: web.nikto
      inputs:
        flags: -maxtime 30
        target: '{{inputs.target}}'
      depends_on:
      - nmap_scan
    gobuster_scan:
      atom: web.gobuster
      inputs:
        flags: -f --no-error -q -t 10
        target: '{{inputs.target}}'
      depends_on:
      - nmap_scan
    merge_findings:
      atom: mem.write_session
      inputs:
        path: findings/{{inputs.target}}_recon_full.json
        data:
          molecule: recon.host.full
          target: '{{inputs.target}}'
          nmap: '{{steps.nmap_scan.result}}'
          whatweb: '{{steps.whatweb_scan.result}}'
          nikto: '{{steps.nikto_scan.result}}'
          gobuster: '{{steps.gobuster_scan.result}}'
      depends_on:
      - whatweb_scan
      - nikto_scan
      - gobuster_scan
inputs:
  target:
    required: true
    type: string
kind: molecule
```

This molecule:
1. Runs nmap first (no dependencies)
2. Runs whatweb, nikto, and gobuster in parallel (all depend on nmap)
3. Merges all results into a single JSON file (depends on all three)

## Promotion Criteria

Molecules follow the same promotion gate as atoms:
- `required_success`: Minimum successful trials (default: 3)
- `required_distinct_inputs`: Minimum distinct input combinations (default: 3)
- `requires_human_review`: Whether a human must approve promotion

## Molecule vs Atom

| | Atom | Molecule |
|--|------|----------|
| kind | `shell` or `python` | `compose` |
| implementation | `cmd` or `method` | `dag` |
| execution | Single command | DAG of atoms |
| output | Parsed from stdout | Last step's result |
| artifacts | Single file | Multiple + merged output |
| complexity | Low | Medium-High |

## Ledger

Molecule trials are recorded in `ledger/{molecule_id}.trials.jsonl`,
following the same schema as atom trials. The `result` field contains
the merged output (typically the last step's result).

Each trial entry includes:
- `steps`: List of step IDs that completed successfully
- `result`: The molecule's final output (last step's result)
- `duration_ms`: Total wall-clock time for all steps

## Self-Improvement Loop Integration

The self-improvement loop analyzes molecule trial ledgers just like
atom ledgers. Failures within a molecule's steps are traced to the
specific atom that failed, enabling targeted fixes.

Improvement tickets for molecules should reference the molecule ID
(e.g., `IT-recon.host.full-001`) and identify the failing step.
