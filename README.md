<a id="top"></a>

<div align="center">

<a href="https://github.com/TianGzlab/OmicsClaw">
  <img src="docs/images/OmicsClaw_banner.jpeg" alt="OmicsClaw banner" width="100%"/>
</a>

<h3>Local-first AI research partner for multi-omics analysis</h3>

<p>
  <b>English</b> ·
  <a href="README_zh-CN.md">简体中文</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#desktop-app">Desktop App</a> ·
  <a href="#domains">Domains</a> ·
  <a href="https://TianGzlab.github.io/OmicsClaw/">Docs site</a>
</p>

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Website](https://img.shields.io/badge/Website-Live-brightgreen.svg)](https://TianGzlab.github.io/OmicsClaw/)
[![Desktop App](https://img.shields.io/github/v/release/TianGzlab/OmicsClaw?label=desktop%20app&color=blue&cacheSeconds=600)](https://github.com/TianGzlab/OmicsClaw/releases/latest)
[![Installer Downloads](https://img.shields.io/github/downloads/TianGzlab/OmicsClaw/total?label=installer%20downloads&color=brightgreen&cacheSeconds=600)](https://github.com/TianGzlab/OmicsClaw/releases)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey)](https://github.com/TianGzlab/OmicsClaw/releases/latest)

</div>

OmicsClaw is an AI agent for multi-omics analysis. You describe the analysis
you want; the model picks a skill, reads its instructions and runs its Python,
R or command-line tools in your own environment, on your machine or on a
server. It ships 88 skills in seven domains, and the same agent answers in the
terminal, in the desktop app and on chat platforms.

## What's new

- Across seven domains, 83 skills expose function libraries and replayable examples; five remain CLI-only, including the demo-only XCMS stub, and Python/R modules support IO tracking and review before acceptance ([0074](docs/plans/0074-singlecell-skill-migration.md), [0075](docs/plans/0075-spatial-skill-migration.md), [0076](docs/plans/0076-remaining-modalities-migration.md)).
- A real-model routing eval (`tests/evals/live/`, run by hand) measures whether the model picks the right skill for 26 seed requests, the CI unit-test job now also runs the launch shell, attachments, top-level and desktop HTTP tests, and the four consensus skills whose scripts could not start have since been deleted ([0068](docs/plans/0068-eval-hardening.md), [0070](docs/plans/0070-notebook-skill-runtime.md)).
- The agent framework has been rebuilt around three entry points, `oc cli`, `oc desktop` and `oc channel`, and the old `oc interactive`, `oc tui`, `oc onboard` and `oc run` commands are gone ([rebuild status](docs/FRAMEWORK-REBUILD.md)).
- [Desktop v0.1.8](https://github.com/TianGzlab/OmicsClaw/releases/tag/v0.1.8) is available for macOS, Windows and Linux, with Desktop v3, SSH session recovery and an optional Independent review button below each completed reply.
- The agent tells you which of a skill's packages your environment lacks, and with `OMICSCLAW_SKILL_ENV=install` it can install them after you approve, into a separate overlay that leaves the base environment untouched ([0061](docs/plans/0061-adaptive-env-provisioning.md)).

Earlier entries are in [CHANGELOG.md](CHANGELOG.md).

## Quick start

```bash
git clone https://github.com/TianGzlab/OmicsClaw.git
cd OmicsClaw
bash 0_setup_env.sh        # creates the OmicsClaw conda environment
conda activate OmicsClaw
oc cli --configure         # choose a model provider and enter its API key
oc cli                     # chat in the terminal
```

`oc cli --configure` saves its answers to a `.env` file. It asks for one of 13
providers (DeepSeek, OpenAI, Anthropic, Gemini, Qwen on DashScope, Ollama, any
OpenAI-compatible endpoint and others), the API key, the model, an optional
base URL, and the workspace directory the agent may read and write. The agent
loads skills from `<workspace>/skills`, so if the workspace is not the
checkout, also set `OMICSCLAW_SKILLS_DIR=<checkout>/skills` in `.env`.
`oc cli --prompt "..."` answers one question and exits. If `oc` is not on
`PATH`, use `python omicsclaw.py cli`.

Skills are ordinary scripts, so you can also run one without the agent:

```bash
make list    # every skill, by domain
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/omicsclaw_demo
```

## Ways to use it

| Where | Start it with | What you get |
|---|---|---|
| Terminal | `oc cli` | Chat with the agent. `/resume` reopens an earlier conversation, `/skills` lists skills, `/help` lists the other commands |
| Desktop App | the App starts `oc desktop` | Chat, approvals and file viewing in a desktop window ([below](#desktop-app)) |
| Remote server | `oc desktop` on the server | The App reaches it through its own SSH tunnel, so the data stays on the server ([remote mode](docs/engineering/remote-execution.mdx)) |
| Chat platforms | `oc channel --channels telegram` | Owner-only text chat on Telegram, Feishu, Slack, Discord, DingTalk, QQ or Email. `oc channel --list` shows them. Set `OMICSCLAW_APPROVAL_TIMEOUT_S` in `.env` first, or it refuses to start |
| Skill scripts | `python <skill directory>/<script>.py` | One analysis without the agent. Each skill's `SKILL.md` documents its options |

Conversations and the agent's long-term notes are stored in
`<workspace>/.omicsclaw/memory.db`. MCP servers listed in
`<workspace>/.mcp.json` are connected at start-up, and their tools become
available to the agent.

The agent asks you before it runs a shell command, writes or edits a file,
goes to the web, or calls an MCP tool. In the terminal you can allow a call once, allow that tool for
the rest of the conversation, or always allow that exact call; `/auto` stops
the questions about ordinary work. Dangerous commands and changes to
`.omicsclaw/` or `.env` are still asked about. The dangerous-command check
matches known patterns, and a command written to avoid them gets through, so if
you let the agent work unattended, run its commands in a container without
network access by setting `OMICSCLAW_SANDBOX=docker` and
`OMICSCLAW_SANDBOX_IMAGE` (see [`.env.example`](.env.example)).

## Desktop App

<p align="center">
  <img src="docs/images/omicsclaw-app-overview.png" alt="The OmicsClaw desktop app, with a project's conversations in the sidebar and the chat box in the middle" width="94%"/>
</p>

Download [Desktop v0.1.8](https://github.com/TianGzlab/OmicsClaw/releases/tag/v0.1.8) for your platform below.
Check each download against the
[`SHA256SUMS.txt`](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/SHA256SUMS.txt)
published with it.

| Platform | Installer |
|---|---|
| macOS, Apple Silicon | [OmicsClaw-0.1.8-arm64.dmg](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-arm64.dmg) |
| macOS, Intel | [OmicsClaw-0.1.8-x64.dmg](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-x64.dmg) |
| Windows, x64 or ARM64 | [OmicsClaw.Setup.0.1.8-x64.exe](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw.Setup.0.1.8-x64.exe), [OmicsClaw.Setup.0.1.8-arm64.exe](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw.Setup.0.1.8-arm64.exe) |
| Linux, x64 | [AppImage](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-x86_64.AppImage), [deb](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-amd64.deb), [rpm](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-x86_64.rpm) |
| Linux, ARM64 | [AppImage](https://github.com/TianGzlab/OmicsClaw/releases/download/v0.1.8/OmicsClaw-0.1.8-arm64.AppImage) |

The installer contains no Python. **Remote mode** connects to a server through
SSH or a backend URL and needs no Python on the client. **Local mode** asks for
an interpreter with OmicsClaw installed, normally the conda environment from
the quick start:

```bash
conda run -n OmicsClaw python -c "import sys; print(sys.executable)"
```

In Local mode, the App starts `oc desktop` for the project you open, one backend per
project. The model comes from the backend's `.env`, which the App's Providers
page can edit; a change takes effect when the backend restarts. Troubleshooting
is in the [App guide](docs/ecosystem/omicsclaw-app.mdx), and the HTTP contract
in [`docs/core-features/surfaces.md`](docs/core-features/surfaces.md) §8.

Independent module review is off by default. After a reply finishes, click
**Independent review** below it to review that reply's analysis and return
the findings in the same conversation. The click applies only to that review;
it does not enable reviews for later analyses. Use App v0.1.8 or later, update
the backend to include [`1540fca7`](https://github.com/TianGzlab/OmicsClaw/commit/1540fca71bc3dbf9ba83557aafe964860a6b81dc),
and restart `oc desktop` to use this control.

## Installation

| Method | Command | Covers |
|---|---|---|
| conda (recommended) | `bash 0_setup_env.sh` | Python, R and the command-line tools the skills need, plus the Desktop backend |
| pip | `pip install -e .` | Terminal chat only. Most skills need packages that the conda environment provides, and the Desktop backend's FastAPI and uvicorn come from conda |

Chat platforms need their own SDKs: `pip install -e ".[channels]"` for
Telegram and Feishu, `pip install slack-sdk aiohttp` for Slack,
`pip install discord.py` for Discord, `pip install httpx websockets` for
DingTalk and `pip install qq-botpy` for QQ; Email uses only the standard
library. The dependency lists are [`environment.yml`](environment.yml) and
[`pyproject.toml`](pyproject.toml).

## Domains

88 skills in seven domains. `make list` prints the current index.

| Domain | Skills | Examples | Guide |
|---|---|---|---|
| Spatial transcriptomics | 17 | QC, domains, annotation, deconvolution, CNV, trajectory | [spatial](docs/domains/spatial.mdx) |
| Single-cell omics | 30 | QC, clustering, annotation, doublets, velocity, GRN | [singlecell](docs/domains/singlecell.mdx) |
| Genomics | 10 | QC, alignment, variants, CNV, assembly, epigenomics | [genomics](docs/domains/genomics.mdx) |
| Proteomics | 8 | DIA/DDA, PTM, networks, biomarkers | [proteomics](docs/domains/proteomics.mdx) |
| Metabolomics | 8 | Peaks, normalization, annotation, pathways | [metabolomics](docs/domains/metabolomics.mdx) |
| Bulk RNA-seq | 14 | DE, enrichment, co-expression, deconvolution, survival, cosinor rhythms | [bulkrna](docs/domains/bulkrna.mdx) |
| Literature | 1 | PDF, DOI, PubMed and GEO parsing, dataset handoff | |

## Documentation

The [docs site](https://TianGzlab.github.io/OmicsClaw/) is written in Chinese.

| Topic | Where |
|---|---|
| Quickstart | [introduction/quickstart](docs/introduction/quickstart.mdx) |
| Desktop App | [ecosystem/omicsclaw-app](docs/ecosystem/omicsclaw-app.mdx) |
| Remote mode | [engineering/remote-execution](docs/engineering/remote-execution.mdx) |
| Domain guides | [spatial](docs/domains/spatial.mdx) · [singlecell](docs/domains/singlecell.mdx) · [genomics](docs/domains/genomics.mdx) · [proteomics](docs/domains/proteomics.mdx) · [metabolomics](docs/domains/metabolomics.mdx) · [bulkrna](docs/domains/bulkrna.mdx) |
| Safety and data privacy | [data privacy](docs/safety/data-privacy.mdx) · [rules and disclaimer](docs/safety/rules-and-disclaimer.mdx) |
| Writing a skill | [CONTRIBUTING.md](CONTRIBUTING.md) · [`templates/skill/`](templates/skill/) |
| Framework design | [`docs/FRAMEWORK-REBUILD.md`](docs/FRAMEWORK-REBUILD.md) |
| Changelog | [CHANGELOG.md](CHANGELOG.md) |

## Safety and data

Skills read and process your data in your own runtime, local or remote; the
model receives the conversation and what the tools return. OmicsClaw is a
research tool. It is not a medical device and gives no clinical diagnoses, so
have a domain expert check results before acting on them. On a server, keep
`oc desktop` bound to localhost and reach it through SSH; a non-loopback bind
requires `OMICSCLAW_REMOTE_AUTH_TOKEN`. See [data privacy](docs/safety/data-privacy.mdx)
and [rules and disclaimer](docs/safety/rules-and-disclaimer.mdx).

## Community

Maintainers: Luyi Tian (Principal Investigator), Weige Zhou (Lead Developer), Liying Chen (Developer), and Pengfei Yin (Developer).

[Issues](https://github.com/TianGzlab/OmicsClaw/issues) · [Discussions](https://github.com/TianGzlab/OmicsClaw/discussions) · [Docs](https://TianGzlab.github.io/OmicsClaw/)

<table>
  <tr>
    <td align="center" width="30%">
      <img src="docs/images/IMG_3729.JPG" alt="OmicsClaw WeChat group QR code" width="180"/>
      <br/>
      WeChat group
    </td>
    <td valign="middle" width="70%">
      Scan the code to join our WeChat group for analysis tips and help with problems.
    </td>
  </tr>
</table>

<a href="https://github.com/TianGzlab/OmicsClaw/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=TianGzlab/OmicsClaw" alt="OmicsClaw contributors"/>
</a>

## Acknowledgments

The architecture, skill design and local-first approach are inspired by
[ClawBio](https://github.com/ClawBio/ClawBio), an early bioinformatics-native
AI agent skill library. The memory and session-continuity patterns are inspired
by [Nocturne Memory](https://github.com/Dataojitori/nocturne_memory).

## Contributing

To add a skill, see [CONTRIBUTING.md](CONTRIBUTING.md) and the scaffold under
[`templates/skill/`](templates/skill/). For work on the framework itself, start
with [AGENTS.md](AGENTS.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

## Citation

```bibtex
@software{omicsclaw2026,
  title = {OmicsClaw: A Memory-Enabled AI Agent for Multi-Omics Analysis},
  author = {Zhou, Weige and Chen, Liying and Yin, Pengfei and Tian, Luyi},
  year = {2026},
  url = {https://github.com/TianGzlab/OmicsClaw}
}
```

[Back to top](#top)
