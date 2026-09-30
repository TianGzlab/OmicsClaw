"""Shared pieces of the 0057 validation scripts: paths, units, runners, the model.

Every script in this directory is a benchmark driver. It may read ground
truth (only ``evaluate.py`` and ``define_population.py`` do, and only where the
plan allows); nothing under ``omicsclaw/`` imports these files.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

SKILL_PYTHON = os.environ.get("OMICSCLAW_ENSEMBLE_PYTHON", "/opt/conda/envs/OmicsClaw/bin/python")
SKILLS = REPO / "skills"
PREPROCESS = SKILLS / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
DOMAINS = SKILLS / "spatial" / "spatial-domains" / "spatial_domains.py"
DLPFC_TISSUE = "human dorsolateral prefrontal cortex"
DEV_SLICES = ("151673", "151674")
DEV_DATA = Path(os.environ.get("OMICSCLAW_TUNING_DEV_DATA", "/workspace/algorithm/zhouwg_project/data_external/DLPFC"))
TRUTH_COLUMN = "sce.layer_guess"
RUNNABLE = ("leiden", "louvain", "spagcn", "graphst", "cellcharter")
TRIAL_SEED = 0
"""Seed of every trial process (see ``omicsclaw/ensemble/_seed/sitecustomize.py``)."""
ARMS = {"A1": ("det", True, 3), "A2": ("det", False, 3), "A6": ("random", False, 3), "A3": ("free", True, 2)}
"""arm -> (pipeline arm, tissue given, repetitions)."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(document, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---- units ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    """One validation unit: an opaque id, its prepared input, tissue and platform."""

    uid: str
    input: Path
    tissue: str
    data_type: str

    @property
    def context(self) -> dict[str, Any]:
        return {"data_type": self.data_type} if self.data_type else {}


def preprocess(raw: Path, out_dir: Path, *, data_type: str, species: str, max_mt_pct: float | None) -> Path:
    """Run spatial-preprocess on *raw*; returns the processed ``.h5ad``."""
    command = [SKILL_PYTHON, str(PREPROCESS), "--input", str(raw), "--output", str(out_dir),
               "--data-type", data_type, "--species", species]
    if max_mt_pct is not None:
        command += ["--max-mt-pct", str(max_mt_pct)]
    done = subprocess.run(command, capture_output=True, text=True,
                          env={**os.environ, "PYTHONPATH": str(REPO)})
    if done.returncode != 0:
        raise RuntimeError(f"preprocess failed: {done.stderr[-3000:]}")
    return out_dir / "processed.h5ad"


def strip_obs(processed: Path, target: Path, batch: str = "b0") -> None:
    """Write *processed* with ``obs`` reduced to one ``batch`` column (runs under the skill interpreter)."""
    code = (
        "import anndata, sys\n"
        "a = anndata.read_h5ad(sys.argv[1])\n"
        "import pandas as pd\n"
        "a.obs = pd.DataFrame({'batch': [sys.argv[3]] * a.n_obs}, index=a.obs_names)\n"
        "a.write_h5ad(sys.argv[2])\n"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([SKILL_PYTHON, "-c", code, str(processed), str(target), batch], check=True,
                   env={**os.environ, "PYTHONPATH": str(REPO)})


# ---- runners ----------------------------------------------------------------------------


def make_pool(cpus: int | None = None, memory_gb: float | None = None):
    from omicsclaw.ensemble.resources import ResourcePool, detect_gpus

    gpus = asyncio.run(detect_gpus(""))
    total_mem = memory_gb
    if total_mem is None:
        from omicsclaw.entry.config import mem_total_gib

        total_mem = (mem_total_gib() or 256) * 0.8 - 64
    return ResourcePool(gpu_ids=gpus.ids, slots_per_gpu=2, memory_gb=total_mem,
                        cpus=cpus or (os.cpu_count() or 8) - 4, gpu_detail=gpus.describe())


def make_runner(workspace: Path, pool, *, seed: int | None = TRIAL_SEED):
    from omicsclaw.ensemble import RUNS_DIRNAME
    from omicsclaw.ensemble.execution import LocalExecutor
    from omicsclaw.ensemble.runner import EnsembleRunner
    from omicsclaw.ensemble.space import TuningCatalog
    from omicsclaw.skills import load_skills

    catalog = TuningCatalog.from_skills(load_skills(SKILLS))
    return EnsembleRunner(catalog=catalog, pool=pool, executor=LocalExecutor(python=SKILL_PYTHON),
                          runs_root=workspace / RUNS_DIRNAME, repo_root=REPO, seed=seed, determinism="strict")


def skill_text():
    from omicsclaw.ensemble.tuning.tools import skill_text_loader
    from omicsclaw.skills import load_skills

    return skill_text_loader(load_skills(SKILLS))


def real_model(model: str = "", provider: str = ""):
    """The configured provider and what is recorded about it."""
    from omicsclaw.ensemble.tuning.llm import LLMSettings
    from omicsclaw.provider import provider_from_env, resolve_config

    resolved = resolve_config(provider, model)
    instance = RetryingModel(provider_from_env(provider, model))
    return instance, LLMSettings(model=resolved.model, provider=resolved.provider,
                                 temperature=resolved.temperature,
                                 max_tokens=resolved.max_tokens or None,
                                 thinking_budget=resolved.thinking_budget_tokens or None)


TRANSIENT = ("APIConnectionError", "APITimeoutError", "Connection error", "timed out", "status 5", "InternalServerError",
             "RateLimitError", "ServiceUnavailable")


def is_transient(exc: BaseException) -> bool:
    """Whether *exc* is a model-call failure worth retrying (connection, time-out, 429, 5xx)."""
    text = f"{type(exc).__name__}: {exc}"
    return any(marker in text for marker in TRANSIENT)


class RetryingModel:
    """A model whose calls are retried with exponential back-off on transient failures.

    Up to *attempts* calls, waiting ``base * 2**i`` seconds (at most *cap*) between
    them; any other error, or the last transient one, is raised.
    """

    def __init__(self, inner, *, attempts: int = 8, base: float = 5.0, cap: float = 300.0, sleep=None) -> None:
        self._inner = inner
        self.attempts = attempts
        self.base = base
        self.cap = cap
        self._sleep = sleep or asyncio.sleep
        self.retries = 0

    @property
    def name(self) -> str:
        return self._inner.name

    async def generate(self, messages, tools=None):
        for attempt in range(self.attempts):
            try:
                return await self._inner.generate(messages, tools)
            except Exception as exc:  # noqa: BLE001 - classified below
                if attempt == self.attempts - 1 or not is_transient(exc):
                    raise
                self.retries += 1
                await self._sleep(min(self.cap, self.base * 2 ** attempt))

    def generate_stream(self, messages, tools=None):
        return self._inner.generate_stream(messages, tools)

    def bind(self, **overrides):
        return self._inner.bind(**overrides)


def load_env_file(path: Path = REPO / ".env") -> None:
    """Export the ``KEY=value`` lines of *path* not already in the environment (values never printed)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def copy_probe(source_runs: Path, target_runs: Path, base: str) -> None:
    """Copy the probe run (``<base>-probe``) of one unit into another workspace's ``ensemble_runs``."""
    target_runs.mkdir(parents=True, exist_ok=True)
    name = f"{base}-probe"
    if not (target_runs / name).exists():
        shutil.copytree(source_runs / name, target_runs / name, symlinks=False)
    cache = source_runs / "_cache"
    if cache.is_dir() and not (target_runs / "_cache").exists():
        shutil.copytree(cache, target_runs / "_cache")
