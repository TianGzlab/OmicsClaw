# 计划 0061 交付记录 — P0b 残留与文档、P1 探测与报告

**日期**：2026-09-24。**规格**：`docs/plans/0061-adaptive-env-provisioning.md` 第 5 版（定稿）。本记录不改动计划正文。
**范围**：本次只做 P0b 和 P1。P2 排在论文主线之后；P3 要等 0056 合入，而且 Q4–Q10、Q16、Q17 还没裁定。
**状态**：P0b、P1 都已实施并验收。没有 commit，也没有 `git add`（见偏离 1）。
**开工状态**：工作树是 `0881aa7b` 加上未提交改动，也就是 0062 两个阶段都完成之后的状态。

## 1. 结论

| 阶段 | 验收结论 | 关键证据 |
|---|---|---|
| P0b | **通过** | `$BASE` 为 2200 passed、17 skipped，与开工基线相同，没有新增失败。`tests/test_env_example.py` 通过（新增 4 个退役名）。`tests/test_adaptive_env_phase3.py` 已从工作树删除。按 P0b 时的复跑结果，F58 共 10 处，其中 6 处补了声明、4 处进了 P1 例外表，每处都附理由。文档引用逐条核对过 |
| P1 | **通过** | §6 P1 命令为 **2400 passed、17 skipped**。全量回归没有新增失败，比开工基线少了 phase3 那一个收集错误。§5 P1 验收的 12 项逐条满足（§4.3）。§6.2 里与 P1 相关的变异全部变红（§5） |

## 2. 开工基线（0062 完成后的同一工作树）

输出目录：`/tmp/claude-0/…/scratchpad/impl0061/baseline/`（会话临时目录，不入库）。

- **全量**（0062 附录 B 命令）：`214 failed, 6176 passed, 46 skipped, 16 deselected, 43 errors in 343.12s`。失败清单 257 行，与 0062 交付时的失败集合**逐行相同**（`diff` 为空）。
- **§6 `$BASE`**：`2200 passed, 17 skipped in 102.82s`。计划记的 2066 是 0062 之前的数字，而且当时 `$BASE` 还不含 `tests/sdk`。
- **F64 复跑**：见附录 A 的 F64 扫描。改为用 `ast.literal_eval` 直接读 `skills/_sdk/deps.py` 的 `DEPENDENCIES`，结果：
  - 61 键；声明名 63 个；
  - 落到回落的 16 个：`PyYAML adjustText anndata dask h5py matplotlib mygene networkx numpy packaging pandas requests scanpy scikit-learn scipy statsmodels`；
  - git 类的声明者：pybanksy←spatial-domains、STAGATE-pyG←spatial-domains、STalign←spatial-register；
  - r 类（xcms、metaboanalyst）与带 `also` 的 singler 都没有任何 skill 声明。

  以上与计划 F64 完全一致。
- **F58 复跑**：调用名按 0062 F29 的 AST 规则收集，排除 `skills/singlecell/_lib/preflight.py`。结果是 **10 个 skill、10 处**：
  - 计划列出的 8 个 skill：`spatial-domains`→cellcharter、`spatial-integrate`→scanorama、`sc-clustering`→louvain、`sc-integrate-cluster`→scvi-tools，以及 `sc-qc`、`sc-filter`、`sc-preprocessing`、`scatac-preprocessing` 各→scrublet（经 `_lib/qc.py`）；
  - **新增 2 处**：`sc-enrichment`→gseapy（经 `_lib/stat_enrichment.py`）、`spatial-enrichment`→gseapy（经 `_lib/enrichment.py`）。新规则把"从 `skills._sdk.deps` import 的 `get`"也算作调用，这两处是它带出来的；计划 F58 当时明确不计 `get`。
  - 不排除 preflight 时报 23 个 skill，与 F58"模块粒度误报"的描述一致。

## 3. P0b

### 3.1 先红

`RETIRED` 先加上 4 个旧变量名，此时测试失败：`['OMICSCLAW_ADAPTIVE_ENV', 'OMICSCLAW_SKIP_ADAPTIVE_ENV', 'OMICSCLAW_ENV_DIR', 'OMICSCLAW_RUN_PYTHON'] vanished instead of being retired`。

### 3.2 实施与核对

| 项 | 落点 | 核对 |
|---|---|---|
| 删除 `tests/test_adaptive_env_phase3.py` | 工作树删除（计划 §4.8 与 §5 P0b 的删除清单） | `git status` 显示 ` D`；`git ls-files` 仍会列出它，因为暂存区没动（偏离 1） |
| 4 个旧变量退役 | `.env.example` §12 新增一段；`tests/test_env_example.py` 的 `RETIRED` | P0b 阶段不提新名（Q14）；P1 合入时再补一句"OMICSCLAW_SKILL_ENV (section 4) replaces them" |
| 旧提案状态行 | `docs/proposals/adaptive-environment-provisioning.md` 文首 | 写明实现已随 runner 删除，运行期供给见 0061 |
| `AGENTS.md` 中 `remote/` 的描述 | 结构树 | 按实测改写：`OmicsClaw` 环境下，12 个叶子模块里 5 个可 import（schemas、auth、storage、routers.connections、routers.sessions），另 7 个卡在已删除的 `omicsclaw.control` 或 `omicsclaw.diagnostics` 上；rapids 环境缺 fastapi/pydantic，只有 storage 可 import。与 F15 一致 |
| `AGENTS.md` 中 `diagnostics.py` 的条目 | 结构树 | 删掉这一行，`surfaces/` 改为最后一项（`└──`） |
| `0_setup_env.sh` 的 "4 tiers" 注释 | 文件头 | 改为 5 tiers，并补上 Tier 5（只在 `--with-banksy` 或 `OMICSCLAW_WITH_BANKSY=1` 时运行）；`bash -n` 语法检查通过 |
| F58 逐条人工确认 | 6 个 `SKILL.md` 的包名行（只改正文包名行，按大小写不敏感排序插入） | 见下表 |

**F58 逐条确认**（Q3 = b：漏报靠补声明，或进例外表）：

| skill | 键 | 证据 | 处置 |
|---|---|---|---|
| spatial-domains | cellcharter | `_lib/domains.py` 里 `require("cellcharter")`；脚本支持 `cellcharter` 方法 | 补声明 |
| spatial-integrate | scanorama | `_lib/integration.py` 中 `SUPPORTED_METHODS = ("harmony","bbknn","scanorama")` | 补声明 |
| sc-clustering | louvain | 脚本自己调用 `sc_dep_manager.is_available("louvain")`（`--cluster-method louvain`） | 补声明 |
| sc-integrate-cluster | scvi-tools | `--method scvi` 走 `_lib/integration.py` 的 scVI | 补声明 |
| sc-enrichment | gseapy | `_lib/stat_enrichment.py` 在 `get_dependency("gseapy")` 后走 prerank 与远程基因集；脚本的复现依赖清单也列了 gseapy | 补声明（复跑新发现） |
| spatial-enrichment | gseapy | `_lib/enrichment.py` 有 4 处 `get_dependency("gseapy")`（enrich/prerank） | 补声明（复跑新发现） |
| sc-qc / sc-filter / sc-preprocessing / scatac-preprocessing | scrublet | 这 4 个脚本只用 `_lib/qc.py` 的 metrics、filter、plot 函数；带 scrublet 调用的 `calculate_doublet_scores`、`run_scrublet_detection` 只有 `sc-doublet-detection` 在调用（grep 核对过） | 进 P1 一致性测试的 `EXCEPTIONS`，附理由 |

补完后声明名从 63 个变成 **64 个**（新增的名字只有 `cellcharter`，其余 5 个此前已有别的 skill 声明过），与计划用例 5"补 cellcharter 后 64 个"一致。回落集合仍是那 16 个。

### 3.3 验收证据

| 检查 | 结果 |
|---|---|
| `$PYT $BASE` | **2200 passed, 17 skipped**（101.9 s），与开工基线相同 |
| 用例 4 的变异 | 从 `.env.example` 删掉一个退役名 → 红；把退役名改成 `#OMICSCLAW_ADAPTIVE_ENV=on` 这种赋值形式 → 红 |
| F58 复跑（补声明后） | 只剩 4 个 scrublet 例外项 |
| 0062 的 `tests/sdk` | 包含在 `$BASE` 里，全绿 |

## 4. P1

### 4.1 先红

改 `use_skill` 之前，先用未改动的工具录下 `tests/skillenv/fixtures/golden/use_skill_off.txt` 与 `use_skill_definition.json`（用例 11 需要的"改动前字节"）。随后写完 P1 的全部测试并运行：**5 failed、7 个收集错误**（`omicsclaw.skillenv` 与 `annotate=` 都还不存在）。

### 4.2 实施

- **`omicsclaw/skillenv/registry.py`**：
  - 包名行解析：`DependencyFormatError`，报错写明文件与行号。
  - `read_registry`：用 AST 找 `DEPENDENCIES`（`AnnAssign` 与普通 `Assign` 都认），再 `ast.literal_eval`，并按 0062 用例 22 的同一组字段约束做契约校验。任何不满足都抛 `RegistryFormatError`，写明文件与行；文件不存在时给出 §4.2 规定的 skills_dir 报错原文。
  - `resolve`：顺序是键 → PEP 503 规范化键 → `module`；回落按本侧规则推导 import 名（两项小表，否则 `-` 换 `_`）。
  - `Resolution.distributions`：返回 `[键, *also]`。
  - `probe_plan`：`r` 类不进 imports。
- **`omicsclaw/skillenv/probe.py`**：
  - 固定探针代码，只用标准库，按 3.8 语法写（`ast.parse(feature_version=(3,8))` 核验通过）。
  - `probe_command` 以 `cd <skill 目录> 2>/dev/null || true;` 开头；`probe_argv` 与它共用同一份代码和 JSON。
  - `parse_probe`、`run_probe`。
  - `LocalProbeRunner` 走 `bash -c` 并建新进程组，超时杀整组，返回 124；`SandboxProbeRunner` 调 `run_bash`，有 env 时写成 `env K=V … bash -c '<命令>'`。
  - 探针超时 10 s。
- **`omicsclaw/skillenv/report.py`**：`render_annotation` 是纯函数，文案按 §4.4。总长上限 1500 字符，超出时缺项只列名。
- **`omicsclaw/skills/use_skill.py`**：
  - 新增 `annotate=`（`Annotator = Callable[[Skill, str], Awaitable[str]]`）。
  - 为 `None` 时仍走原来的同步路径，输出逐字节不变。
  - 读取拆成 `_read` 与 `_located`，两条路径共用；回调收到的正文就是本次读出的那一份。
  - 回调抛异常时追加 `---\nEnvironment check unavailable: <原因>`。
  - `omicsclaw/skills` 没有 import `skillenv`。
- **`omicsclaw/entry/config.py`**：
  - 新增 `SkillEnvMode`（`off`、`probe`）与 `AppConfig.skill_env`，默认 `probe`。
  - `_Option("skill_env", "--skill-env", ("OMICSCLAW_SKILL_ENV",))`。
  - 取值 `install` 报 "skill_env=install is not available in this version; use probe or off"。
- **`omicsclaw/entry/skill_env.py`**：
  - `build_skill_env(config, skills, binding)`：registry 路径取 `skills.root / "_sdk" / "deps.py"`，启动时读一次；读不出就记 warning 并降级。沙箱运行时用 `SandboxProbeRunner`，并带上 `SandboxContext`（镜像、是否断网、网络名）；read-only 模式不产出回调。
  - `log_skill_env`：输出 `skill_env=… location=… python=…` 一行，并在三个解释器不一致时告警。
