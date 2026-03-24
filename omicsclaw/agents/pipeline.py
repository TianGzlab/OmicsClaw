"""Research pipeline controller — multi-agent orchestration using deepagents.

This is the core module that builds and runs the multi-agent research
pipeline. It uses deepagents' ``create_deep_agent()`` with sub-agents
configured from ``config.yaml``.

The pipeline follows these stages:
    intake → plan → research → execute → analyze → write → review

If the reviewer requests revisions, the pipeline loops back to
the writing (or execution) stage.
"""

from __future__ import annotations

import logging
import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Suppress noisy HTTP logs from Langchain/OpenAI/httpx
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@dataclass
class PipelineState:
    """Tracks pipeline progress across stages."""

    current_stage: str = "intake"
    completed_stages: list[str] = field(default_factory=list)
    stage_outputs: dict[str, str] = field(default_factory=dict)
    review_iterations: int = 0
    max_review_iterations: int = 3
    error: str = ""
    # Graph memory integration (optional)
    memory_client: Any = None

    def record_stage(self, stage: str, output_summary: str = ""):
        """Record a completed stage and optionally persist to memory."""
        if stage not in self.completed_stages:
            self.completed_stages.append(stage)
        self.stage_outputs[stage] = output_summary
        self.current_stage = stage
        logger.info(
            "Stage '%s' completed (%d/%d stages done)",
            stage, len(self.completed_stages), 7,
        )

    def is_stage_done(self, stage: str) -> bool:
        """Check whether a stage has already been completed."""
        return stage in self.completed_stages

    def should_stop_review(self) -> bool:
        """Return True when the review loop should be forcibly terminated."""
        return self.review_iterations >= self.max_review_iterations

    def checkpoint(self, workspace: Path):
        """Write a checkpoint file to workspace for crash recovery."""
        import json
        ckpt = {
            "current_stage": self.current_stage,
            "completed_stages": self.completed_stages,
            "stage_outputs": self.stage_outputs,
            "review_iterations": self.review_iterations,
        }
        ckpt_path = workspace / ".pipeline_checkpoint.json"
        ckpt_path.write_text(json.dumps(ckpt, indent=2), encoding="utf-8")
        logger.debug("Checkpoint saved: %s", ckpt_path)

    @classmethod
    def load_checkpoint(cls, workspace: Path) -> "PipelineState | None":
        """Load a previously saved checkpoint for crash recovery.

        Returns None if no checkpoint exists or it is corrupted.
        """
        import json
        ckpt_path = workspace / ".pipeline_checkpoint.json"
        if not ckpt_path.exists():
            return None
        try:
            data = json.loads(ckpt_path.read_text(encoding="utf-8"))
            state = cls(
                current_stage=data.get("current_stage", "intake"),
                completed_stages=data.get("completed_stages", []),
                stage_outputs=data.get("stage_outputs", {}),
                review_iterations=data.get("review_iterations", 0),
            )
            logger.info(
                "Loaded checkpoint: stages=%s, review_iter=%d",
                state.completed_stages, state.review_iterations,
            )
            return state
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Corrupted checkpoint at %s: %s", ckpt_path, e)
            return None

    async def persist_stage(self, stage: str, output: str):
        """Persist stage output to graph memory if client is available."""
        if self.memory_client is None:
            return
        try:
            await self.memory_client.remember(
                uri=f"session://pipeline/{stage}",
                content=output[:5000],  # Cap content size
                disclosure=f"Output from pipeline stage: {stage}",
            )
        except Exception as e:
            logger.warning(f"Failed to persist stage {stage} to memory: {e}")


