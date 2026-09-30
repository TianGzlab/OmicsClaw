"""Seed every trial process: ``random`` at start-up, numpy and torch when they are imported.

Put on ``PYTHONPATH`` ahead of everything else by the trial runner, so Python
imports it at start-up. Reads ``OMICSCLAW_TRIAL_SEED``; without it nothing is
done. numpy and torch are seeded right after their first import, through an
import hook, so a process that never imports them does not pay for them.
torch is also switched to deterministic algorithms; with
``OMICSCLAW_TRIAL_DETERMINISM=warn`` a non-deterministic operation warns
instead of raising. Uses only the standard library.
"""

import importlib.abc
import importlib.machinery
import os
import random
import sys

_SEED = os.environ.get("OMICSCLAW_TRIAL_SEED")


def _seed_numpy(module):
    module.random.seed(int(_SEED))


def _seed_torch(module):
    seed = int(_SEED)
    module.manual_seed(seed)
    try:
        module.cuda.manual_seed_all(seed)
    except Exception:
        pass
    module.use_deterministic_algorithms(True, warn_only=os.environ.get("OMICSCLAW_TRIAL_DETERMINISM") == "warn")
    module.backends.cudnn.deterministic = True
    module.backends.cudnn.benchmark = False


_AFTER_IMPORT = {"numpy": _seed_numpy, "torch": _seed_torch}


class _Loader(importlib.abc.Loader):
    def __init__(self, inner, after):
        self._inner = inner
        self._after = after

    def create_module(self, spec):
        return self._inner.create_module(spec)

    def exec_module(self, module):
        self._inner.exec_module(module)
        self._after(module)


class _SeedOnImport(importlib.abc.MetaPathFinder):
    """Wraps the loader of numpy and torch so they are seeded once loaded."""

    def find_spec(self, name, path=None, target=None):
        after = _AFTER_IMPORT.pop(name, None)
        if after is None:
            return None
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None or spec.loader is None:
            return spec
        spec.loader = _Loader(spec.loader, after)
        return spec


if _SEED is not None:
    random.seed(int(_SEED))
    os.environ["OMICSCLAW_TRIAL_SEEDED"] = "1"
    for _name in list(_AFTER_IMPORT):
        if _name in sys.modules:
            _AFTER_IMPORT.pop(_name)(sys.modules[_name])
    sys.meta_path.insert(0, _SeedOnImport())