- **`omicsclaw/entry/assembly.py`**：
  - `foundation_tools(..., skill_env=)` 把回调交给 `use_skill_tool`。
  - `build_app` 只在 `tools is None` 时构建，结果放在 `AgentApp.skill_env`（带默认值的新字段）。
  - `open_app` 的 `_swept` 在内存维护之后调用 `log_skill_env`。
- **测试**：`tests/skillenv/` 下 10 个测试文件，外加夹具（一个 demo skill 与一份夹具 registry）；`tests/entry/test_entry_is_the_top_layer.py` 的 `_LOWER_LAYERS` 加上 `"skillenv"`。
- **文档与配置**：
  - `.env.example` 第 4 节加 `#OMICSCLAW_SKILL_ENV=probe` 及说明，§12 的退役段补一句由它取代。
  - `tests/test_env_example.py` 的 `READ_BY_THE_STACK` 加 `OMICSCLAW_SKILL_ENV`。
  - `pyproject.toml` 第 77–79 行的注释改为指向 `skills/_sdk/deps.py` 的 `kind="git"`。
  - `AGENTS.md` 结构树加 `skillenv/` 一行（偏离 5）。
  - `README.md` 加里程碑一条。

### 4.3 §5 P1 验收逐条

| 验收项 | 证据 |
|---|---|
| `off` 时 `use_skill` 输出与改动前逐字节相同 | `test_use_skill_annotation.py::test_without_a_callback_the_output_is_unchanged`（工具层）；`test_entry_skill_env.py::test_off_leaves_use_skill_byte_identical`（经 `build_app` 装配，比对改动前录下的字节） |
| `off`/`probe` 的系统提示与工具表都等于 golden | `test_prompt_and_tools_equal_the_golden_deployment[off/probe]`，比对 `tests/entry/golden/ensemble_off_{prompt.txt,tools.json}`；golden 文件未改 |
| 本机与假 `BashEnvironment` 两条探针路径 | `test_probe_runners.py`（本机：`PATH` 前置的假 `python` 被探到；沙箱：命令、cwd、timeout 原样传入，env 以前缀形式出现）；`test_local_and_sandbox_bindings_pick_their_runner` |
| 工作区 `json.py` 不被执行，工作区 `cellbender/` 不致误报 | `test_probe.py::test_workspace_code_is_not_executed`（标记文件不出现，`cellbender` 仍报缺失） |
| read-only 不附注记 | `test_read_only_gets_no_note` |
| 探针失败时仍返回正文，带"不可用"一行 | `test_a_failing_callback_still_returns_the_body`；`test_report.py::test_an_unavailable_probe_is_one_line`；`run_probe` 非零退出与超时都抛 `ProbeError`，由注记渲染成一行 |
| 格式契约覆盖 94 个文件 | `test_dependencies_section.py`（94 个参数化用例、64 个名字、6 种畸形各自报错且带文件路径） |
| registry 读出真实 61 键，子进程里没有 `skills` 模块 | `test_registry_reader.py::test_reading_imports_nothing_from_skills`（子进程输出 `[61, []]`）；读出结果与 `import skills._sdk.deps` 相等 |
| 声明名的回落集合等于冻结表 | `test_the_declared_fallback_names_are_frozen`（16 个，与复跑一致） |
| 一致性测试除具名排除和例外外全绿 | `test_skill_requires_are_declared.py`：1 个排除模块、4 个例外，全绿；例外过期也会变红 |
| `sandbox_code_in_image` 情形仍给出结果 | `test_a_skill_directory_absent_here_leaves_the_probe_in_the_workspace`；`test_the_skill_directory_is_the_working_directory_when_it_exists` 的第二段（目录不存在时 cwd 为工作区） |
| 0062 的 `tests/sdk` 仍绿，尤其 B4 | 包含在 P1 命令内，全绿；B4 已知项仍只有 `autoagent/metrics_compute.py` |

### 4.4 命令与结果

| 检查 | 结果 |
|---|---|
| §6 P1：`$PYT tests/skillenv $BASE` | **2400 passed, 17 skipped**（110.9 s）。比基线多 200 个：`tests/skillenv` 197 个，`_LOWER_LAYERS` 新增的 skillenv 参数化 3 个 |
| 相关套件：`tests/entry tests/launch tests/ensemble tests/subagent`（非 slow） | 2103 passed, 7 skipped |
| 全量回归 | `214 failed, 6376 passed, 46 skipped, 16 deselected, 42 errors`；**新增失败为空**；消失的只有 `ERROR tests/test_adaptive_env_phase3.py` |
| 读 README/AGENTS 的文档测试 | 7 failed，全是已知的 `test_control_plane_documentation_contract.py`，其余通过 |
| 真实注记样例（`OmicsClaw` 为 `bash` 的 python） | `spatial-domains` 用时 0.04 s、512 字符，git 类两项给出了 registry 命令和 `omicsclaw_banksy`；`genomics-variant-annotation` 为 "2 of 2" |

`spatial-domains` 的注记原文如下（与计划 §4.4 的示例一致）：

```
---
Environment check (the `python` bash runs here: /opt/conda/envs/OmicsClaw/bin/python, Python 3.11.15)
- 15 of 17 packages under "## Dependencies" are importable.
- Missing, git-only (install_skill_deps cannot install these): pybanksy (import banksy) — pip install git+https://github.com/prabhakarlab/Banksy_py.git, or the conda env `omicsclaw_banksy`; STAGATE-pyG (import STAGATE_pyG) — pip install git+https://github.com/RucDongLab/STAGATE_pyG.git
- Methods that do not use a missing package are unaffected.
```

## 5. 变异验证（§6.2 中与 P0b、P1 相关的条目）

方法与 0062 相同：用会话临时目录里的脚本对单个文件做替换，跑指定测试，再按字节恢复。每条跑完都核对了工作树已复原。

| 变异 | 结果 | 变红的测试 |
|---|---|---|
| `find_spec` 抛异常改判为缺失 | 红 | `test_a_find_spec_that_raises_counts_as_present` |
| 探针不剔除 `''` | 红 | `test_workspace_code_is_not_executed` |
| 探针 cwd 改回工作区（去掉 `cd`） | 红 | `test_the_skill_directory_is_the_working_directory_when_it_exists` |
| `off` 时仍附注记（等价于"`annotate` 缺省不为 `None`"） | 红 | `test_off_leaves_use_skill_byte_identical` |
| read-only 仍附注记 | 红 | `test_read_only_gets_no_note` |
| `skillenv` import `entry` | 红 | `test_skillenv_is_a_layer` ×2、`test_entry_is_the_top_layer[skillenv]` ×2 |
| registry 改为 `import skills._sdk.deps` 读取 | 红 | 分层测试；`test_reading_imports_nothing_from_skills` |
| 有回调时工具描述变化（即 `off/probe` 下工具表变化） | 红 | `test_the_definition_does_not_depend_on_the_callback`、golden[probe] |
| 类别改回从 `install` 字符串推断 | 红 | `test_the_category_is_the_kind_field` |
| 安装展开改为解析 `install` 字符串 | 红 | `test_expansion_ignores_the_install_string` |
| `module` 反查排在规范化匹配之前 | 红 | `test_normalised_match_comes_before_the_module_lookup` |
| 去掉 `module` 反查 | 红 | resolution[scvi/tangram/paste] |
| 回落改用"名字本身" | 红 | fallback[PyYAML/scikit-learn/a-b] |
| 新增只能靠回落解析的声明名却不改冻结表 | 红 | `test_the_declared_fallback_names_are_frozen`、`test_the_declared_names_number_64` |
| registry 不是字面量时静默当空表 | 红 | 契约[call/lambda] |
| 对 `r` 类名字做 `find_spec` | 红 | `test_probe_inputs_skip_r_packages_and_use_modules`、`test_r_packages_are_named_and_not_probed` |
| 沙箱运行时注记仍指向宿主 overlay | 红 | `test_an_existing_overlay_is_named_locally_only` |
| 接受 `install` | 删掉拒绝分支 → 红（`test_install_is_refused_until_it_exists`）；只往枚举里加 `INSTALL` → 绿，因为拒绝分支在枚举之前，行为不变 | — |
| 从 `spatial-domains` 删掉 `cellcharter` | 红 | 一致性测试、声明名计数 |
| 往例外表加一个不存在的 skill | 红 | `test_every_exception_is_still_needed` |
| 不收集 `deps` 模块别名形式的调用 | 红 | `test_an_aliased_deps_module_is_collected`、`test_every_exception_is_still_needed` |
| 回调异常时丢掉正文（改为 raise） | 红 | `test_a_failing_callback_still_returns_the_body` |
| 超时只杀 shell、不杀进程组 | 红 | `test_a_probe_past_its_limit_is_killed_with_its_group` |
| 去掉 1500 字符上限 | 红 | `test_the_note_is_capped_and_long_lists_keep_only_names` |
| P0b：`.env.example` 删掉退役名 / 把退役名写成可设置的赋值 | 红 / 红 | `test_a_retired_variable_is_named_but_never_offered` |

"接受 `install`"最初的变异写法只是把拒绝分支的条件改掉，测试没有变红：枚举本身也会拒绝 `install`，测试又没钉住报错文字。之后改了测试，单独用 `test_install_is_refused_until_it_exists` 钉住报错信息，这条变异随即变红。

§6.2 其余条目都属于 P2 或 P3（overlay、安装、pip、锁、Desktop、`ensemble` import、`provenance`），本次不做。

## 6. 偏离与理由

1. **删除与改名只动工作树**：派发规则禁止 `git add`，所以 `tests/test_adaptive_env_phase3.py` 是用 `rm` 删的。计划的验收写的是"`git ls-files` 为空"，这要等暂存或提交之后才成立；现在的证据是 `git status` 显示 ` D`、文件已不在盘上、全量回归里对应的收集错误消失。
2. **F58 的复跑比计划多出 2 处**（gseapy ×2）：0062 F29 的规则把"从依赖模块 import 的 `get`"也计为调用，这两处是它带出来的。两处都是真实依赖，所以补了声明，而不是放进例外表。计划写"以复跑结果为准"，这里照做。
3. **一致性测试只看主脚本直接 import 的 `_lib` 模块**，不做传递展开，与 F58 的口径"它 import 的 `skills.<domain>._lib.<模块>`"一致。`from skills.<d>._lib import <子模块>` 的写法按子模块文件计入。
4. **本机探针的环境用 `without_control_credentials()`**：计划写"继承 agent 进程环境"。0062 之后，`bash` 本机路径本身就剔除控制面凭据，探针用同一份环境，才真正等于"`bash` 实际会用的环境"。差别只在那一个凭据名上。
5. **`AGENTS.md` 结构树在 P1 就加了 `skillenv/` 一行**：计划把 AGENTS.md 的改动放在 P2，但 P1 已经新增了这个包，SPEC 要求结构变化同步写进 AGENTS。只加了一行描述，P2 规定的其他 AGENTS 改动（"Nothing installs from the section" 的改写、`bash(pip install*)` 的说明等）都没提前做。
6. **P1 只加了 `skill_env` 这一个配置项**：§4.10 表里的 `skill_env_dir`、`skill_env_install_timeout_s` 只服务于安装，按 §5 P1 的清单（只列 `AppConfig.skill_env`）留给 P2。
7. **没有实现 `find_overlays` 与 pyproject 版本约束**：两者都属于安装链路，P1 里 overlay 不可能存在。`render_annotation` 保留了 `overlays=` 和 `install_tool=` 两个参数，用例 10 覆盖了渲染；entry 目前不传这两个参数。
8. **启动日志的 python 通过一次探针取得**（在 `open_app` 的 `_swept` 里跑，imports 为空）：
   - 本机时与 `sys.executable` 比较，沙箱时不比较，因为容器内解释器不可比；
   - 与 `ensemble_python` 的比较只在它是绝对路径时做；
   - 比较用 `realpath`，避免同一解释器的不同符号链接被误报；
   - read-only 加沙箱时不跑探针，日志记 `python=unchecked`，与"read-only 不附注记"的理由相同：沙箱里的 `run_bash` 会写文件；
   - `build_app` 本身不起子进程。
