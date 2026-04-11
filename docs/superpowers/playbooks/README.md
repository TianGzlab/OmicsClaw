# Workflow Playbooks

These playbooks are the OmicsClaw repository equivalent of the workflow skills
used in the `feishu_agent` project. They are documentation-based workflow
contracts for AI coding agents and maintainers to consult on demand.

Each playbook should be read as a real operating constraint, not as a loose
"best practice" note. The minimum bar for each one is:

- a core principle
- an iron law or blocking gate
- when to use it
- when not to use it
- red flags and common failure modes
- required outputs or evidence

## Available Playbooks

- [skill_systematic_debugging.md](skill_systematic_debugging.md) —
  reproduce-first debugging and root-cause isolation
- [skill_test_driven_development.md](skill_test_driven_development.md) —
  test-first implementation and regression coverage
- [skill_verification_before_completion.md](skill_verification_before_completion.md) —
  completion checks before claiming success
- [skill_writing_plans.md](skill_writing_plans.md) —
  when and how to write durable execution plans
- [skill_dispatching_parallel_agents.md](skill_dispatching_parallel_agents.md) —
  safe parallelization of independent subtasks
- [skill_requesting_code_review.md](skill_requesting_code_review.md) —
  focused review for bugs, regressions, and test gaps
- [skill_finishing_a_development_branch.md](skill_finishing_a_development_branch.md) —
  final branch hygiene before handoff or merge

## Usage

- Read the matching playbook before doing that kind of work.
- Follow the playbook only as far as it fits the current task; do not add
  process overhead to simple changes.
- For complex work, chain playbooks rather than treating them as isolated:
  planning -> TDD/debugging -> verification -> review -> branch completion.
- Update `README.md` when a playbook-guided task results in an important
  repository decision or milestone.
