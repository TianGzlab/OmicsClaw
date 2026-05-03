# Conda-Forge Torch GPU Setup Plan

**Goal:** Fix CUDA PyTorch setup failures caused by mixing the official PyTorch channel with OmicsClaw's conda-forge/bioconda main environment.

**Root cause:** `0_setup_env.sh` currently installs CUDA PyTorch with official `pytorch` and `nvidia` channels using `pytorch=*=*cuda* pytorch-cuda=<version>`. On an environment built with strict conda-forge/bioconda priority, that can make the solver switch BLAS/MKL families and fail with `libblas ... mkl` incompatibilities.

**Scope:** Change only the setup-layer CUDA PyTorch override, tests, and docs. Do not change GraphST runtime logic.

**File map:**

- Modify `0_setup_env.sh`: install CUDA PyTorch from conda-forge using `pytorch-gpu` and `cuda-version`.
- Modify `tests/test_setup_env_script.py`: update fake installer expectations and add a regression assertion that official `pytorch-cuda` is not used by default.
- Modify `README.md` and `README_zh-CN.md`: document conda-forge GPU route and remove official-channel guidance from the default path.
- Modify `docs/superpowers/README.md` and `docs/superpowers/plans/README.md`: index this plan.

**Implementation tasks:**

1. Update tests first.
   - Expected CUDA install command should use `-c conda-forge -c bioconda pytorch pytorch-gpu cuda-version=<version> -y`.
   - Tests should reject `-c nodefaults`; `nodefaults` is a YAML marker, not a downloadable CLI channel.
   - Tests should fail if `pytorch-cuda` or official `https://conda.anaconda.org/pytorch` is present in the default command.
   - Preserve existing CPU opt-out, forced CUDA failure, prefix install, and marker removal coverage.

2. Run targeted tests and confirm RED.
   - Command: `python -m pytest tests/test_setup_env_script.py -q -k 'torch_backend or cuda_torch'`.

3. Implement the script change.
   - Replace official channel defaults with `OMICSCLAW_TORCH_CHANNELS`, defaulting to `conda-forge bioconda nodefaults`.
   - Filter `nodefaults` out when converting `OMICSCLAW_TORCH_CHANNELS` into `mamba install -c ...` arguments.
   - Install `pytorch`, `pytorch-gpu`, and `cuda-version=$OMICSCLAW_PYTORCH_CUDA_VERSION`.
   - Keep CPU marker removal and CUDA verification.

4. Update documentation.
   - Explain that the setup uses conda-forge `pytorch-gpu + cuda-version` to stay in the same channel/BLAS ecosystem as the main env.
   - Mention `OMICSCLAW_TORCH_CHANNELS` only as an advanced override.

5. Verify.
   - `python -m pytest tests/test_setup_env_script.py -q`
   - `bash -n 0_setup_env.sh`
   - `git diff --check`

**Acceptance criteria:**

- Default CUDA setup no longer invokes official `pytorch`/`nvidia` channels or `pytorch-cuda`.
- CUDA setup remains automatic/strict/CPU-selectable via `OMICSCLAW_TORCH_BACKEND`.
- Tests cover named and prefix environments, CPU marker removal, and forced CUDA verification failure.