9. **用例 6b 的 `install` 一半**：P1 期间 `install` 在解析阶段就被拒绝，"registry 不可读时 install 拒绝启动"要到 P2 才有意义；这里用 `test_install_is_refused_until_it_exists` 代替。
10. **所有 P1 测试都放在 `tests/skillenv/`**，包括计划标注为"entry"的 6b 与 12，这样 §6 的 P1 命令（`tests/skillenv $BASE`）能覆盖到它们。
11. **报告文案的几处取舍**：
    - 沙箱时首行写 "the `python` bash runs in the sandbox: …"；
    - pip 类缺项写成 "Missing: 名 (import 模块)"；
    - 沙箱措辞与 "Methods … unaffected" 只在有缺项时出现；
    - 超过 1500 字符时先改为只列名，仍超出才截断。

    计划只给了本机示例和几句固定文案，其余按最接近的写法补齐，由用例 10 钉住。
12. **`use_skill` 的回调异常只捕获 `Exception`**，取消（`CancelledError`）照常向上传播。

## 7. 改动文件清单

**新增**
- `omicsclaw/skillenv/__init__.py`、`registry.py`、`probe.py`、`report.py`
- `omicsclaw/entry/skill_env.py`
- `tests/skillenv/__init__.py`、`conftest.py`、`test_dependencies_section.py`、`test_registry_reader.py`、`test_skill_requires_are_declared.py`、`test_probe.py`、`test_probe_runners.py`、`test_report.py`、`test_use_skill_annotation.py`、`test_entry_skill_env.py`、`test_skillenv_is_a_layer.py`
- `tests/skillenv/fixtures/skills/demo/demo-skill/SKILL.md`、`tests/skillenv/fixtures/skills/_sdk/deps.py`、`tests/skillenv/fixtures/golden/use_skill_off.txt`、`use_skill_definition.json`
- `docs/plans/0061-adaptive-env-provisioning-delivery.md`（本文件）

**删除**
- `tests/test_adaptive_env_phase3.py`

**修改**
- 框架代码：`omicsclaw/skills/use_skill.py`、`omicsclaw/entry/config.py`、`omicsclaw/entry/assembly.py`
- 测试：`tests/test_env_example.py`（`RETIRED` 加 4 个名字，`READ_BY_THE_STACK` 加 1 个）、`tests/entry/test_entry_is_the_top_layer.py`（`_LOWER_LAYERS`）
- skill 声明：`skills/spatial/spatial-domains/SKILL.md`、`skills/spatial/spatial-integrate/SKILL.md`、`skills/spatial/spatial-enrichment/SKILL.md`、`skills/singlecell/scrna/sc-clustering/SKILL.md`、`skills/singlecell/scrna/sc-integrate-cluster/SKILL.md`、`skills/singlecell/scrna/sc-enrichment/SKILL.md`（各在包名行加一个名字）
- 文档与配置：`.env.example`、`AGENTS.md`、`0_setup_env.sh`（注释）、`pyproject.toml`（注释）、`docs/proposals/adaptive-environment-provisioning.md`、`README.md`

没有改动 `omicsclaw/ensemble/`、`skills/_sdk/`、golden 文件 `tests/entry/golden/*`、`CLAUDE.md`。

## 8. 遗留

- **P2 与 P3 未做**：P2 排在 0057–0060 之后，需先裁定 Q4–Q10；P3 需 0056 合入，并先裁定 Q16、Q17。§4.12 "对 0059 的要求"是文档交付，由 owner 转给 0059 的作者。
- **P2 还要做的**：
  - `find_overlays`、pyproject 版本约束、`skill_env_dir` 与安装超时两个配置项；
  - AGENTS.md 的其余改动；
  - `install` 模式下"registry 不可读即拒绝启动"。
- **暂存区**：删除和新增都没有暂存；提交前需要 `git add -A`（或逐项添加）。
- **不在本计划范围、未动的残留**（按 §4.8 如实记录）：
  - `remote/` 死代码（Q13 = a，只改了 AGENTS 的描述）；
  - `ensemble/execution.py` 的 `ENV_WHITELIST` 里 4 个死变量名（Q16，建议项，随 0056 终审或 P3 处理）；
  - BANKSY Tier 5 与 `environments/banksy.yml`（Q12 = b，另立小计划）；
  - OmicsClaw-App 仓库里调用 `/env/*` 的 8 处（F57，由 App 仓库处理）；
  - 0062 B2 不扫 `omicsclaw/common`（今天无违例，影响很小）。
- **注记的覆盖面**：只覆盖经 `use_skill` 的路径；子代理预载正文、或直接照 `CLAUDE.md` 写命令的路径看不到注记（F53、§8 非目标）。
- **0062 评估留下的次要清理**：owner 尚未授权，本次没有动。

## 附录 A：复跑脚本

F58、F64 的扫描脚本在会话临时目录 `impl0061/scripts/f58_f64.py`，不入库。做法：
1. 用 `ast.literal_eval` 读 `skills/_sdk/deps.py` 的 `DEPENDENCIES`；
2. 用正则取 94 个包名行；
3. 调用名按 0062 F29 的规则收集（`skills._sdk.deps` 的 `require`/`is_available`/`install_hint`/`get_dependency`/`get`，以及经 `deps` 别名的属性调用）；
4. 对每个 skill，扫它的主脚本和主脚本直接 import 的 `skills.<domain>._lib` 模块，逐项对照该 skill 的声明。

`f64` 模式输出回落集合与各类条目的声明者；`f58 <排除模块…>` 模式输出逐 skill 的漏报。进入仓库的等价实现就是 `tests/skillenv/test_skill_requires_are_declared.py` 与 `test_registry_reader.py::test_the_declared_fallback_names_are_frozen`。

## 评估后清理（2026-09-24，owner 授权）

依据两轮独立评估。按 owner 的要求，这一轮**不跑全量测试**，只跑新增测试和直接相关的目录。变异一律在会话临时目录里的仓库副本（`scratchpad/cleanup/repo`）上注入和还原，不碰活工作树。

| # | 问题 | 处理 | 测试证据 |
|---|---|---|---|
| A1 | `_swept` 把 `log_skill_env` 放在 try 块外面。探针最长会等 10 s，这期间被取消的话，内存数据库不会被关闭，与 docstring 的承诺不符 | 把 `log_skill_env` 移进 `prepare_memory` 所在的同一个 try 块 | `tests/skillenv/test_startup_logging.py::test_a_cancellation_during_the_startup_probe_closes_memory`：让探针永不返回，在它运行时取消，断言 `CancelledError` 向上传播、内存的 `close()` 被调用一次。改之前先确认这个测试是红的 |
| A2-M6 | 本机探针子进程是否剔除控制面凭据，没有测试钉住 | 只加测试 | `test_the_local_probe_does_not_inherit_the_control_credential`：大小写两种拼法的 token 都不在子进程环境里，哨兵变量照常存在 |
| A2-M11 | read-only 加沙箱时仍会跑探针，没有测试钉住 | 只加测试 | `test_read_only_in_a_sandbox_runs_no_probe`：假 `BashEnvironment` 一次都没被调用，日志恰为 `skill_env=probe location=sandbox python=unchecked` |
| A2-M12 | `_swept` 不调用 `log_skill_env` 时，没有测试会变红 | 只加测试 | `test_open_app_writes_the_startup_line`：走完整的 `open_app`，启动日志里有 `skill_env=probe location=local python=/…`。A1 的测试给等待加了 15 s 上限：探针没启动时直接失败，不会一直挂住 |
| B1 | 探针失败时，注记丢掉了"registry 不可读"那一行 | `render_annotation` 在 `result is None` 时也输出 `dependency registry unreadable` 行；`skill_env._annotator` 把 `registry_error` 传进去 | `test_report.py::test_an_unreadable_registry_is_still_said_when_the_probe_fails`；`test_entry_skill_env.py::test_an_unreadable_registry_is_kept_when_the_probe_fails`。两者先红后绿 |
| B2 | skills_dir 下没有 registry 时，报错写"install_skill_deps needs that registry"，但 P1 并没有这个工具 | 措辞改为 "…not an OmicsClaw skills tree with `_sdk/`, so there is no dependency registry to read"，行为不变 | `test_registry_reader.py::test_a_missing_file_says_the_skills_dir_is_not_a_skills_tree` 加两条断言：信息里不出现 `install_skill_deps`，并含新措辞。先红后绿 |

**变异结果**（在副本上，每条跑 `tests/skillenv`）：

| 变异 | 结果 | 变红的测试 |
|---|---|---|
| M6：`LocalProbeRunner.run` 改用 `dict(os.environ)` | 红 | `test_the_local_probe_does_not_inherit_the_control_credential` |
| M11：read-only 加沙箱时仍跑探针（条件改成 `if True:`） | 红 | `test_read_only_in_a_sandbox_runs_no_probe` |
| M12：`_swept` 不调用 `log_skill_env` | 红 | `test_open_app_writes_the_startup_line`、`test_a_cancellation_during_the_startup_probe_closes_memory` |
| A1 回退：`log_skill_env` 移回 try 外 | 红 | `test_a_cancellation_during_the_startup_probe_closes_memory` |
| B1 回退：`_annotator` 不传 `registry_error` | 红 | `test_an_unreadable_registry_is_kept_when_the_probe_fails` |
| B1 回退：`render_annotation` 在 `result is None` 时不输出那一行 | 红 | 上一条，以及 `test_an_unreadable_registry_is_still_said_when_the_probe_fails` |
| B2 回退：恢复旧措辞 | 红 | `test_a_missing_file_says_the_skills_dir_is_not_a_skills_tree` |

变异过程中有一次意外。第一次跑 M12 时，取消测试还没有等待上限，一直挂住；中止挂住的运行后，副本里的 `assembly.py` 与 `skill_env.py` 停在了变异状态。当时逐行核对过：活工作树里这两处都是正确代码。随后从活工作树重新同步副本，把 7 条变异全部重跑，得到上表。那次中止时，B2 的首次结果受到污染，已作废。

**所跑测试**：
```
PYTHONDONTWRITEBYTECODE=1 /opt/conda/envs/rapids_singlecell/bin/python -m pytest -p no:cacheprovider -q -o addopts="" -p no:randomly -m "not slow" \
  tests/skillenv tests/sdk tests/launch tests/entry/test_assembly.py tests/entry/test_open_app.py tests/entry/test_config.py \
  tests/entry/test_ensemble_golden.py tests/entry/test_entry_is_the_top_layer.py tests/entry/test_permission_wiring.py \
  tests/entry/test_memory_wiring.py tests/ensemble/test_local_executor_credentials.py
→ 873 passed, 6 skipped, 11 deselected
```
其中 `tests/skillenv` 单独为 203 passed。

**文件核实（D）**：`skills/genomics/genomics-qc/SKILL.md` 的 mtime 是 12:32:52，对应 P1 变异"新增只能靠回落解析的声明名"。那一轮是在活工作树上做的；变异脚本在注入前读入原始字节，结束后在 `finally` 里按字节写回。核对结果：
- 在 0062 与 0061 的开工快照（`git status`）里，这个文件都已经是 ` M`，是别人的未提交改动，不是我改的；
- 文件里没有变异注入的 `oc-brand-new-lib`；包名行仍是 `` `numpy`, `pandas` ``；
- F64 复跑仍是 64 个声明名、16 个回落名，与变异前的扫描一致。

结论：内容与开工前一致，只是 mtime 因为按字节写回而更新。