def _generate_todos(workspace: Path, mode: str, has_pdf: bool) -> None:
    """Create an initial todos.md in the workspace if it doesn't exist.

    This gives the orchestrator a pre-structured checklist to track
    pipeline progress, reducing the chance it skips stages.
    """
    todos_path = workspace / "todos.md"
    if todos_path.exists():
        return

    stages = [
        ("Intake", "Parse paper/idea, build workspace", True),
        ("Plan", "Generate experiment plan (plan.md)", True),
        ("Research", "Literature review for methods and baselines", True),
        ("Execute", "Run OmicsClaw skills in notebook", True),
        ("Analyze", "Compute metrics, generate plots", True),
        ("Write", "Draft final report (final_report.md)", True),
        ("Review", "Peer review of the report", True),
    ]

    lines = [
        "# Research Pipeline Progress\n",
        f"Mode: {mode} | Paper: {'yes' if has_pdf else 'no'}\n",
        "",
    ]
    for name, desc, _ in stages:
        lines.append(f"- [ ] **{name}** — {desc}")

    lines.extend([
        "",
        "---",
        "*Auto-generated by OmicsClaw intake. "
        "Update this file as stages complete.*",
    ])
    todos_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Created todos.md at %s", todos_path)



# =========================================================================
# Config loading
# =========================================================================


