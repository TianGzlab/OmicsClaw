"""Every trial process is seeded, so a method run twice with the same parameters gives the same labels.

Some methods (SpaGCN, CellCharter) never fix their own random state; without
this, the default-parameter trial of the probe and the same method run
directly disagreed (ARI 0.4-0.7 on DLPFC), and a tuning decision could rest on
a lucky draw. The runner puts a seeding ``sitecustomize`` first on
``PYTHONPATH``; it seeds ``random`` at start-up and numpy and torch right
after their import (torch with deterministic algorithms), and sets
``PYTHONHASHSEED`` and the cuBLAS workspace so the CUDA kernels are
deterministic too. No skill file is changed.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from omicsclaw.ensemble.resources import Lease
from tests.ensemble.test_runner import _input, _run, _runner

REPO = Path(__file__).resolve().parents[2]
SITECUSTOMIZE = REPO / "omicsclaw" / "ensemble" / "_seed" / "sitecustomize.py"


def _lease():
    return Lease(gpu=None, cpus=2, memory_gb=1.0)


def test_the_seed_environment(tmp_path):
    runner = _runner(tmp_path, seed=7)
    env = runner.trial_environment(tmp_path, _lease())
    assert env["PYTHONPATH"].split(":")[0].endswith("omicsclaw/ensemble/_seed")
    assert env["OMICSCLAW_TRIAL_SEED"] == "7" and env["PYTHONHASHSEED"] == "0"
    assert env["CUBLAS_WORKSPACE_CONFIG"] == ":4096:8" and env["OMICSCLAW_TRIAL_DETERMINISM"] == "strict"
    assert runner.seed_sitecustomize_sha256() == hashlib.sha256(SITECUSTOMIZE.read_bytes()).hexdigest()
    unseeded = _runner(tmp_path, seed=None).trial_environment(tmp_path, _lease())
    assert "OMICSCLAW_TRIAL_SEED" not in unseeded and unseeded["PYTHONPATH"] == str(REPO)


def test_the_default_is_a_fixed_seed(tmp_path):
    assert _runner(tmp_path).seed == 0


def _probe(env: dict) -> str:
    code = (
        "import sys, os, random\n"
        "import numpy\n"
        "print('sitecustomize' in sys.modules, os.environ.get('OMICSCLAW_TRIAL_SEEDED'), random.random(),"
        " numpy.random.rand())"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **env}, timeout=120)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_the_sitecustomize_is_loaded_and_seeds_random_and_numpy(tmp_path):
    runner = _runner(tmp_path, seed=0)
    env = runner.trial_environment(tmp_path, _lease())
    first, second = _probe(env), _probe(env)
    assert first == second and first.startswith("True 1 ")
    import random

    import numpy

    random.seed(0)
    numpy.random.seed(0)
    assert first == f"True 1 {random.random()} {numpy.random.rand()}"
    other = runner.trial_environment(tmp_path, _lease()) | {"OMICSCLAW_TRIAL_SEED": "1"}
    assert _probe(other) != first


def test_torch_is_made_deterministic_when_it_is_imported(tmp_path):
    pytest.importorskip("torch")
    env = _runner(tmp_path, seed=0).trial_environment(tmp_path, _lease())
    code = "import torch; print(torch.are_deterministic_algorithms_enabled(), torch.rand(1).item())"
    outputs = [
        subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin", **env}, timeout=300).stdout.strip()
        for _ in range(2)
    ]
    assert outputs[0] == outputs[1] and outputs[0].startswith("True ")


def _labels(result) -> list[str]:
    with gzip.open(Path(result.output_dir) / "labels.csv.gz", "rt") as source:
        return source.read().splitlines()


def test_the_same_trial_twice_gives_the_same_labels(tmp_path):
    source = _input(tmp_path / "ws" / "data" / "in.h5ad")
    seeded = _runner(tmp_path / "a", seed=0)
    first = _run(seeded, source, "rand", {"n": 5})
    second = _run(seeded, source, "rand", {"n": 5})
    assert first.status == second.status == "ok"
    assert _labels(first) == _labels(second)
    assert first.provenance["seed"] == 0 and first.provenance["seed_sitecustomize_sha256"]
    unseeded = _runner(tmp_path / "b", seed=None)
    a = _run(unseeded, source, "rand", {"n": 5})
    b = _run(unseeded, source, "rand", {"n": 5})
    assert _labels(a) != _labels(b)