**改动文件**：
- `omicsclaw/entry/assembly.py`（`_swept`）
- `omicsclaw/entry/skill_env.py`（`_annotator`）
- `omicsclaw/skillenv/report.py`（`render_annotation`）
- `omicsclaw/skillenv/registry.py`（报错措辞）
- 新增 `tests/skillenv/test_startup_logging.py`
- 修改 `tests/skillenv/test_report.py`、`test_entry_skill_env.py`、`test_registry_reader.py`

## P3 与 P2 交付（2026-09-25）

**规格**：计划第 7.2 版，含 §9.1 "2026-09-25" 的裁定：Q4–Q10、Q16、Q17、Q27、Q28、Q31、Q33 全部按推荐（Q33 取 a，不加 d1），P2、P3 即刻实施，不等 0057–0060。本节不改计划正文。
**范围**：先 P3（与 0056/0059 对接，在未提交的 0056 工作树上实施），后 P2（本机安装 `install_skill_deps`、`skill_env=install`）。P2 按第 7.2 版（D8/Q34）沿用本机 pip 配置联网安装，没有实现第 7、7.1 版的 `skill_env_*` 来源配置与来源文法，实现了第 7.3 步的安装位置守卫（F93）。
**状态**：P3、P2 都已实施，§5 两个阶段的验收条目逐条满足（见 P3.2、P2.2）。没有 commit，也没有 `git add`。

### P3/P2.0 结论

| 阶段 | 验收结论 | 关键证据 |
|---|---|---|
| P3 | **通过** | §6 P3 命令 **2696 passed, 23 skipped**（211 s）；0056 的 entry 测试加 `tests/launch`：310 passed, 2 skipped；与 P3 相关的 9 条变异全部变红 |
| P2 | **通过** | §6 P2 命令 **2596 passed, 18 skipped**（202 s）；直接相关套件 811 passed, 8 skipped；以 `OmicsClaw` 环境（Py 3.11.15、pip 26.0.1）为 base 跑 `test_overlay_real.py test_install_offline.py`：21 passed，无跳过；真实联网 E2E 手动跑一次通过；§6.2 中适用于 P2 的变异 50 条全部变红 |

### P3.1 实施

- **`omicsclaw/ensemble/runner.py`**：`EnsembleRunner` 新增可选参数 `describe_environment`（类型别名 `EnvironmentDescriber = Callable[[CommandExecutor, str], Awaitable[Mapping[str, Any]]]`，第二个参数是 skill 名）。每个试验在进入各阶段之前调用一次，返回值写进 `provenance.environment`。回调抛异常或超过 `ENVIRONMENT_TIMEOUT_S`（60 s）时记 `{"error": "…"}`，试验照常进行。调用放在原有的 `try` 之内，所以在此期间被取消的试验仍记为 `cancelled`。`ensemble` 没有 import `skillenv`。
- **`omicsclaw/entry/skill_env.py`**：新增 `describe_trial_environment(skills)`，registry 在构造时读一次。回调用 `probe_argv(executor.python, …)` 生成 argv，经 `executor.capture` 执行，不经 shell；cwd 是 skill 目录，`env=None`。返回 `executable`、`version`、`prefix`、`packages`（每个声明的发行包到版本或 `null`，r 类不列）、`missing`（import 不到的声明名）。
- **`omicsclaw/entry/ensemble.py`**：`build_ensemble` 总是注入这个回调（`open_ensemble` 经它，所以两条路径都有）。
- **Q16 第 1 条**：`ensemble/execution.py` 的 `ENV_WHITELIST` 删掉 `OMICSCLAW_ADAPTIVE_ENV`、`OMICSCLAW_SKIP_ADAPTIVE_ENV`、`OMICSCLAW_ENV_DIR`、`OMICSCLAW_RUN_PYTHON`（用例 26）。
- **解释器不一致告警**：`assembly._swept` 改为把 runner 实际用的 `executor.python` 交给 `log_skill_env`，原来交的是配置里的 `ensemble_python`（见偏离 P3-3）。
- **测试**：`tests/ensemble/test_trial_environment.py`（9 个：用假执行器与手写回调，只测 runner 一侧）；`tests/skillenv/test_ensemble_environment.py`（8 个：entry 构造的回调，含一次真实的 fake-domains 试验）。

### P3.2 §5 P3 验收逐条

| 验收项 | 证据 |
|---|---|
| 假执行器下 `trial.json` 含 `provenance.environment`，字段全是名字与版本、无哈希 | `test_the_described_environment_is_recorded_in_trial_json`（假执行器）；`test_nothing_recorded_looks_like_a_content_hash`、`test_a_real_trial_records_its_interpreter`（断言没有 64 位十六进制值） |
| `capture` 收到以 `executor.python` 开头的 argv（用例 25b） | `test_the_probe_is_an_argv_starting_with_the_executor_python`：`argv[0] == executor.python`，`argv[1:3] == ["-B", "-c"]`，共 5 项；cwd 是 skill 目录，`env is None` |
| 探针失败记 `{"error": …}` 且不阻止试验 | runner 侧：`test_a_failing_callback_is_recorded_and_does_not_stop_the_trial`、`test_a_callback_that_hangs_is_cut_off`；entry 侧：`test_a_failing_probe_is_an_error_entry` |
| `ensemble` 仍不 import `skillenv` | `tests/ensemble/test_ensemble_is_a_layer.py`（未改动），变异 M-P3-1 变红 |
| 0056 全部测试仍绿 | `tests/ensemble` 包含在 P3 命令里，全绿；`tests/entry/test_ensemble_{config,golden,wiring}.py` 加 `tests/launch`：310 passed, 2 skipped |
| 用例 26（Q16 采纳建议） | `test_the_retired_runner_variables_are_not_passed_to_trials` ×4 |
| §4.12 对 0059 的要求 | 这是文档交付，已写在计划 §4.12，请协调方转给 0059 的作者；0061 没有实现冻结开关（按 §4.12 的"P3 一律注入"） |

### P2.1 实施

- **`omicsclaw/skillenv/sources.py`**（纯函数）：
  - 需求项文法 `check_requirement`，只允许"名字 + 可选 extras + 可选版本约束"；运算符、逗号、方括号两侧可以有空格，检查通过后删掉空格。
  - 钉版本文法 `check_pin`。
  - 安装位置守卫 `location_settings`：只看键名的最后一段。
  - `config_list_environment`：跑 `pip config list` 时去掉 `PIP_GLOBAL`/`PIP_SITE`/`PIP_USER`（见偏离 P2-2）。
  - pip 环境 `pip_environment`、装后无凭据环境 `clean_environment`。
  - 制品核对 `foreign_reason`：直接 URL、非 archive、非 wheel 都算外来制品。
  - `artifact_source`、`artifact_transport`，都取制品 URL 自身。
  - `redact`：把 URL 里的 userinfo 换成 `***`。
- **`omicsclaw/skillenv/probe.py`**：新增第二个固定程序"inventory"（`BaseInventory`、`inventory_command`、`parse_inventory`、`run_inventory`），按 3.8 语法写。它报告以下内容：
  - base 身份：真实路径、版本、prefix、base_prefix、mtime、平台、机器、pip 版本；
  - 请求模块的缺项；
  - `metadata.distributions(path=site.getsitepackages())` 的原始记录（Name、Version、目录名）；
  - `sys.path` 上的顶层名及其种类（模块、常规包、命名空间）。

  本机实测 `OmicsClaw` 为 base 时得到 541 条记录、4 条无名记录，与 F48 一致。
- **`omicsclaw/skillenv/registry.py`**：新增 `pyproject_constraints`（从 `[project.optional-dependencies]` 取约束，同名以第一条为准，跳过项目自身）和 `requirements`（按 `[键, *also]` 展开，每一项都带上来源说明，供报错时指明是哪个文件的哪一项）。
- **`omicsclaw/skillenv/overlay.py`**：
  - 纯函数：`base_distributions`（同名多条合并；无名记录按目录名解析，解析不出的计数）、`fill_only`、`new_violations`（前后差集）、`overlay_key`、`check_records`（只读本次新装发行包的 `RECORD`）、`default_root`、`list_overlays`；
  - `find_overlays`：先按 meta 筛，有候选时才再跑一次 inventory 比对摘要；
  - `OverlayBuilder.build`：锁在 `<root>/.locks/<key>.lock`，锁内复查 fingerprint，删除半成品；随后依次建 venv、安装位置守卫、before `pip check`、dry-run、只补缺与制品核对、钉版本安装与安装 report 比对、after `pip check`（无凭据环境 + `PIP_CONFIG_FILE=/dev/null`）、`RECORD` 落盘与顶层名核对、验证 import（无凭据环境）、写 `.meta.json`，最后写 fingerprint。整段在 `skill_env_install_timeout_s` 之内；`finally` 里只删除没有 fingerprint 的目录，然后释放锁；
  - `LocalCommandRunner`：超时或取消时杀整个进程组；
  - 所有子进程的 cwd 都是新建的空临时目录，解释器都带 `-I`。
- **`omicsclaw/skillenv/tool.py`**：`install_skill_deps`。
  - schema 与 policy 与 §4.5 逐字段一致。
  - 询问之前依次做：白名单校验（`ToolArgumentError`）、展开与文法检查（不起任何子进程）、一次本机 inventory、venv base 与 pip < 22.2 的拒绝、跳过已存在的包、求 key、快速复用。
  - 卡片按 §4.5 第 6 步第 7.2 版的原文。
  - 安装在 `pause_tool_timeout()` 内进行，并用 `report_progress` 报告阶段。
  - 结果逐项写出 `name==ver`、wheel 文件名、来源，http 制品标 `(plaintext)`；另写保留的 base 版本、新 `.pth`、命名空间目录、验证结果、git 与 R 提示，以及建议命令。
  - 失败结果另附解析出的计划，以及"the method that needs it cannot run here; report this rather than switching to another method"。
- **`omicsclaw/entry/config.py`**：
  - `SkillEnvMode.INSTALL`，删掉 P1 的拒绝分支；
  - 新增 `skill_env_dir`（`--skill-env-dir`/`OMICSCLAW_SKILL_ENV_DIR`）和 `skill_env_install_timeout_s`（`--skill-env-install-timeout`/`OMICSCLAW_SKILL_ENV_INSTALL_TIMEOUT_S`，默认 1800）；
  - 解析器 `_as_positive_float`，另加 `AppConfig.__post_init__`：非正数在任何构造路径上都报 `AppConfigError`。
- **`omicsclaw/entry/skill_env.py`**：
  - `build_skill_env` 在 `install` 且 registry 不可读时抛 `AppConfigError`（Q23）。
  - 挂载按矩阵：`install` 且 `bash` 在本机（沙箱关闭或降级）时挂载，沙箱运行中不挂载。
  - `SkillEnvBinding` 新增 `tool`、`overlay_root`、`environment`。
  - 注记在工具已挂载时写出 install 一行；在本机模式下经 `find_overlays` 写出现成 overlay。
- **`omicsclaw/entry/assembly.py`**：`foundation_tools` 把工具追加在最后（`run_skill` 之后），所以排在 MCP 工具和 `task` 之前。
- **`omicsclaw/launch/_surfaces.py`**：`start_desktop` 在 `skill_env=install` 时拒绝启动（Q6）。检查放在不安全绑定检查之后、依赖检查之前；报错写明没有审批通道，并给出补救办法（`--skill-env probe`，或改用 `oc cli`）。
- **守卫与配置文档**：
  - `tests/launch/test_the_environment_is_read_in_known_places.py`：`REBUILT_PACKAGES` 加 `skillenv`，`ENVIRONMENT_READERS` 登记 `skillenv/probe.py` 并写明理由；
  - `.env.example` 第 4 节补 `install` 的说明，另加两个变量；
  - `tests/test_env_example.py` 的 `READ_BY_THE_STACK` 加这两个变量；
  - `tests/permission/test_foundation_tools_keep_their_prompts.py` 把本工具加进覆盖名单，docstring 写明它在询问前跑一个本机子进程这一例外及理由。
