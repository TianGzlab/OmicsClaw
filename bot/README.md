# OmicsClaw Bot

Dual-channel messaging frontend for OmicsClaw. Supports **Telegram** and **Feishu (Lark)** — both share the same LLM-powered core engine.

> **OmicsClaw is a research and educational tool. It is not a medical device and does not provide clinical diagnoses. Consult a domain expert before making decisions based on these results.**

## Architecture

```
User (Telegram / Feishu)
       │
       ▼
┌──────────────┐    ┌──────────────────────┐
│ telegram_bot │───▶│                      │
│   .py        │    │   bot/core.py        │
├──────────────┤    │  ┌─────────────────┐ │    ┌────────────────┐
│ feishu_bot   │───▶│  │ LLM tool loop   │─┼───▶│ omicsclaw.py │
│   .py        │    │  └─────────────────┘ │    │  (skill runner) │
└──────────────┘    └──────────────────────┘    └────────────────┘
```

- **core.py** — LLM client, TOOLS definition, skill execution, security helpers, audit logging
- **telegram_bot.py** — Telegram handlers, rate limiting, media delivery
- **feishu_bot.py** — Feishu WebSocket client, message parsing, image/file download/upload

## Setup

### 1. Install dependencies

```bash
pip install -r bot/requirements.txt
```

### 2. Create `.env` (project root)

```bash
cp .env.example .env
# edit with your values
```

Required variables:

| Variable | Purpose | Required by |
|---|---|---|
| `LLM_PROVIDER` | Provider preset: `deepseek`, `gemini`, `openai`, `custom` | Both |
| `LLM_API_KEY` | API key for the chosen provider | Both |
| `LLM_BASE_URL` | Override endpoint URL (optional, auto-set by provider) | Both |
| `OMICSCLAW_MODEL` | Override model name (optional, auto-set by provider) | Both |
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram | Telegram |
| `TELEGRAM_CHAT_ID` | Admin chat ID (optional) | Telegram |
| `FEISHU_APP_ID` | From Feishu developer console | Feishu |
| `FEISHU_APP_SECRET` | From Feishu developer console | Feishu |
| `RATE_LIMIT_PER_HOUR` | Max messages/user/hour (default: 10) | Telegram |

### LLM Provider Quick Start

Set `LLM_PROVIDER` to auto-configure the API endpoint and default model:

| Provider | `LLM_PROVIDER` | Default Model | Base URL |
|---|---|---|---|
| DeepSeek | `deepseek` | `deepseek-chat` | `https://api.deepseek.com` |
| Google Gemini | `gemini` | `gemini-2.0-flash` | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| OpenAI | `openai` | `gpt-4o` | (default) |
| Custom endpoint | `custom` | (set `OMICSCLAW_MODEL`) | (set `LLM_BASE_URL`) |

Example `.env` for DeepSeek:

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
```

Example `.env` for Gemini:

```bash
LLM_PROVIDER=gemini
LLM_API_KEY=AIzaSy...
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
```

You can also override the auto-configured defaults:

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxx
OMICSCLAW_MODEL=deepseek-reasoner   # Use R1 instead of default V3
```

### 3. Platform-specific setup

#### Telegram

1. Chat with [@BotFather](https://t.me/BotFather) to create a bot and get the token
2. Set `TELEGRAM_BOT_TOKEN` in `.env`
3. (Optional) Set `TELEGRAM_CHAT_ID` for admin access bypass

#### Feishu

1. Create an app at [Feishu Open Platform](https://open.feishu.cn/app)
2. **CRITICAL**: See [bot/FEISHU_SETUP.md](./FEISHU_SETUP.md) for detailed instructions on configuring permissions (`im:message`, `im:resource`), subscribing to events, enabling Long Connection, and **Publishing a Version** (which is strictly required for receiving messages).
3. Set `FEISHU_APP_ID` and `FEISHU_APP_SECRET` in `.env`

## Usage

```bash
# Telegram bot
python bot/telegram_bot.py

# Feishu bot
python bot/feishu_bot.py

# Or via Makefile
make bot-telegram
make bot-feishu
```

## Bot Commands (Telegram)

| Command | Description |
|---|---|
| `/start` | Welcome message with instructions |
| `/skills` | List all available OmicsClaw analysis skills |
| `/demo <skill>` | Run a skill demo (e.g. `/demo preprocess`) |
| `/status` | Bot uptime and configuration |
| `/health` | System health check |

## Data Input

### Small files (< 40 MB): Upload via messaging

Both platforms accept file uploads. The bot auto-detects omics data formats and routes to the appropriate skill.

### Large files: Server-side path mode (recommended)

Spatial transcriptomics data files are typically hundreds of MB to several GB, far exceeding messaging upload limits. The recommended workflow:

1. **Place files** in the `data/` directory on the server (or any trusted directory)
2. **Tell the bot** the filename or path in the chat

```
User: 对 data/brain_visium.h5ad 做预处理
Bot:  (runs preprocess on data/brain_visium.h5ad)

User: analyze my_experiment.h5ad
Bot:  (auto-discovers my_experiment.h5ad in data/)

User: run de on /mnt/nas/spatial/sample01.h5ad
Bot:  (reads from NAS if OMICSCLAW_DATA_DIRS includes /mnt/nas/spatial)
```

The bot automatically searches these directories:
- `data/` — primary user data folder
- `examples/` — demo datasets
- `output/` — previous analysis outputs
- Any additional paths in `OMICSCLAW_DATA_DIRS`

To add external data directories (NAS, shared storage, other projects), set in `.env`:

```bash
OMICSCLAW_DATA_DIRS=/mnt/nas/spatial_data,/home/user/experiments
```

Files are only readable from trusted directories. Paths outside these directories are rejected.

### Tissue images

Both platforms support:
- **Tissue images** (H&E stain, fluorescence, spatial barcodes) — identifies tissue type and suggests analysis
- **General images** — described and user asked for intent

## Logging

Structured audit logs are written to `bot/logs/audit.jsonl`. Each entry includes timestamp, event type, and relevant metadata.

## Security

- All data stays on the local machine — no cloud uploads
- File paths are validated against a trusted directory whitelist (`data/`, `examples/`, `output/`, `OMICSCLAW_DATA_DIRS`)
- Path traversal attempts (e.g. `../../etc/passwd`) are blocked and logged
- File size limits enforced for uploads (50 MB files, 20 MB photos)
- Rate limiting per user (Telegram)
- Bot token redacted from all log output
- All path resolutions are logged in the audit trail
