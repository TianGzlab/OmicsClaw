# Auto Torch Backend Setup Implementation Plan

**Goal:** Make `0_setup_env.sh` choose the correct PyTorch CPU/CUDA runtime during environment construction so GPU-capable remote servers do not silently keep the CPU-only `pytorch-cpu` build.

**Scope:** This plan changes the conda setup script, setup-script regression tests, and user-facing installation docs. It does not change GraphST runtime device selection or skill command parsing.

**Key assumptions and constraints:**

- The issue is environment-level: `environment.yml` installs `pytorch-cpu`, while GraphST can only use CUDA when the active Python environment has a CUDA-enabled PyTorch build.
- The setup script may run on the remote analysis server, not on the local desktop machine. Tests must use fake `mamba`/`conda`/`nvidia-smi` commands rather than local GPU state.
- Default behavior should remain safe for CPU-only machines. `auto` should try CUDA only when `nvidia-smi -L` reports a GPU, and should warn and continue if CUDA PyTorch cannot be installed or verified.
- `cuda` mode should be explicit and strict: install and verify CUDA PyTorch or exit non-zero.
- `cpu` mode should skip CUDA override entirely, even if `nvidia-smi` exists.

**File map:**

- Modify `0_setup_env.sh`: add `OMICSCLAW_TORCH_BACKEND=auto|cuda|cpu`, `OMICSCLAW_PYTORCH_CUDA_VERSION`, conda install helper, GPU detection, CUDA PyTorch install, and verification.
- Modify `tests/test_setup_env_script.py`: add fake installer tests for auto GPU install, CPU opt-out, forced CUDA failure, and invalid backend validation.
- Modify `environment.yml`: update PyTorch comments so `pytorch-cpu` is documented as the baseline that the setup script may replace.
- Modify `README.md` and `README_zh-CN.md`: replace manual-only CUDA instructions with automatic/default behavior and override examples.
- Modify `docs/superpowers/README.md` and `docs/superpowers/plans/README.md`: index this plan.

**Implementation tasks:**

1. Add setup-script tests first.
   - Add tests that create fake `mamba`, `conda`, and optional `nvidia-smi` commands under `tmp_path/bin`.
   - Confirm `OMICSCLAW_TORCH_BACKEND=auto` plus fake GPU causes a `mamba install -n OmicsClaw -c pytorch -c nvidia pytorch pytorch-cuda=12.1 -y` call before Tier 2.
   - Confirm `OMICSCLAW_TORCH_BACKEND=cpu` does not make any `pytorch-cuda` install call when fake GPU is present.
   - Confirm `OMICSCLAW_TORCH_BACKEND=cuda` exits non-zero when fake CUDA verification fails.
   - Confirm invalid backend values exit before conda env creation.

2. Run the new targeted tests and observe RED.
   - Command: `python -m pytest tests/test_setup_env_script.py -q -k 'torch_backend or invalid_torch_backend'`
   - Expected: failures because `0_setup_env.sh` does not yet implement these variables or commands.

3. Implement backend selection in `0_setup_env.sh`.
   - Parse `OMICSCLAW_TORCH_BACKEND`, defaulting to `auto`, and validate `auto|cuda|cpu`.
   - Parse `OMICSCLAW_PYTORCH_CUDA_VERSION`, defaulting to `12.1`.
   - Add `env_install()` to call `$INSTALLER install` against either `-n "$ENV_TARGET_VALUE"` or `-p "$ENV_TARGET_VALUE"`.
   - Add `detect_nvidia_gpu()` using `command -v nvidia-smi` and `nvidia-smi -L`.
   - Add `install_cuda_pytorch()` that installs `pytorch` plus `pytorch-cuda=$PYTORCH_CUDA_VERSION` from `pytorch` and `nvidia` channels.
   - Add `verify_cuda_pytorch()` that runs Python inside the created env and exits non-zero unless `torch.cuda.is_available()` is true.
   - Insert the torch backend step after the env prefix is resolved and before Tier 2 pip installs.
   - In `auto`, only attempt CUDA when GPU detection succeeds; on install/verify failure print a clear warning and continue.
   - In `cuda`, always attempt install and verification; any failure exits non-zero.
   - In `cpu`, print a CPU-mode message and leave the baseline CPU PyTorch build in place.

4. Run targeted setup-script tests and script syntax validation.
   - Command: `python -m pytest tests/test_setup_env_script.py -q -k 'torch_backend or invalid_torch_backend'`
   - Command: `bash -n 0_setup_env.sh`

5. Update docs and comments.
   - Update `README.md` and `README_zh-CN.md` common install snippets with `OMICSCLAW_TORCH_BACKEND` and `OMICSCLAW_PYTORCH_CUDA_VERSION`.
   - Update `environment.yml` PyTorch comment to match the setup-script behavior.
   - Add this plan to the two superpowers indexes.

6. Run final verification and review.
   - Command: `python -m pytest tests/test_setup_env_script.py -q`
   - Command: `bash -n 0_setup_env.sh`
   - Inspect `git diff --check` and `git status --short`.

**Acceptance criteria:**

- Fresh installs on GPU-capable servers automatically attempt a CUDA-enabled PyTorch override.
- CPU-only installs remain non-failing by default.
- Forced CUDA installs fail clearly if CUDA PyTorch is not usable.
- Users can opt out with `OMICSCLAW_TORCH_BACKEND=cpu`.
- README documentation no longer tells CUDA users that manual post-install override is the only path.