- **文档**：
  - `AGENTS.md`：结构树的 skillenv 一行；"Nothing installs from the section"一句按 Q3 改写；"Running a skill"新增"Missing packages"一段，包含来源沿用本机 pip 配置且未经核对、base 前缀下的 `pip.conf` 对 overlay 不生效、位置类键会被拒绝、不要把 agent 可写目录配成 find-links、`bash(pip install*)` 规则管不到本工具、overlay 可以直接删除、`run_skill` 不安装且会记录环境。
  - `docs/FRAMEWORK-REBUILD.md`：新增 "Step 7.1 — `omicsclaw/skillenv/` (plan 0061)"。
  - `README.md`：新增里程碑一条，并把 P1 条目里"Nothing installs yet …"一句改成与现状一致。

### P2.2 §5 P2 验收逐条

| 验收项 | 证据 |
|---|---|
| 离线 E2E：审批 → 规划 → 只补缺与制品核对 → 钉版本安装与 report 比对 → `pip check` 差集 → 落盘与顶层名 → 验证（无凭据）→ 复用时不问人、不联网 | `test_a_leaf_and_its_dependency_install_verify_and_are_reused`：阶段顺序恰为 venv/config/check/dry-run/install/check/verify；询问时一个安装命令也没跑过（`calls_at_ask == [0]`）；第二次调用换成不含 find-links 的 pip.conf，仍然成功复用，没有询问，也没有任何命令 |
| 拒绝审批零副作用 | `test_a_refusal_has_no_side_effects`（真实 builder：没有命令，overlay 根目录不存在）；`test_a_refusal_changes_nothing_and_runs_no_pip`；`test_a_refusal_through_the_gate_builds_nothing` |
| 来源取自夹具 pip.conf（`PIP_CONFIG_FILE`）且安装成功；卡片写明"未经核对"；http 制品标 `plaintext` | 离线用例全部经夹具 pip.conf；`test_the_card_text`；`test_the_result_lists_wheels_sources_and_plaintext`；真实联网 E2E（下文）是真实的 http 制品 |
| pip.conf 或环境里的 `no-binary`/`PIP_NO_BINARY` 不能让 sdist 被构建（F92） | `test_no_binary_cannot_make_pip_build_a_source_distribution[config/environment]`：`setup.py` 的标记文件没有出现 |
| `target`/`prefix`/`root`/`user`/`src` 在 dry-run 之前拒绝，base 与目标目录未被写（F93） | `test_install_location_settings_are_refused_before_resolving`（pip.conf 的 target/prefix/root/user，环境变量 `PIP_TARGET`/`PIP_PREFIX`）：阶段只有 venv、config，目标目录为空，base 仍然 import 不到；`src` 与其余键在 `test_sources.py` 的纯函数用例里 |
| 不产生需求文件，`--` 之后只有需求 | 成功用例：所有 argv 都没有 `-r`，也没有任何含 `://` 的项；dry-run 的 `--` 之后恰为 `["oc-leaf"]`，安装的 `--` 之后恰为两个 `name==ver` |
| 约束违例、文件与计划不符、直接 URL 都回滚且无残留 | `test_a_new_violation_rolls_back`；`test_a_wheel_swapped_between_resolution_and_installation_rolls_back`（F68，带 build 号的 wheel）；`test_a_dependency_named_by_direct_url_is_refused`；主语是 base 包的违例（F60）由 `test_pip_check_diff.py` 覆盖（夹具与真实 pip 各一条） |
| 装后 `pip check` 与验证 import（含新 wheel 的 `.pth`）看不到代理变量与凭据 | `test_code_run_after_installation_sees_none_of_the_agents_credentials`：`.pth` 至少触发两次，import 触发一次，每一次看到的键名都在白名单内；`HOME` 是临时目录，调用结束后已删除 |
| spec 为直接 URL 或带 `;`/`@` 时在任何子进程之前失败 | `test_a_direct_url_in_the_registry_fails_before_any_process`：探针、命令、审批都是 0 次，本地 HTTP 服务收到 0 个请求；`test_sources.py` 的文法组 |
| cwd 里的 `pip/__main__.py`、`venv/__main__.py` 不被执行 | `test_python_m_hijacks_nearby_are_never_executed`（测试进程的 cwd 与 overlay 根目录的上级各放一套） |
| `PIP_NO_INPUT=1`，遇到 401 不挂起 | `test_a_find_links_server_answering_401_fails_without_waiting`；`test_the_pip_environment_is_the_whitelist_plus_every_pip_variable` |
| Q33 = a：直接 URL 依赖被拒，卡片有说明 | 同上直接 URL 用例（结果写明 "named by oc-near"）；`test_the_card_text` 断言卡片上有那两行 |
| venv base 被拒 | `test_a_virtual_environment_as_base_is_refused`（真实 venv）；`test_install_tool.py` 同名用例 |
| 卡片、结果、`.meta.json`、日志里没有 userinfo | `test_userinfo_is_redacted_wherever_it_appears`；`test_source_and_transport_come_from_the_artifact_url`；成功用例断言 meta 里没有 `@`；`test_the_suggested_command_and_result_carry_no_credentials` |
| 并发同一 key 只建一次 | `test_two_coroutines_install_once`、`test_two_processes_install_once`（两个真实进程共用一个根目录，总共只装一次） |
| 取消后进程组被杀、目录被删、锁被释放 | `test_cancelling_kills_pip_removes_the_overlay_and_frees_the_lock[dry-run/install]`；`test_running_past_the_limit_takes_the_same_path` |
| 预置无 fingerprint 的半成品，下一次锁内清掉再建 | `test_a_half_built_overlay_is_removed_and_built_again` |
| 带 `also` 的条目展开为多个发行包 | `test_an_entry_with_also_installs_every_distribution`（真实安装）；`test_a_registry_entry_expands_to_its_key_and_also`（该条目的 `install` 故意写成 `Rscript …`） |
| 沙箱运行时不挂载；降级按本机 | `test_a_running_sandbox_gets_no_tool_with_or_without_network`；`test_a_degraded_sandbox_is_treated_as_this_machine` |
| golden 插入断言 | `test_install_inserts_the_tool_before_task_and_changes_nothing_else`：系统提示等于 golden；删掉本工具后，工具表逐字节等于 golden；另有 `run_skill` 之后、MCP 之前两条位置断言 |
| `uv` 从未被调用 | PATH 最前放了一个一运行就写标记文件并失败的 `uv`，成功用例断言标记文件不存在 |
| 真实网络 E2E 手动跑一次 | 见 P2.3 |
| 其他：Desktop 拒绝、registry 不可读拒绝、`MOUNTED` 缺省不变、权限矩阵 | `test_the_desktop_refuses_install_before_needing_uvicorn`；`test_install_refuses_to_start_without_a_readable_registry`；`tests/entry/test_permission_wiring.py` 未改动且全绿；`test_install_permissions.py`（default 问，auto-approve/bypass 不问，read-only 拒绝，`ask` 规则在 auto-approve 下仍问且 `ask_every_time`，"always allow" 写出 `install_skill_deps(oc-skill)`，`bash(pip install*)` 的 deny 规则管不到本工具，`install` 配置下挂载名单为 `MOUNTED` 在 `task` 前插入一项且被 gate 包裹） |

### P2.3 命令与结果

| 命令 | 结果 |
|---|---|
| §6 P3：`$PYT tests/skillenv tests/ensemble $BASE`（P3 完成时） | **2696 passed, 23 skipped**（211 s） |
| P3 相关：`tests/entry/test_ensemble_{config,golden,wiring}.py tests/launch` | 310 passed, 2 skipped |
| §6 P2：`$PYT tests/skillenv $BASE`（P2 完成时） | **2596 passed, 18 skipped**（202 s）。比 P1 的 2400/17 多 196 个 passed；多出的 1 个 skip 是需手动开启的联网用例 |
| P2 相关：`tests/launch tests/ensemble tests/entry/test_ensemble_*.py tests/entry/test_config.py tests/entry/test_memory_wiring.py` 以及读 AGENTS/README 的文档测试（`tests/entry/test_display.py`、`test_approval_card.py`、`test_cli_approval_scope.py`、`tests/context/test_context_is_a_leaf_layer.py`、`test_sections.py`、`tests/test_output_ownership_contract.py`） | 811 passed, 8 skipped |
| §6 另一条：`/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -o addopts="" tests/skillenv/test_overlay_real.py tests/skillenv/test_install_offline.py`（以 OmicsClaw 为 base） | **21 passed**，无跳过（54 s）；rapids 版的同两个文件包含在 P2 命令里，全过 |
| 验收之后补的两个用例（真实 builder 的拒绝零副作用、pip.conf 的 `user` 键），加一处健壮性修改（dry-run report 解析失败改为普通失败结果）与测试文件的无用 import 清理，之后跑一次 `tests/skillenv` 加两个守卫文件 | 411 passed, 1 skipped（其中 `tests/skillenv` 为 394 passed, 1 skipped） |
| 真实联网 E2E（手动）：`OMICSCLAW_TEST_NETWORK=1 … tests/skillenv/test_install_network.py` | 1 passed（4.3 s）。以 `OmicsClaw` 为 base，直接用本机 `/root/.pip/pip.conf`（内部代理 `http://10.20.16.126:8081/…` 加 trusted-host），不配任何 OmicsClaw 来源。装上 `mygene 3.2.2`、`biothings_client 0.5.1`，两项 `transport` 都是 `http`，结果标 `(plaintext)`，`kept_from_base` 为空，`pip_version` 26.0.1。第二次调用复用，没有询问。overlay 在 pytest 的临时目录下 |

新测试文件的用例数：`test_sources.py` 61、`test_install_wiring.py` 23、`test_install_tool.py` 21、`test_install_offline.py` 20、`test_fill_only.py` 14、`test_overlay_keys.py` 10、`test_install_permissions.py` 9、`test_ensemble_environment.py` 8、`tests/ensemble/test_trial_environment.py` 9、`test_install_concurrency.py` 6、`test_pip_check_diff.py` 4、`test_records.py` 4、`test_overlay_real.py` 3、`test_install_cancel.py` 3、`test_validate_env.py` 2、`test_install_network.py` 1（需手动开启）。

### P2.4 §6.2 变异结果

方法与 P1 相同：会话临时目录里有一个脚本，把单个或多个精确替换写入文件，运行指定测试（`-x`），再按字节写回并核对。脚本在 `/tmp/impl0061p23/mut/`。P2 的一轮跑完后抽查了 7 处被改过的行，都已复原。

**P3（9 条，全部变红）**

| # | 变异 | 变红的测试 |
|---|---|---|
| M-P3-1 | `ensemble/runner.py` import `omicsclaw.skillenv` | `test_only_permitted_omicsclaw_packages_are_imported[runner.py]` |
| M-P3-2 | 探针改为经 shell 字符串交给 `capture`（用例 25b） | `test_the_probe_is_an_argv_starting_with_the_executor_python` |
| M-P3-3 / 3b | `provenance.environment` 写入内容哈希（新增键 / 或作为包版本的值） | 同上 / `test_nothing_recorded_looks_like_a_content_hash` |
| M-P3-4 | 回调异常不再兜住 | `test_a_failing_callback_is_recorded_and_does_not_stop_the_trial` |
| M-P3-5 | `build_ensemble` 不注入回调 | `test_build_ensemble_always_injects_the_callback` |
| M-P3-6 | 死变量放回 `ENV_WHITELIST` | `test_the_retired_runner_variables_are_not_passed_to_trials[…]` |
| M-P3-7 | `_swept` 改回只比对配置里的 `ensemble_python` | `test_the_startup_warning_compares_the_runner_interpreter` |
| M-P3-8 | 回调不设超时 | `test_a_callback_that_hangs_is_cut_off` |