def _load_agent_config() -> dict[str, Any]:
    """Load sub-agent config from config.yaml."""
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_prompt_refs(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve system_prompt_ref → actual prompt text."""
    from .prompts import build_prompt_refs

    refs = build_prompt_refs()
    for agent_name, agent_def in config.items():
        ref = agent_def.get("system_prompt_ref")
        if ref and ref in refs:
            agent_def["system_prompt"] = refs[ref]
            del agent_def["system_prompt_ref"]
    return config


# =========================================================================
# Agent builder
# =========================================================================


def _build_subagent_configs(
    agent_config: dict[str, Any],
    tool_registry: dict,
) -> list[dict[str, Any]]:
    """Convert our YAML config into deepagents subagent format.

    Follows EvoScientist's pattern:
    - Each subagent gets its tools from the registry
    - Each subagent declares skills=['/skills/'] so it can read SKILL.md
    - Each subagent gets ToolErrorHandlerMiddleware for self-recovery

    Parameters
    ----------
    agent_config : dict
        Parsed config.yaml content.
    tool_registry : dict
        Mapping of tool name → tool object.

    Returns
    -------
    list of dicts in deepagents subagent format
    """
    from .middleware import ToolErrorHandlerMiddleware

    subagents = []
    for agent_name, agent_def in agent_config.items():
        tool_names = agent_def.get("tools", [])
        tools = [tool_registry[t] for t in tool_names if t in tool_registry]

        subagent: dict[str, Any] = {
            "name": agent_name,
            "description": agent_def.get("description", ""),
            "tools": tools,
        }
        if "system_prompt" in agent_def:
            subagent["system_prompt"] = agent_def["system_prompt"]

        # EvoScientist pattern: let subagents see /skills/ for SKILL.md
        if "skills" in agent_def:
            subagent["skills"] = agent_def["skills"]
        else:
            subagent["skills"] = ["/skills/"]

        # EvoScientist pattern: inject ToolErrorHandlerMiddleware
        # so tool errors become recoverable ToolMessages instead of crashes
        subagent["middleware"] = [ToolErrorHandlerMiddleware()]

        subagents.append(subagent)
    return subagents


# =========================================================================
# Research Pipeline
# =========================================================================


class ResearchPipeline:
    """Multi-agent research pipeline using deepagents/LangGraph.

    Parameters
    ----------
    workspace_dir : str, optional
        Directory for pipeline workspace. Auto-created if needed.
    provider : str, optional
        LLM provider (uses .env default if empty).
    model : str, optional
        LLM model name override.
    """

    STAGES = [
        "intake", "plan", "research", "execute",
        "analyze", "write", "review",
    ]

    def __init__(
        self,
        workspace_dir: str | None = None,
        provider: str = "",
        model: str = "",
    ):
        from .tools import build_tool_registry
        from .prompts import get_system_prompt

        # Workspace
        if workspace_dir:
            self.workspace = Path(workspace_dir).resolve()
        else:
            self.workspace = Path.cwd() / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Config
        self.agent_config = _resolve_prompt_refs(_load_agent_config())
        self.tool_registry = build_tool_registry()
        self.system_prompt = get_system_prompt()
        self.state = PipelineState()

        # Notebook session — coding-agent uses this for experiment execution
        self.notebook_path = str(self.workspace / "analysis.ipynb")
        self._nb_session = None  # lazy-init on first run

        # LLM settings
        self.provider = provider
        self.model = model

    def _get_llm(self):
        """Build the LLM instance from provider/model settings.

        Resolution order (provider):
            1. Constructor ``provider`` arg  (e.g. from CLI ``--provider``)
            2. ``OC_LLM_PROVIDER`` env       (research-pipeline-specific override)
            3. ``LLM_PROVIDER`` env           (project-wide default, same as bot/interactive)
            4. Fallback: ``"deepseek"``

        Resolution order (api key):
            ``DEEPSEEK_API_KEY`` → ``LLM_API_KEY`` (for deepseek)
            ``OPENAI_API_KEY``  → ``LLM_API_KEY`` (for openai)
            ``ANTHROPIC_API_KEY`` → ``LLM_API_KEY`` (for anthropic)

        Resolution order (model):
            1. Constructor ``model`` arg
            2. ``OC_LLM_MODEL`` env
            3. ``OMICSCLAW_MODEL`` env
            4. Provider-specific default
        """
        provider = (
            self.provider
            or os.getenv("OC_LLM_PROVIDER")
            or os.getenv("LLM_PROVIDER", "deepseek")
        )
        model = (
            self.model
            or os.getenv("OC_LLM_MODEL")
            or os.getenv("OMICSCLAW_MODEL")
        )
        # Unified API key: provider-specific env → LLM_API_KEY fallback
        api_key = os.getenv("LLM_API_KEY", "")

        if provider == "deepseek":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model or "deepseek-chat",
                openai_api_key=os.getenv("DEEPSEEK_API_KEY") or api_key,
                openai_api_base=os.getenv(
                    "DEEPSEEK_BASE_URL",
                    "https://api.deepseek.com/v1",
                ),
                temperature=0.3,
            )
        elif provider in ("openai", ""):
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model or "gpt-4o",
                openai_api_key=os.getenv("OPENAI_API_KEY") or api_key or None,
                temperature=0.3,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=model or "claude-sonnet-4-20250514",
                anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or api_key or None,
                temperature=0.3,
            )
        else:
            # Generic OpenAI-compatible
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=model or "gpt-4o",
                openai_api_key=api_key or None,
                openai_api_base=os.getenv("LLM_BASE_URL"),
                temperature=0.3,
            )

    def _build_agent(self):
        """Build the deepagents agent with OmicsClaw sub-agents.

        Architecture (adapted from EvoScientist):
        - CompositeBackend routes /skills/ to read-only skills directory
        - ToolErrorHandlerMiddleware on orchestrator + all sub-agents
        - skills=["/skills/"] enables deepagents skill discovery
        """
        from deepagents import create_deep_agent
        from deepagents.backends import CompositeBackend

        from .backends import create_sandbox_backend, create_skills_backend
        from .middleware import ToolErrorHandlerMiddleware

        llm = self._get_llm()

        # Workspace backend (sandboxed read/write + shell)
        ws_backend = create_sandbox_backend(str(self.workspace))

        # Skills backend (read-only, maps /skills/ → OmicsClaw skills/)
        project_root = str(Path(__file__).resolve().parent.parent.parent)
        sk_backend = create_skills_backend(project_root)

        # Composite backend — like EvoScientist's multi-route FS
        backend = CompositeBackend(
            default=ws_backend,
            routes={
                "/skills/": sk_backend,
            },
        )

        subagents = _build_subagent_configs(
            self.agent_config, self.tool_registry
        )

        # Orchestrator middleware — error handler for main agent tools
        middleware = [ToolErrorHandlerMiddleware()]

        agent = create_deep_agent(
            model=llm,
            backend=backend,
            system_prompt=self.system_prompt,
            subagents=subagents,
            middleware=middleware,
            skills=["/skills/"],
        )
        return agent

    async def run(
        self,
        idea: str,
        pdf_path: str | None = None,
        h5ad_path: str | None = None,
        on_stage: Callable[[str, str], None] | None = None,
        resume: bool = False,
    ) -> dict[str, Any]:
        """Execute the full research pipeline.

        Parameters
        ----------
        idea : str
            User's research idea / hypothesis (always required).
        pdf_path : str, optional
            Path to the scientific paper PDF (Mode A/B).
            If omitted, runs in Mode C (idea-only).
        h5ad_path : str, optional
            Path to user-provided h5ad file (Mode B).
        on_stage : callable, optional
            Progress callback ``(stage_name, status_message)``.
        resume : bool, optional
            If True, attempt to resume from a previous checkpoint.

        Returns
        -------
        dict with keys: success, report_path, review_path, workspace, error
        """
        def _notify_stage(stage: str, status: str):
            self.state.current_stage = stage
            if on_stage:
                on_stage(stage, status)
            logger.info("[%s] %s", stage, status)

        try:
            # ── Checkpoint resume ─────────────────────────────────────
            skip_intake = False
            if resume:
                loaded = PipelineState.load_checkpoint(self.workspace)
                if loaded and loaded.completed_stages:
                    self.state = loaded
                    _notify_stage(
                        "resume",
                        f"Resuming from checkpoint "
                        f"(completed: {', '.join(loaded.completed_stages)})",
                    )
                    if loaded.is_stage_done("intake"):
                        skip_intake = True

            # ── Stage 1: Intake ────────────────────────────────────────
            if skip_intake:
                _notify_stage("intake", "Skipped (already completed)")
            else:
                if pdf_path:
                    _notify_stage("intake", "Parsing PDF and assembling context...")
                else:
                    _notify_stage("intake", "Assembling idea-only context (Mode C)...")

                from .intake import prepare_intake

                intake = prepare_intake(
                    idea=idea,
                    pdf_path=pdf_path,
                    h5ad_path=h5ad_path,
                    output_dir=str(self.workspace),
                )
                self.state.record_stage("intake", intake.paper_md_path)
                self.state.checkpoint(self.workspace)

                # Auto-generate todos.md so the orchestrator has a checklist
                _generate_todos(
                    self.workspace,
                    mode=intake.input_mode,
                    has_pdf=bool(pdf_path),
                )

            # For resume, re-create a minimal intake result from workspace
            if skip_intake:
                from .intake import IntakeResult
                intake = IntakeResult.from_workspace(
                    str(self.workspace), idea=idea,
                    pdf_path=pdf_path, h5ad_path=h5ad_path,
                )

            # ── Stage 2–7: Agent-driven stages ────────────────────────
            # Register workspace so notebook_create resolves relative paths
            from .tools import set_workspace_dir
            set_workspace_dir(str(self.workspace))

            _notify_stage("agent", "Building multi-agent graph...")
            agent = self._build_agent()

            # Construct the initial prompt for the orchestrator
            initial_prompt = self._build_initial_prompt(intake)

            # If resuming with completed stages, append resume context
            if resume and self.state.completed_stages:
                completed = self.state.completed_stages
                pending = [s for s in self.STAGES if s not in completed]
                initial_prompt += (
                    f"\n\n## ⚡ Resume Context\n"
                    f"This pipeline is being RESUMED from a previous run.\n"
                    f"- **Already completed**: {', '.join(completed)}\n"
                    f"- **Remaining stages**: {', '.join(pending)}\n"
                    f"Skip the completed stages and continue from "
                    f"'{pending[0]}' if stages remain.\n"
                    f"Review existing outputs in the workspace before "
                    f"proceeding.\n"
                )

            _notify_stage("pipeline", "Running research pipeline...")

            # Stream the agent execution
            # Default recursion_limit=25 is far too low for a multi-agent
            # pipeline with 6 sub-agents and multiple tool calls per stage.
            recursion_limit = int(
                os.getenv("OC_RECURSION_LIMIT", "500")
            )
            config = {
                "recursion_limit": recursion_limit,
                "configurable": {
                    "thread_id": f"research-{self.workspace.name}",
                },
            }

            final_output = ""
            review_cap_reached = False
            async for event in agent.astream_events(
                {"messages": [("human", initial_prompt)]},
                config=config,
                version="v2",
            ):
                kind = event.get("event", "")
                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        content = chunk.content
                        if isinstance(content, str):
                            final_output += content
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "")
                    task_input = event.get("data", {}).get("input", {})
                    
                    if tool_name == "task":
                        # Sub-agent delegation — track pipeline stage
                        agent_name = task_input.get("subagent", "sub-agent")
                        task_desc = task_input.get("task_description", "")
                        desc = (task_desc[:50] + "...") if len(task_desc) > 50 else task_desc
                        _notify_stage(
                            agent_name.replace("-agent", ""),
                            f"Delegating task: [italic]{desc}[/italic]"
                        )
                        # Map agent name → pipeline stage for tracking
                        _agent_to_stage = {
                            "planner-agent": "plan",
                            "research-agent": "research",
                            "coding-agent": "execute",
                            "analysis-agent": "analyze",
                            "writing-agent": "write",
                            "reviewer-agent": "review",
                        }
                        stage = _agent_to_stage.get(agent_name)
                        if stage:
                            self.state.record_stage(stage, desc)
                            self.state.checkpoint(self.workspace)
                            if stage == "review":
                                self.state.review_iterations += 1
                                # ── Review cap enforcement ────────
                                if self.state.should_stop_review():
                                    _notify_stage(
                                        "review",
                                        f"Review iteration cap reached "
                                        f"({self.state.max_review_iterations}). "
                                        f"Stopping pipeline."
                                    )
                                    review_cap_reached = True
                                    break
                    elif tool_name == "execute":
                        cmd = task_input.get("command", "")
                        _notify_stage("shell", f"Running: [dim]{cmd[:60]}{'...' if len(cmd) > 60 else ''}[/dim]")
                    elif tool_name == "notebook_create":
                        _notify_stage("notebook", f"Creating notebook...")
                    elif tool_name == "write_file":
                        path = task_input.get("file_path", "")
                        _notify_stage("file", f"Writing [dim]{Path(path).name}[/dim]...")
                    elif tool_name == "read_file":
                        path = task_input.get("file_path", "")
                        _notify_stage("file", f"Reading [dim]{Path(path).name}[/dim]...")
                    elif tool_name == "tavily_search":
                        q = task_input.get("query", "")
                        _notify_stage("search", f"Searching web for: [dim]'{q}'[/dim]")
                    elif tool_name == "skill_search":
                        q = task_input.get("query", "")
                        _notify_stage("search", f"Searching local skills for: [dim]'{q}'[/dim]")
                    elif tool_name not in ("__start__", "agent"):
                        _notify_stage("tool", f"Using [bold]{tool_name}[/bold]...")

            # ── Post-pipeline validation ──────────────────────────────
            report_path = self.workspace / "final_report.md"
            review_path = self.workspace / "review_report.json"
            plan_path = self.workspace / "plan.md"

            # Check for skipped stages
            warnings = []
            if not plan_path.exists() and not self.state.is_stage_done("plan"):
                warnings.append("plan.md not found — planner stage may have been skipped")
            if not report_path.exists() and not review_cap_reached:
                warnings.append("final_report.md not found — writing stage may have been skipped")

            if warnings:
                for w in warnings:
                    logger.warning("Pipeline validation: %s", w)
                    _notify_stage("warning", w)

            # Final checkpoint
            self.state.checkpoint(self.workspace)

            return {
                "success": True,
                "report_path": str(report_path) if report_path.exists() else "",
                "review_path": str(review_path) if review_path.exists() else "",
                "notebook_path": self.notebook_path,
                "workspace": str(self.workspace),
                "intake": {
                    "mode": intake.input_mode,
                    "title": intake.paper_title,
                    "geo_accessions": intake.geo_accessions,
                },
                "completed_stages": self.state.completed_stages,
                "review_iterations": self.state.review_iterations,
                "review_cap_reached": review_cap_reached,
                "warnings": warnings,
                "final_output": final_output[:2000],
                "error": "",
            }

        except Exception as e:
            logger.error("Pipeline failed: %s", e, exc_info=True)
            self.state.error = str(e)
            # Save checkpoint even on failure for resume
            try:
                self.state.checkpoint(self.workspace)
            except Exception:
                pass
            return {
                "success": False,
                "report_path": "",
                "review_path": "",
                "notebook_path": self.notebook_path,
                "workspace": str(self.workspace),
                "completed_stages": self.state.completed_stages,
                "error": str(e),
            }
        finally:
            # Clean up notebook kernel
            from .tools import _nb_session
            if _nb_session is not None:
                try:
                    _nb_session.shutdown()
                except Exception:
                    pass

    def _build_initial_prompt(self, intake) -> str:
        """Build the initial prompt that kicks off the orchestrator.

        For Modes A/B, injects ``02_methodology.md`` content directly so the
        planner-agent receives untruncated methodology without needing
        a separate ``read_file`` call.  The coding-agent is NOT expected to
        read the methodology — it should follow ``plan.md`` instead.
        """
        from .intake import IntakeResult

        workspace_abs = str(self.workspace.resolve())

        parts = [
            "# New Research Request\n",
            "The user wants to conduct a multi-omics research project. "
            "Start the research pipeline workflow.\n",
            f"## Workspace\n",
            f"All output files MUST be saved under: `{workspace_abs}`\n",
            f"This includes: plan.md, todos.md, notebooks (.ipynb), "
            f"artifacts/, final_report.md, review_report.json.\n",
            f"When using shell commands, always use absolute paths with "
            f"this workspace prefix. When creating notebooks, use simple "
            f"filenames (the system resolves them to the workspace).\n",
        ]

        # Mode C: idea only
        if intake.input_mode == "C":
            parts.append(f"## User's Research Idea\n\n{intake.idea}\n")
            parts.append(
                "## Data (Mode C: idea only)\n"
                "No reference paper was provided. Start by delegating to the "
                "research-agent to search for relevant literature, datasets, "
                "and methods. Then proceed to the planner-agent.\n"
            )
        else:
            # Mode A / B — inject paper structure + methodology content
            parts.extend([
                "## Paper (Macro Agentic FS)\n",
                f"The reference paper has been 'unpacked' into a structured "
                f"directory at `{workspace_abs}/paper/`:\n",
                f"- `paper/01_abstract_conclusion.md` — "
                f"Abstract, introduction, conclusions (quick overview)\n",
                f"- `paper/02_methodology.md` — **MUST READ** "
                f"Complete, untruncated methods, algorithms, and parameters\n",
                f"- `paper/03_results_figs.md` — "
                f"Results and discussion sections\n",
                f"- `paper/04_fulltext.md` — "
                f"Full cleaned text (reference / fallback)\n",
            ])

            # ── Methodology: light hint + on-demand read ──────────────
            # Instead of embedding the full methodology (~2000 tokens) in
            # the initial prompt (which persists through ALL orchestrator
            # turns), we inject only a brief summary hint plus a mandatory
            # read_file instruction.  This keeps the prompt lean while
            # ensuring the planner still gets full methodology.
            #
            # Design rationale:
            #   - initial_prompt stays in orchestrator context for 50-100+
            #     LLM calls across all 7 stages.  Full methodology wastes
            #     tokens in execute/analyze/write/review stages.
            #   - Orchestrator reads the file once via read_file, passes
            #     it to planner's task body → only planner's sub-context
            #     carries the full text.
            #   - The brief hint serves as a safety net: even if the
            #     orchestrator skips read_file, the planner still has
            #     enough context to produce a reasonable plan.
            meth_path = self.workspace / "paper" / "02_methodology.md"
            if meth_path.exists():
                meth_content = meth_path.read_text(encoding="utf-8")
                # Extract a brief summary (first ~500 chars) as a hint
                hint = meth_content[:500].strip()
                if len(meth_content) > 500:
                    hint += "\n... [truncated — read full file for all parameters]"
                parts.append(
                    "## Paper Methodology (Summary Hint)\n"
                    "Below is a **brief excerpt** of the paper's computational "
                    "methods. The FULL untruncated methodology is in:\n"
                    f"`{workspace_abs}/paper/02_methodology.md`\n\n"
                    "```\n"
                    f"{hint}\n"
                    "```\n\n"
                    "**MANDATORY**: Before delegating to planner-agent, you MUST:\n"
                    f"1. Call `read_file(\"{workspace_abs}/paper/02_methodology.md\")`\n"
                    "2. Include the FULL content in the planner's task description\n"
                    "3. The planner needs exact parameters, QC thresholds, and "
                    "algorithm details to create an accurate plan.\n"
                )
            else:
                parts.append(
                    "## Paper Methodology\n"
                    "NOTE: `02_methodology.md` was not generated. Use `read_file` "
                    f"on `{workspace_abs}/paper/04_fulltext.md` for methods.\n"
                )

            parts.append(f"## User's Research Idea\n\n{intake.idea}\n")

            if intake.input_mode == "B":
                parts.append(
                    f"## Data (Mode B: user-provided)\n"
                    f"User provided h5ad file: {intake.h5ad_path}\n"
                )
                if intake.h5ad_metadata:
                    meta = intake.h5ad_metadata
                    parts.append(
                        f"- Cells: {meta.get('n_obs', 'N/A')}, "
                        f"Genes: {meta.get('n_vars', 'N/A')}\n"
                    )
                    if meta.get("has_spatial"):
                        parts.append("- Contains spatial coordinates\n")
            else:
                parts.append(
                    f"## Data (Mode A: from paper)\n"
                    f"GEO accessions found: {', '.join(intake.geo_accessions) or 'None'}\n"
                    f"Download datasets if accessions are available.\n"
                )

        # ── Delegation instructions (role separation) ─────────────
        parts.append(
            f"\n## Instructions\n"
            f"Follow the research pipeline workflow. Delegate to agents "
            f"based on the role separation below:\n\n"
            f"### Agent Delegation Rules\n"
            f"1. **planner-agent**: FIRST delegate here. Include the "
            f"'Paper Methodology' section above in the task body so the "
            f"planner can extract exact parameters and QC thresholds. "
            f"The planner produces `plan.md`.\n"
            f"2. **research-agent**: Delegate for literature search, "
            f"baseline comparison, and dataset discovery.\n"
            f"3. **coding-agent**: Delegate for experiment execution. "
            f"The coding-agent does NOT read the paper methodology — "
            f"it reads `plan.md` and follows the plan. Include the plan "
            f"content or key parameters in the task description.\n"
            f"4. **analysis-agent**: Delegate for interpreting results, "
            f"computing metrics, and generating plots.\n"
            f"5. **writing-agent**: Delegate for drafting the report.\n"
            f"6. **reviewer-agent**: Delegate for peer review.\n"
            f"\n"
            f"IMPORTANT: All generated files must go into `{workspace_abs}`.\n"
            f"Use this as the base directory for ALL read/write operations.\n"
        )

        return "\n".join(parts)

