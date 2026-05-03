# CUDA Torch Wheel Setup Plan

**Goal:** Fix CUDA PyTorch setup failures caused by mixing the official PyTorch channel with OmicsClaw's conda-forge/bioconda main environment.

**Root cause:** Earlier CUDA override attempts used conda solver paths:
first official `pytorch`/`nvidia` channels with `pytorch-cuda=<version>`, then
conda-forge `pytorch-gpu` with `cuda-version=<version>`. The second path avoids
TUNA `nvidia` 404s and some BLAS/MKL switches, but on the full OmicsClaw env it
still makes conda re-solve `libtorch`, `libarrow`, `libprotobuf`, `libabseil`,
and BLAS/MKL together. With CUDA 12.1 that solver graph can become
unsatisfiable.

**Decision update:** Do not use conda for post-create CUDA PyTorch overrides.
Keep the CPU-safe conda baseline from `environment.yml`, and when
`OMICSCLAW_TORCH_BACKEND=auto/cuda` needs CUDA, install the official PyTorch
CUDA wheel in the existing env with `uv pip install --index-url
https://download.pytorch.org/whl/cu121 torch==2.5.1+cu121`. This narrows the
operation to the Python wheel layer and avoids re-solving the conda scientific
stack.

**Scope:** Change only the setup-layer CUDA PyTorch override, tests, and docs. Do not change GraphST runtime logic.

**File map:**

- Modify `0_setup_env.sh`: install CUDA PyTorch from the official PyTorch CUDA
  wheel index using `uv pip install`, with pip fallback.
- Modify `tests/test_setup_env_script.py`: update fake installer expectations
  and add regression assertions that no conda GPU torch solver path is used by
  default.
- Modify `README.md` and `README_zh-CN.md`: document the CUDA wheel route and
  remove conda-forge GPU-stack guidance from the default path.
- Modify `docs/superpowers/README.md` and `docs/superpowers/plans/README.md`: index this plan.

**Implementation tasks:**

1. Update tests first.
   - Expected CUDA install command should use `uv pip install --index-url https://download.pytorch.org/whl/cu121 --upgrade torch==2.5.1+cu121`.
   - Tests should fail if `pytorch-gpu`, `cuda-version=`, `pytorch-cuda`, `-c nodefaults`, or official conda channels appear in the default CUDA command.
   - Preserve existing CPU opt-out, forced CUDA failure, prefix install, and marker removal coverage.

2. Run targeted tests and confirm RED.
   - Command: `python -m pytest tests/test_setup_env_script.py -q -k 'torch_backend or cuda_torch'`.

3. Implement the script change.
   - Map `OMICSCLAW_PYTORCH_CUDA_VERSION=12.1` to `cu121`.
   - Default to `OMICSCLAW_TORCH_VERSION=2.5.1`.
   - Install `torch==${OMICSCLAW_TORCH_VERSION}+${CUDA_TAG}` from `OMICSCLAW_TORCH_WHEEL_INDEX`, defaulting to the official PyTorch wheel index.
   - Keep CPU marker removal and CUDA verification.

4. Update documentation.
   - Explain that the setup uses PyTorch CUDA wheels to avoid conda re-solving the full environment.
   - Mention `OMICSCLAW_TORCH_WHEEL_INDEX`, `OMICSCLAW_TORCH_VERSION`, and CUDA tag/spec overrides for advanced cases.

5. Verify.
   - `python -m pytest tests/test_setup_env_script.py -q`
   - `bash -n 0_setup_env.sh`
   - `git diff --check`

**Acceptance criteria:**

- Default CUDA setup no longer invokes conda GPU torch packages (`pytorch-gpu`, `cuda-version`, `pytorch-cuda`) or `nodefaults` as a CLI channel.
- CUDA setup remains automatic/strict/CPU-selectable via `OMICSCLAW_TORCH_BACKEND`.
- Tests cover named and prefix environments, CPU marker removal, and forced CUDA verification failure.