**P2（50 条，全部变红）**。逐条输出在 `/tmp/impl0061p23/mut/p2_results.txt`，下表是摘要：

| # | 变异（§6.2 对应项） | 变红的测试 |
|---|---|---|
| M01/M02/M03 | pip 环境、装后环境、inventory 漏设 `PYTHONNOUSERSITE` | `test_the_pip_environment_is_…`、`test_the_clean_environment_carries_no_credentials`、`test_the_inventory_runs_without_the_user_site` |
| M04 | 不拒绝 venv base | `test_a_virtual_environment_as_base_is_refused` |
| M05/M05b | 审批前建目录或安装 / 审批前跑 pip 子命令 | `test_install_tool.py` / 离线成功用例的 `calls_at_ask == [0]` |
| M06 | `packages` 可省略 | `test_the_schema_requires_skill_first_and_at_least_one_package` |
| M07/M08/M09 | `fill_only` 不去掉 base 已有者；无名记录、重复记录处理错误 | `test_pertpy_keeps_what_the_base_already_has` |
| M10 | base 清单受 `sys.path`（cwd、`PYTHONPATH`）影响 | `test_the_real_inventory_does_not_depend_on_where_or_how_it_runs`（仓库根目录下有 `omicsclaw.egg-info`） |
| M11 | 去掉 `--only-binary=:all:` | `test_no_binary_cannot_make_pip_build_a_source_distribution[config]` |
| M12 | `pip check` 改为只比行数 | `test_a_violation_whose_subject_is_a_base_package_is_found` |
| M13 | 违例不回滚 | `test_a_new_violation_rolls_back` |
| M14 | pip 环境带上白名单外的变量 | `test_the_pip_environment_is_the_whitelist_plus_every_pip_variable` |
| M15 | 来源 URL 上命令行 | 离线成功用例（argv 里不许有 `://`） |
| M16/M17 | 来源或日志保留 userinfo | `test_source_and_transport_…`、`test_userinfo_is_redacted_wherever_it_appears` |
| M18 | 改用 `uv pip` | 离线成功用例 |
| M19/M20 | key 去掉 base 清单摘要 / mtime | `test_overlay_keys.py` |
| M21 | 锁文件放回 key 目录 | 离线成功用例（锁在 `.locks/`） |
| M22 | 锁内不复查 | `test_two_coroutines_install_once` |
| M23 | 回滚删除已有 fingerprint 的目录 | `test_two_coroutines_install_once` |
| M24/M25 | 取消时不杀进程组 / 不删半成品 | `test_cancelling_kills_pip_…[dry-run]` |
| M26 | 不按 `RECORD` 查顶层名碰撞 | `test_a_module_hiding_one_the_base_has_rolls_back` |
| M27 | 沙箱运行时仍挂载安装工具 | `test_a_running_sandbox_gets_no_tool_with_or_without_network` |
| M28 | Desktop 显式 `install` 不拒绝启动 | `test_the_desktop_refuses_install_before_needing_uvicorn` |
| M29 | 接受白名单外包名 | `test_a_package_not_under_dependencies_is_refused` |
| M30 | `install` 在 registry 不可读时照常启动 | `test_install_refuses_to_start_without_a_readable_registry` |
| M31/M32 | 放过外来制品 / 放过 `is_direct` | `test_a_dependency_named_by_direct_url_is_refused`、`test_direct_urls_non_archives_and_sdists_are_foreign` |
| M33 | 安装 report 不与计划比对 | `test_a_wheel_swapped_between_resolution_and_installation_rolls_back` |
| M34/M35 | 验证 import / 装后 `pip check` 继承 pip 环境 | `test_code_run_after_installation_sees_none_of_the_agents_credentials` |
| M36 | P1 的"install 不可用"分支未删 | `test_install_is_accepted_and_starts` |
| M37 | `.meta.json` 写入制品哈希 | 离线成功用例（全文只允许 `base_dists_sha256` 一个 64 位十六进制值） |
| M38 | spec 文法放过 `@`、`;` 等 | `test_anything_else_is_refused_naming_its_source[…]` |
| M39/M40 | 解释器不带 `-I` / cwd 不是空临时目录 | `test_python_m_hijacks_nearby_are_never_executed` |
| M41 | 不设 `PIP_NO_INPUT` | `test_the_pip_environment_is_…` |
| M42/M43/M44 | 去掉安装位置守卫 / 守卫按值判断 / 守卫放到 dry-run 之后 | `test_install_location_settings_…[target]`、`test_only_the_key_is_read_never_the_value`、`test_install_location_settings_…[target]`（阶段序列断言） |
| M45/M46 | 卡片列出来源 / 卡片提到 hash | `test_the_card_text` |
| M47/47b/47c | 去掉落盘核对 / 不收集越界路径 / 把 ensurepip 装的 pip 当作新装包检查 | `test_records.py` 三个用例 |

另外核对过一条：删掉注记里"只在本机查 overlay"的条件后，渲染层本身也会在沙箱模式下丢弃 overlay（P1 的双层保护），所以最初写的测试仍是绿的。之后在 `test_the_sandbox_note_never_names_a_host_overlay` 里补了"沙箱模式下根本不跑 inventory"的断言，这条变异随之变红。

§6.2 中没有跑的条目及原因：
- "透传 `PIP_*`""去掉 `PIP_CONFIG_FILE=/dev/null`（pip 环境）"：第 7.2 版有意透传、有意不设，计划已在 §6.2 第 7.2 版段落删去；
- "key 里放钉版本"：key 在审批前由请求的 specs 求出，那时钉版本还不存在，这条变异在本实现里没有对应的写法；
- "`annotate` 缺省不为 `None`""read-only 仍附注记""`skillenv` import `entry`"：属于 P1，P1 交付时已验证；
- "`transport` 取来源而非制品 URL 的 scheme"：本实现根本不解析来源，没有可替换的来源 scheme；由 `test_the_transport_is_the_artifact_url_scheme_not_the_index` 钉住取制品 URL 这一点。

### P2.5 偏离与理由

**P3**

1. **P3-1 runner 侧加了 60 s 上限**（`ENVIRONMENT_TIMEOUT_S`）：计划只要求"探针失败不阻止试验"。回调由 entry 注入，runner 不知道它会不会卡住，一个卡住的回调就能拖住试验，所以 runner 自己兜一层上限。entry 的探针本身还有 `PROBE_TIMEOUT_S`（10 s）。
2. **P3-2 `environment` 的字段**：`missing` 记的是声明名（如 `pybanksy`），不是 import 名（`banksy`），因为 trial 记录是给人读的。skill 的 `## Dependencies` 读不出时（例如测试用的 fake-domains 没有这一段），仍然记录解释器，`packages` 为空，另加一个字符串字段 `declared_error` 说明原因。计划列的字段里没有 `declared_error`，它也只是可读文字，不含哈希。
3. **P3-3 解释器不一致告警**：`_swept` 改为比对 runner 实际用的 `executor.python`。原来比对的是配置里的 `ensemble_python`，未配置时为空，本机默认的 `sys.executable` 就比不到；沙箱里 executor 的 python 是相对名 `python`，照旧不比。
4. **P3-4（按裁定不实施，不属偏离）§4.12 对 0056 的第 5 条（试验环境加 `PYTHONNOUSERSITE=1`）**：owner 2026-09-26 裁定它不在已批准范围内、不实施（计划 §9.1 的 2026-09-26 条）。第 1 条（删死变量）做了：依据是 Q16"按推荐"（第 1 条为建议）加"授权 P3 补"，§4.8 也写明可以"随 P3 处理"。

**P2**

5. **P2-1 环境变量的来源**：计划 §4.10 写的是"由 entry 从交给 `main()` 的环境映射里取出后注入"，但 `build_app`、`open_app` 拿不到那份映射。entry 改为注入 `tools.builtin.bash.without_control_credentials`：它是 `bash` 本机路径取环境的同一个函数，返回当前进程环境（launch 已把 `.env` 合并进去）去掉控制面凭据后的副本，每次安装时调用。这样 `skillenv` 与 `entry` 都不直接写 `os.environ`；`ENVIRONMENT_READERS` 只新增 `skillenv/probe.py` 一项，`tools/builtin/bash.py` 原本就已登记。overlay 缺省根目录用同一份环境里的 `XDG_CACHE_HOME`/`HOME`。
6. **P2-2 新发现：`PIP_USER`/`PIP_GLOBAL`/`PIP_SITE` 会收窄 `pip config list` 的输出**。这三个变量对应的是 `pip config` 命令自己的 `--user`/`--global`/`--site`。实测 pip 25.3：pip.conf 里有 `install.target`，设 `PIP_USER=1` 后 `pip config list` 只列出 `:env:` 项，`install.target` 看不到。`PIP_USER` 本身在守卫里就会被拒；另外两个对 `pip install` 不起作用，却能让守卫漏看。所以跑 `config list` 时从环境里去掉这三个（`config_list_environment`），装的时候不去。计划没有写这一点。
7. **P2-3 `RECORD` 核对只读本次新装的发行包**：计划原文就是"新装发行包"。实现初版读了 overlay 里的全部 dist-info，结果 `ensurepip` 装进 overlay 的 pip 被当成"遮蔽 base 的 pip"而回滚（`test_a_base_without_pip_gets_an_overlay_with_its_own_pip` 发现），随即改正，并加了变异 M47c。
8. **P2-4 base 顶层名取自 base 的整个 `sys.path`**：包括标准库、lib-dynload，以及 agent 环境里的 `PYTHONPATH`。与 F63 的口径一致（F63 把标准库的 `test` 算作 base 顶层名）。这样偏保守：新包里与标准库同名的模块会被判为遮蔽而回滚，尽管标准库在 `sys.path` 上排在 site-packages 之前，实际并不会被遮蔽。同理，inventory 像运行脚本一样把 skill 目录放在 `sys.path[0]`，skill 目录里的子目录（例如 `tests/`）也算作 base 顶层名，所以带同名顶层包（如 `tests`）的 wheel 也会被判为遮蔽而回滚（评估 m3）。行为保持不变。
9. **P2-5 `find_overlays` 的签名**：实际是 `(root, 探针结果, 缺失的声明名, runner, cwd=…)`，按"overlay 的包与缺项有交集"匹配，不按 skill 名，因为别的 skill 建的 overlay 同样能用。计划写的是 `(root, base_state, skill)`。先比 meta 里的路径、版本、prefix、mtime，只有筛出候选时才再跑一次 inventory 比摘要，这一点与计划一致。
10. **P2-6 询问前的额外拒绝**：base 的 pip 低于 22.2 时，在询问前拒绝（R12"报无法规划"）。询问前还做了文法检查：spec 不合文法时返回普通结果，不抛 `ToolArgumentError`，因为问题出在仓库文件（pyproject 或 registry），不在这次调用的参数。
11. **P2-7 只补缺后没有要装的**：dry-run 显示请求的包 base 都已"满足"，而模块仍 import 不到（元数据与实际不符）时，按失败处理并附上计划，不写"无需安装"：否则会建出一个空 overlay 并谎称装好了。
12. **P2-8 结果措辞**：
    - 保留项写成 "the index wanted X; the base records A, B (ambiguous metadata) — kept as is"，没有写计划示例里的"import 实际得到 0.43.0"：那需要再起一个探针，价值不大。
    - 验证结果逐个列出请求的模块，其余 import 不到的模块只列名字。
    - 失败日志尾部不收 `pip config list` 与 `pip check` 的原文：前者可能带来源 URL，虽已去 userinfo，但与失败无关；后者的 base 违例会淹没真正的错误。新增的违例单独列出。
