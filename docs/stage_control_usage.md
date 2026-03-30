# Stage Control Usage Examples

## Overview

The research pipeline supports fine-grained stage control through two parameters:
- `from_stage`: Start from a specific stage (skip all prior stages)
- `skip_stages`: Skip specific stages entirely

These parameters enable flexible workflows for iterative development and debugging.

## Stage List

The pipeline has 7 stages (in order):
1. `intake` — Parse PDF and assemble context
2. `plan` — Generate experimental plan
3. `research` — Literature search and method discovery
4. `execute` — Run experiments in Jupyter notebook
5. `analyze` — Compute metrics and create visualizations
6. `write` — Draft paper-ready report
7. `review` — Peer-review and revision

## Usage Patterns

### Pattern 1: Start from Middle Stage

**Use case**: You already have a plan and want to jump directly to execution.

```python
from omicsclaw.agents.pipeline import ResearchPipeline
import asyncio

pipeline = ResearchPipeline(workspace_dir="./workspace")

result = asyncio.run(
    pipeline.run(
        idea="Analyze spatial heterogeneity in tumor microenvironment",
        pdf_path="paper.pdf",
        from_stage="execute"  # Skip intake, plan, research
    )
)
```

**What happens**:
- Stages `intake`, `plan`, `research` are marked as completed
- Pipeline starts from `execute` stage
- Requires: `plan.md` must exist in workspace

### Pattern 2: Skip Specific Stages

**Use case**: You don't need literature search for this analysis.

```python
result = asyncio.run(
    pipeline.run(
        idea="Compare two spatial datasets",
        pdf_path="paper.pdf",
        skip_stages=["research"]  # Skip literature search
    )
)
```

**What happens**:
- `research` stage is marked as completed (skipped)
- All other stages run normally
- Planner won't expect research results

### Pattern 3: Skip Multiple Stages

**Use case**: Quick prototype without review loop.

```python
result = asyncio.run(
    pipeline.run(
        idea="Test new deconvolution method",
        pdf_path="paper.pdf",
        skip_stages=["research", "review"]
    )
)
```

**What happens**:
- Pipeline runs: intake → plan → execute → analyze → write
- No literature search, no peer review
- Faster iteration for prototyping

### Pattern 4: Resume from Checkpoint

**Use case**: Pipeline crashed, resume from last checkpoint.

```python
result = asyncio.run(
    pipeline.run(
        idea="Same idea as before",
        pdf_path="paper.pdf",
        resume=True  # Load .pipeline_checkpoint.json
    )
)
```

**What happens**:
- Loads completed stages from `.pipeline_checkpoint.json`
- Skips completed stages
- Continues from next pending stage

## Constraints

### Mutual Exclusivity

`resume` cannot be used with `from_stage` or `skip_stages`:

```python
# ❌ This will raise ValueError
result = asyncio.run(
    pipeline.run(
        idea="test",
        resume=True,
        from_stage="execute"  # Conflict!
    )
)
```

**Reason**: `resume` loads stage state from checkpoint, while `from_stage`/`skip_stages` explicitly set stage state. Use one approach at a time.

### Validation

Invalid stage names raise `ValueError`:

```python
# ❌ This will raise ValueError
result = asyncio.run(
    pipeline.run(
        idea="test",
        from_stage="invalid_stage"
    )
)
```

Valid stage names: `intake`, `plan`, `research`, `execute`, `analyze`, `write`, `review`

## Workspace Requirements

### from_stage Requirements

When using `from_stage`, the workspace must contain artifacts from prior stages:

| from_stage | Required Files |
|------------|----------------|
| `plan` | `01_paper_summary.md` (from intake) |
| `research` | `plan.md` (from plan) |
| `execute` | `plan.md` (from plan) |
| `analyze` | `analysis.ipynb` (from execute) |
| `write` | `analysis_summary.md` (from analyze) |
| `review` | `final_report.md` (from write) |

**Example**: Starting from `execute` requires `plan.md` to exist.

### skip_stages Behavior

Skipped stages don't produce outputs:
- `skip_stages=["research"]` → No literature search results
- `skip_stages=["review"]` → No peer review feedback

The orchestrator adapts its prompts to account for missing stages.

## CLI Integration (Future)

When CLI support is added, the syntax will be:

```bash
# Start from execute stage
python -m omicsclaw.agents.pipeline \
  --idea "Analyze tumor microenvironment" \
  --pdf paper.pdf \
  --from-stage execute

# Skip research stage
python -m omicsclaw.agents.pipeline \
  --idea "Compare datasets" \
  --pdf paper.pdf \
  --skip research

# Skip multiple stages
python -m omicsclaw.agents.pipeline \
  --idea "Quick prototype" \
  --pdf paper.pdf \
  --skip research,review

# Resume from checkpoint
python -m omicsclaw.agents.pipeline \
  --idea "Same as before" \
  --pdf paper.pdf \
  --resume
```

## Debugging Tips

### Check Completed Stages

```python
pipeline = ResearchPipeline(workspace_dir="./workspace")

# Load checkpoint
state = PipelineState.load_checkpoint(Path("./workspace"))
if state:
    print(f"Completed stages: {state.completed_stages}")
    print(f"Current stage: {state.current_stage}")
```

### Verify Workspace Artifacts

```bash
# Check what files exist
ls -la workspace/

# Required for from_stage="execute"
cat workspace/plan.md
```

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now run pipeline
result = asyncio.run(pipeline.run(...))
```

## Common Workflows

### Iterative Plan Refinement

```python
# Run 1: Generate initial plan
result = asyncio.run(
    pipeline.run(idea="...", pdf_path="...", skip_stages=["execute", "analyze", "write", "review"])
)

# Manually edit workspace/plan.md

# Run 2: Execute with refined plan
result = asyncio.run(
    pipeline.run(idea="...", pdf_path="...", from_stage="execute")
)
```

### Quick Experiment Validation

```python
# Skip time-consuming stages for rapid prototyping
result = asyncio.run(
    pipeline.run(
        idea="Test hypothesis",
        pdf_path="paper.pdf",
        skip_stages=["research", "review"]  # Focus on execution
    )
)
```

### Crash Recovery

```python
# Pipeline crashed during execute stage
# Resume from checkpoint
result = asyncio.run(
    pipeline.run(
        idea="Same idea",
        pdf_path="paper.pdf",
        resume=True  # Continues from execute
    )
)
```

## Implementation Details

### Stage Marking

When `from_stage="execute"` is used:
1. Stages `intake`, `plan`, `research` are added to `completed_stages`
2. Their `stage_outputs` are set to `"Skipped (--from-stage=execute)"`
3. Orchestrator receives context: "Already completed: intake, plan, research"

When `skip_stages=["research"]` is used:
1. Stage `research` is added to `completed_stages`
2. Its `stage_outputs` is set to `"Skipped (--skip)"`
3. Orchestrator receives context: "Skipped stages: research"

### Checkpoint Format

`.pipeline_checkpoint.json`:
```json
{
  "current_stage": "execute",
  "completed_stages": ["intake", "plan", "research"],
  "stage_outputs": {
    "intake": "01_paper_summary.md",
    "plan": "plan.md",
    "research": "Skipped (--skip)"
  },
  "review_iterations": 0
}
```

## See Also

- `omicsclaw/agents/pipeline.py` — Implementation
- `tests/test_stage_control.py` — Test suite
- `.env.example` — Configuration options