13. **P2-9 正数上限的检查位置**：除了解析器之外，还加了 `AppConfig.__post_init__`，覆盖直接构造 `AppConfig` 与 `resolve_app_config(…, 关键字覆盖)` 两条路径。计划写的是"放在 resolve_app_config/AppConfig 一侧"。
14. **P2-10 Desktop 拒绝的检查点**放在 `start_desktop` 里 `--help` 之后，因为看帮助不应被拒；报错文字避免以 flag 开头，以满足 `test_the_shell_names_no_deployment_flag` 的约束。
15. **P2-11 TDD 顺序**：以下部分是先写测试、先看到红再实现的：P3 全部；P2 的 `sources.py`、`fill_only`/`pip check` 差集/key（红为模块不存在）、entry 装配与配置（`test_install_wiring.py` 18 个失败）、`.env.example`、环境读取守卫。`tool.py` 与 `OverlayBuilder` 的构建流程是先写出实现、后补测试，严格说违反了先红后绿，这里如实记录。弥补办法是 P2.4 的 50 条变异全部变红。另外，这些测试第一次运行就发现了一处真实缺陷（偏离 P2-3）。
16. **P2-12 测试位置**：P2 的测试都放在 `tests/skillenv/`（外加对 `tests/permission/`、`tests/launch/`、`tests/test_env_example.py` 的改动），这样 §6 的 P2 命令能覆盖到它们。计划用例 22、23 标注的是"权限""装配"。

### P2.6 改动文件清单

**新增**
- 生产代码：`omicsclaw/skillenv/sources.py`、`overlay.py`、`tool.py`
- 测试：
  - `tests/ensemble/test_trial_environment.py`
  - `tests/skillenv/` 下：`test_ensemble_environment.py`、`test_sources.py`、`test_fill_only.py`、`test_pip_check_diff.py`、`test_overlay_keys.py`、`test_overlay_real.py`、`test_install_offline.py`、`test_validate_env.py`、`test_install_concurrency.py`、`test_install_cancel.py`、`test_install_tool.py`、`test_install_permissions.py`、`test_install_wiring.py`、`test_records.py`、`test_install_network.py`
  - 测试辅助模块：`tests/skillenv/installing.py`、`wheels.py`
  - 夹具：`tests/skillenv/fixtures/reports/`（`mygene.json`、`pertpy.json`、`direct_url.json`、`pip_check_before.txt`、`pip_check_after.txt`，取自计划实验在 `/tmp` 留下的 report，JSON 只保留名字、版本、`requires_dist`、URL、`archive_info`、`is_direct`、`requested`）

**修改**
- 生产代码：
  - `omicsclaw/skillenv/probe.py`（inventory）、`registry.py`（pyproject 约束与展开）、`__init__.py`（仅 docstring）
  - `omicsclaw/entry/skill_env.py`、`entry/config.py`、`entry/assembly.py`、`entry/ensemble.py`
  - `omicsclaw/launch/_surfaces.py`
  - `omicsclaw/ensemble/runner.py`、`ensemble/execution.py`
- 测试：
  - `tests/skillenv/test_entry_skill_env.py`（P1 的 `test_install_is_refused_until_it_exists` 改写为 `test_install_is_accepted_and_starts`）
  - `tests/permission/test_foundation_tools_keep_their_prompts.py`
  - `tests/launch/test_the_environment_is_read_in_known_places.py`
  - `tests/test_env_example.py`
- 文档与配置：`.env.example`、`AGENTS.md`、`README.md`、`docs/FRAMEWORK-REBUILD.md`、本交付记录

没有改动 `CLAUDE.md`、`tests/entry/golden/*`、计划正文、`skills/**`。

### P2.7 遗留

- **§4.12 对 0059 的要求**是文档交付，请协调方转给 0059 的作者。冻结运行时不注入 `describe_environment` 这一条由 0059 实现，P3 目前一律注入。
- **沙箱路径只用假 `BashEnvironment` 测过**：包括 P3 的 `SandboxExecutor.capture` 探针，以及 P2 的"沙箱不挂载""沙箱注记不找 overlay"。本机没有容器运行时，这一点与 0056 的遗留相同。
- **R29 的剩余风险按 Q33 = a 接受**：离线用例用直接 URL 指向一个 wheel（F67），证明它会被拒绝安装。没有用直接 URL 指向 sdist 来复现"dry-run 期间 `setup.py` 已被执行"（F84）：构建 sdist 需要隔离构建环境里有 setuptools，离线夹具要另外准备。F84 本身在计划的附录 A 里有实测，这里不重复。
- **https 制品只在纯函数层测过**：离线用例都是 `file://`，真实联网用例是内部代理的 http，本机没有离线的 https 源可用。
- **§4.12 对 0056 的第 5 条**（`PYTHONNOUSERSITE`）：owner 2026-09-26 裁定不实施，见 P3-4。
- **base 没有 pip 时，pip 版本下限不生效**（评估 m4）：询问前的"pip 低于 22.2 即拒绝"只检查 base 自己的 pip。base 没有 pip 时，overlay 用 `ensurepip` 自带的 pip，版本由 Python 决定，询问前没有检查。若自带的 pip 低于 22.2（不支持 `--report`），会在审批之后的 dry-run 失败，结果只是一般的"pip could not resolve…"，不是明确的"需要 pip 22.2"。代码未改。
- **Q28 = a**：不做 wheelhouse 与离线重建，base 一变就要重新审批、重新联网（R2）。
- **`README_zh-CN.md` 没有同步**：计划没有要求。
- **`omicsclaw/skillenv/__init__.py` 没有导出新模块的名字**（按 §4.11"不 eager import tool"）。entry 从子模块直接 import。

### 评估后修复（2026-09-26）

独立评估结论为"有条件通过"。按协调方转来的清单逐条修复：每条先写能复现问题的测试、确认变红，再修。约束不变（不 commit、不 `git add`、不改计划正文）。评估方的复现脚本在 `/tmp/eval0061/`，修复后四个脚本都结束于拒绝或成功，没有文件写到 overlay 之外。

**B1（阻断）安装位置守卫可被绕过**
- **问题**：守卫读的是 `pip config list` 的 stdout，而这份输出可能不完整。
  - pip 配置里的 `quiet = 1`，或环境变量 `PIP_QUIET=1`，会让它什么都不打印（退出码 0）。
  - 配置文件 `[global]` 或 `[config]` 段里的 `site = true`、`global = true`，会让它只列出一个文件。
  - `pip install` 不理会这两个键，照常按 `install.prefix` 安装。已复现：包被写到了 prefix 目录下。
  - 另一个后果：安装前的 `pip check` 被 quiet 静默时，base 的既有违例全被当成新增违例。
- **修法**：
  - `sources.config_list_environment`：跑 `pip config list` 时强制 `PIP_QUIET=0`、`PIP_GLOBAL=0`、`PIP_SITE=0`、`PIP_USER=0`，并先删掉 pip 环境里这四个变量的任何大小写写法。环境变量优先于所有配置文件；实测 pip 25.3 下，`[config]` 段的写法与文件里的 `isolated = true` 也都被这些环境变量压过。
  - `sources.location_settings`：跳过列表里的 `:env:` 行，因为它们回显的是 listing 自己的环境，包括强制的 `:env:.user='0'`。环境变量改为直接从 pip 环境判断：凡以 `PIP_` 开头、其余部分按 pip 的规则转小写并把 `_` 换成 `-` 之后属于位置键的，都拒绝。`PIP_Target` 这种写法（pip 同样读取，已实测）在修复前的完整流程里已能被拒绝：pip 把它列为 `:env:.target`，旧代码按列表里的 `:env:` 行拒绝。新加的只是纯函数层对这种写法的直接覆盖。
  - `overlay.py`：安装前的 `pip check` 改为与安装后那次相同的环境，即无凭据环境加 `PIP_CONFIG_FILE=/dev/null`。两次比较的是同样条件下的输出，任何 pip 设置（quiet、python 等）都无法让两次不一致。**这偏离计划 §4.5 第 7.4、7.10 步的原文**（原文让安装前那次用 pip 环境）。理由：前后差集只有在同一条件下才有意义；`pip check` 只读元数据、不联网；那时 overlay 里还没有新代码。没有采用协调方建议的"在 pip 环境里强制 `PIP_QUIET=0`"，因为同一环境比逐个强制更彻底。
  - `OverlayResult.escaped`：失败原因是"文件落在 overlay 之外"或"安装的包不在 overlay 里"时置位。此时 `tool.py` 不再写 "Nothing was changed"，改为说明文件可能已写到 overlay 之外、删除半成品没有清掉它们，并提示检查 pip 配置及其指向的位置（可能包括 base）。
- **新增测试**：
  - `test_install_offline.py::test_settings_that_hide_pip_config_list_output_do_not_hide_a_location_key`，7 个参数：quiet-config、quiet-env、site-global、global-global、site-config、global-config、global-env。
  - `test_install_offline.py::test_a_quiet_pip_does_not_turn_base_problems_into_new_ones`，2 个参数：config、env。
  - `test_sources.py`：`test_environment_lines_of_the_listing_are_judged_from_the_environment_itself`、`test_the_listing_is_read_with_verbosity_and_file_selectors_forced_off`，以及位置变量用例新增的大小写变体。
  - `test_records.py`：已有的落盘用例补了措辞断言。
- **先红后绿**：修前 20 个失败、89 个通过（其中 global-env 修前就能通过，P2-2 已经处理了环境变量这一种；详细清单见 `/tmp/impl0061p23/fix_red.txt`）。修后同一组 109 passed。

**I1（owner 2026-09-26 裁定）pip 的 `python` 选项**
- **修法**：`LOCATION_KEYS` 加入 `python`，`LOCATION_VARIABLES` 随之包含 `PIP_PYTHON`。`python-version`/`PIP_PYTHON_VERSION` 不受影响，有专门用例钉住。AGENTS.md 与 README 的键表同步加上 `python`。
- **新增测试**：
  - `test_install_offline.py::test_pips_python_option_is_refused_before_resolving`，参数 config、environment。用一个 venv 充当另一个解释器，断言安装在 dry-run 之前被拒，那个解释器的 site-packages 没有被写。
  - `test_sources.py` 新增 `global.python`、`PIP_PYTHON`、`PIP_python` 三个参数，以及 `test_pip_python_version_is_not_the_python_option`。
- **先红后绿**：修前两个参数都失败；修前评估方的复现脚本显示包确实装进了那个解释器。

**I2 三条变异补用例**
- **O4**（请求的模块 import 失败也不回滚）：新增 `test_install_offline.py::test_a_module_that_fails_to_import_rolls_back`，用一个 import 时抛 `RuntimeError` 的 wheel。
- **O1**（构建时忽略 `records.outside`）：新增 `test_records.py::test_a_record_naming_files_outside_the_overlay_fails_and_says_so`。安装后往 `RECORD` 追加一条越界路径，断言失败、回滚、措辞正确。
- **G1**（把未过滤的 pip 环境交给 `pip config list`）：由 B1 的端到端用例覆盖。
- **结果**：三条变异逐一注入，都已变红（见下表）。

**次要**
- **m1**：相对路径的 `skill_env_dir` 每次安装都失败，因为子进程的 cwd 是临时目录。修法：`resolve_app_config` 把它 `expanduser().resolve()`；`OverlayBuilder` 构造时也做一次 `expanduser().absolute()`，覆盖直接构造的路径。新增测试 `test_install_wiring.py::test_a_relative_overlay_directory_is_made_absolute` 与 `test_install_offline.py::test_a_relative_overlay_root_works`，修前都失败。
- **m2**：`launch/_surfaces.py` 中 `start_desktop` 的 docstring 从 "Four things" 改为 "Five things"，并写明新增的 `skill_env=install` 拒绝这一步。
- **m3**：见偏离 P2-4 新补的一句，行为不变。
- **m4**：见遗留新补的一条，代码未改。
- **§4.12 第 5 条**：从"偏离"改为"按裁定不实施"，见 P3-4 与遗留。

**变异**（`/tmp/impl0061p23/mut/fix_specs.json`，结果在 `fix_results.txt`）。每条注入后运行指定测试，然后按字节写回；跑完用 `cmp` 与事先存下的快照逐一核对，4 个文件全部一致（B1d 在更新一条用例后单独重跑，也做了 `cmp`）。

| # | 变异 | 结果 | 变红的测试 |
|---|---|---|---|
| O4 | `if failed:` → `if False:` | 红 | `test_a_module_that_fails_to_import_rolls_back` |
| O1 | 忽略 `records.outside` | 红 | `test_a_record_naming_files_outside_the_overlay_fails_and_says_so` |
| G1 | `pip config list` 用未过滤的 pip 环境 | 红 | `test_settings_that_hide_…[quiet-config]` |
| B1a/b/c | 不再强制 `PIP_QUIET` / `PIP_SITE` / `PIP_GLOBAL` | 红 | 同上，分别在 `[quiet-config]`、`[site-global]`、`[global-global]` |
| B1d | 安装前的 `pip check` 改回 pip 环境 | 红 | `test_a_quiet_pip_does_not_turn_base_problems_into_new_ones[config]` |
| B1e | 不跳过 `:env:` 行（强制的 `PIP_USER=0` 被当成 agent 的设置） | 红 | `test_environment_lines_of_the_listing_are_judged_from_the_environment_itself` |
| B1f | 环境变量按大小写精确匹配 | 红 | `test_a_location_variable_in_the_pip_environment_is_refused[PIP_Target]` |
| B1g | 越界失败仍写 "Nothing was changed" | 红 | `test_an_installation_whose_metadata_is_not_in_the_overlay_fails` |
| I1 | 位置键里去掉 `python` | 红 | `test_pips_python_option_is_refused_before_resolving[config]` |
| m1a/m1b | `OverlayBuilder` 或 `resolve_app_config` 保留相对路径 | 红 | `test_a_relative_overlay_root_works` / `test_a_relative_overlay_directory_is_made_absolute` |

**跑过的命令与结果**
- 复现测试，修前：20 failed, 89 passed；修后：109 passed。
- `$PYT tests/skillenv` 加直接相关文件，共跑两次（第一次暴露一条需要随修复一并更新的旧断言，见下）：
  - 直接相关文件：`tests/launch/test_surfaces.py`、`test_launch_is_above_entry.py`、`test_the_environment_is_read_in_known_places.py`、`tests/permission/test_foundation_tools_keep_their_prompts.py`、`tests/entry/test_config.py`、`tests/test_env_example.py`，以及读 AGENTS/README 的 `tests/entry/test_display.py`、`test_approval_card.py`、`test_cli_approval_scope.py`、`tests/context/test_context_is_a_leaf_layer.py`、`test_sections.py`、`tests/test_output_ownership_contract.py`。
  - 第一次：1 failed, 766 passed, 2 skipped。失败的是 `test_a_leaf_and_its_dependency_install_verify_and_are_reused` 里一条旧断言，它钉住的正是这次有意改掉的行为（安装前 `pip check` 用 pip 环境）。改为断言前后两次 `pip check` 的环境相同、都是 `/dev/null` 配置，之后单独重跑通过，B1d 变异仍然变红。
  - 第二次：**767 passed, 2 skipped**。其中 `tests/skillenv` 收集到 416 个用例；两个 skip 是需手动开启的联网用例和 `tests/launch` 里原有的一个 skip。
- 以 `OmicsClaw` 环境为 base：`/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -o addopts="" tests/skillenv/test_overlay_real.py tests/skillenv/test_install_offline.py` → **36 passed**，无跳过。

**本轮改动的文件**
- 生产代码：`omicsclaw/skillenv/sources.py`、`overlay.py`、`tool.py`，`omicsclaw/entry/config.py`，`omicsclaw/launch/_surfaces.py`（仅 docstring）。
- 测试：`tests/skillenv/test_install_offline.py`、`test_records.py`、`test_sources.py`、`test_install_wiring.py`。
- 文档：`AGENTS.md`、`README.md`、本交付记录。

### 复核后修复（2026-09-26）

复核结论为"有条件通过，接近通过"，指出上一轮修复引入了一处回归（N1），另有 N2–N4 三项。每项都先写能复现问题的测试、看到变红再修。约束不变（不 commit、不 `git add`、不改计划正文）。

**N1（上一轮引入的回归）两种写法可绕过守卫**
- **问题**：上一轮让 `location_settings` 整体跳过 `:env:` 行，`_option` 又漏了 pip `_normalize_name` 的最后一步（去掉开头的 `--`）。结果有两种写法能绕过守卫，而修复前的代码都能拦住：
  - A：配置文件里一个字面名为 `[:env:]` 的段，写 `prefix = X`。pip 把它当作 `PIP_` 变量读取，列表里显示为 `:env:.prefix`，被跳过了。
  - B：环境变量 `PIP___PREFIX`。pip 把它规范化为 `prefix`，`_option` 得到的却是 `--prefix`。
- **修法**：
  - `_option` 与 pip 25.3 的 `_normalize_name` 对齐：转小写、`_` 换成 `-`、去掉开头的 `--`。实测：`PIP___QUIET=1` 会让列表静默，`PIP__QUIET=1` 只被列为 `:env:.-quiet`，并不生效。所以两个下划线的写法不算，三个下划线的算，测试照此写。
  - `location_settings` 不再整体跳过 `:env:` 行，只跳过列表时强制为 0 的四个键（quiet、global、site、user）的回显，其余 `:env:` 行里的位置键照常拒绝，描述为"`:env:.prefix`（PIP_ 变量，或配置文件里的 `[:env:]` 段）"。docstring 同步改写。
  - `config_list_environment` 用同一个规范化来删除强制键的其他写法，`PIP___QUIET` 这类写法也会被替换。
- **新增测试**：
  - `test_install_offline.py::test_other_spellings_of_a_location_key_are_refused`，3 个参数：`env-section-in-a-file`、`leading-underscores`、`mixed-case`。
  - `test_sources.py`：`test_a_variable_pip_normalises_to_a_location_key_is_refused`（`PIP___PREFIX`、`PIP___TARGET`、`PIP___python`）、`test_a_single_extra_underscore_is_not_an_option_pip_reads`、`test_an_env_line_of_the_listing_is_judged_unless_it_echoes_a_forced_value`、`test_leading_underscore_spellings_of_the_forced_variables_are_replaced`。
- **先红后绿**：修前 8 failed, 70 passed（清单在 `/tmp/impl0061p23/final_red.txt`）。其中两个单元用例最初写的是 `PIP__TARGET`、`PIP__GLOBAL`（两个下划线），修后仍然失败；实测确认 pip 不认两个下划线后，改为三个下划线，并新增一条"两个下划线不算"的用例。最终这一组 79 passed。

**N2 落盘核对排在装后 `pip check` 之前**
- **问题**：守卫被绕过、而 prefix 指向 base 时，装后 `pip check` 看得到装到别处的包，于是先以 "breaks declared requirements" 失败，`escaped` 仍为假，结果又写成 "Nothing was changed"。
- **修法**：`overlay.py` 把只读文件的 `RECORD` 核对（outside、absent）移到装后 `pip check` 之前。顶层名遮蔽检查也一并前移，这一项不在复核要求之内。理由：它同样只读文件；遮蔽 base 的新模块（例如一个顶层 `pip` 包）若先于检查存在，装后的 `python -m pip check` 就会执行它。模块 docstring 里的步骤顺序同步改了。
- **新增测试**：`test_records.py::test_an_escape_is_reported_even_when_it_also_breaks_requirements`。安装后把 `oc-needs-old` 挪到 overlay 之外，再用一个 `.pth` 让 overlay 仍然看得见它，模拟"装进了 base"。断言结果是"不在 overlay 里"、写明文件可能在 overlay 之外，并且装后 `pip check` 没有运行。修前失败（结果是 "breaks declared requirements"），修后通过。

**N3**：交付记录里"顺带修了只认全大写变量名的漏洞（PIP_Target）"一句已改正。修复前的完整流程已能拒绝它，新加的只是纯函数层面的覆盖。

**N4**：`test_a_quiet_pip_does_not_turn_base_problems_into_new_ones` 改为用夹具主动造一条既有违例。建好 overlay 后，往它的 site-packages 放一个声明了未满足依赖的 `oc-planted`，再断言安装前那次 `pip check` 的输出里确有这一行（前提断言），这样在干净的 base 上也不会空转通过。为此 `tests/skillenv/installing.py` 的 `Call` 新增一个 `output` 字段，记录每条命令的输出。之前的变异 B1d（安装前 `pip check` 改回 pip 环境）对改写后的用例仍然变红。

**评估方复现脚本（活树上运行）**
| 脚本 | 结果 |
|---|---|
| `repro_env_section.py`（以 OmicsClaw 为解释器与 base） | A、B、C 三种都在 dry-run 之前被拒（阶段只有 venv、config），替身 prefix 下没有 `.py` 文件 |
| `repro_quiet.py` | config、environment 两种都被拒，prefix 目录下 0 个文件 |
| `repro_selector.py` | 被拒，prefix 下没有 `.py`，没有残留的 overlay 目录 |
| `repro_python_option.py` | 被拒（`global.python`），替身解释器的 site-packages 为空 |
| `repro_relative_root.py` | 安装成功，overlay 位于 `<tmp>/relenvs/<key>/.venv` |

**变异**（`/tmp/impl0061p23/mut/final_specs.json`，结果在 `final_results.txt`；跑完用 `cmp` 与快照核对，`sources.py`、`overlay.py` 一致）
| # | 变异 | 结果 | 变红的测试 |
|---|---|---|---|
| N1a | `_option` 不去掉开头的 `--` | 红 | `test_a_variable_pip_normalises_to_a_location_key_is_refused[PIP___PREFIX]` |
| N1b | 重新整体跳过 `:env:` 行 | 红 | `test_an_env_line_of_the_listing_is_judged_unless_it_echoes_a_forced_value`；只跑端到端用例时，`test_other_spellings_…[env-section-in-a-file]` 也变红 |
| N2 | 装后 `pip check` 移回落盘核对之前 | 红 | `test_an_escape_is_reported_even_when_it_also_breaks_requirements` |

N1a 只跑端到端用例时是绿的：修好 N1b 之后，pip 在列表里把 `PIP___PREFIX` 显示为 `:env:.prefix`，被列表这一层拦下，与环境变量那一层互为冗余。所以 N1a 由纯函数用例钉住。

**命令与结果**
- 复现测试：修前 8 failed, 70 passed；修后 79 passed。
- `$PYT tests/skillenv`：**425 passed, 1 skipped**（108 s），skip 的是需手动开启的联网用例。
- 以 `OmicsClaw` 为 base：`/opt/conda/envs/OmicsClaw/bin/python -m pytest -q -o addopts="" tests/skillenv/test_overlay_real.py tests/skillenv/test_install_offline.py` → **39 passed**。

**本轮改动的文件**
- 生产代码：`omicsclaw/skillenv/sources.py`、`overlay.py`。
- 测试：`tests/skillenv/test_sources.py`、`test_install_offline.py`、`test_records.py`、`installing.py`。
- 文档：本交付记录。

**计划对齐（2026-09-27）**：上文"装前 `pip check` 改用无配置环境"、守卫强制 quiet/global/site/user 并加入 `python` 键、落盘与遮蔽核对前移这几处，已写入计划正文 §4.5 第 7.3、7.4、7.9、7.10 步（计划 §10 末条），不再是偏离。
