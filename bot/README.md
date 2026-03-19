# OmicsClaw Messaging Bot System

The `bot` module powers OmicsClaw's conversational AI interfaces. It connects the core multi-omics skills engine with popular messaging platforms and a native terminal experience.

## ✨ New: Interactive Terminal Mode (TUI)

You can now chat with OmicsBot natively in your terminal without any messaging apps configured! Similar to the EvoScientist CLI experience:

```bash
# Start the interactive conversational UI
./OmicsClaw interactive
```

## Supported Channels
- [Architecture](#architecture)
- [Capability Matrix](#capability-matrix)
- [Installation](#installation)
- [Configuration](#configuration)
- [Channel Deployment Guides](#channel-deployment-guides)
- [Usage](#usage)
- [Security and Access Control](#security-and-access-control)
- [Troubleshooting](#troubleshooting)

## Architecture

```
User (Telegram / Feishu / DingTalk / Discord / Slack / WeChat / QQ / Email / iMessage)
       │
       ▼
┌───────────────────────────────────────────────────────────────┐
│         bot/channels/  (Channel ABC)                         │
│  ┌──────────┬──────┬────────┬───────┬──────┬──────┬────────┐ │
│  │ Telegram │Feishu│DingTalk│Discord│ Slack│WeChat│QQ/Email│ │
│  └──────────┴──────┴────────┴───────┴──────┴──────┴────────┘ │
│         ↕ MessageBus + MiddlewarePipeline ↕                  │
│  ┌──────────────────────────────────────────┐                │
│  │  ChannelManager (lifecycle + health)     │                │
│  └──────────────────────────────────────────┘                │
│         ↓                                                    │
│  ┌──────────────────────────────────────────┐                │
│  │  bot/core.py  (LLM tool loop)            │───▶ omicsclaw.py (skills)
│  └──────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

### Core Modules

| Module | Purpose |
|--------|--------|
| `core.py` | LLM client, TOOLS, skill execution, security, audit |
| `channels/base.py` | Channel ABC, chunk_text, DedupCache, RateLimiter |
| `channels/bus.py` | MessageBus — async inbound/outbound queues |
| `channels/middleware.py` | Composable dedup/rate-limit/allow-list/audit pipeline |
| `channels/manager.py` | ChannelManager — multi-channel lifecycle + /healthz |
| `channels/telegram.py` | TelegramChannel (python-telegram-bot) |
| `channels/feishu.py` | FeishuChannel (lark-oapi WebSocket) |
| `channels/dingtalk.py` | DingTalkChannel (Stream Mode WebSocket) |
| `channels/discord.py` | DiscordChannel (discord.py Gateway) |
| `channels/slack.py` | SlackChannel (Socket Mode, no public IP) |
| `channels/wechat.py` | WeChatChannel (WeCom + Official Account webhook) |
| `channels/qq.py` | QQChannel (qq-botpy, WebSocket Gateway) |
| `channels/email.py` | EmailChannel (IMAP + SMTP, stdlib only) |
| `channels/imessage.py` | IMessageChannel (imsg CLI, macOS only) |
| `run.py` | Unified CLI runner — `python -m bot.run` |

## Capability Matrix

| Channel | Format | Max Len | Media | Typing | Group | @Mention | No Public IP | Token Refresh |
|:--------|:------:|:-------:|:-----:|:------:|:-----:|:--------:|:------------:|:-------------:|
| Telegram | HTML | 4000 | S/R | 4s | ✓ | ✓ | ✓ | — |
| Feishu | Post | 4096 | S/R | — | ✓ | ✓ | — | 2h |
| DingTalk | MD | 4096 | S/R | — | ✓ | ✓ | ✓ | 2h |
| Discord | MD | 2000 | S/R | 8s | ✓ | ✓ | ✓ | — |
| Slack | Mrkdwn | 4000 | S/R | — | ✓ | ✓ | ✓ | — |
| WeChat | MD | 4096 | S/R | — | ✓ | ✓ | — | 2h |
| QQ | Plain | 4096 | S/R | — | ✓ | ✓ | ✓ | — |
| Email | HTML | — | S/R | — | — | — | ✓ | — |
| iMessage | Plain | — | S/R | — | ✓ | — | ✓ | — |

Legend: **S** = send, **R** = receive, **—** = not applicable/unlimited

### Connection Types

| Channel | Transport | Connection Mode | Default Port |
|---------|-----------|-----------------|:------------:|
| Telegram | HTTPS | Long polling (`getUpdates`) | — |
| Feishu | WebSocket | lark-oapi WebSocket client | — |
| DingTalk | WebSocket | Stream Mode (DingTalk gateway) | — |
| Discord | WebSocket | Gateway events (`discord.py`) | — |
| Slack | WebSocket | Socket Mode (`slack-sdk`) | — |
| WeChat | HTTP | Webhook (`POST /wechat/callback`) | 9001 |
| QQ | WebSocket | Bot Gateway (`qq-botpy`) | — |
| Email | TCP | IMAP polling + SMTP send | 993/587 |
| iMessage | stdio | JSON-RPC (`imsg` CLI) | — |

> **"—"** means no listening port required — no public IP or port forwarding needed.

---

## Installation

### Step 1: Core Dependencies

```bash
# Install core dependencies (LLM client, HTTP, dotenv)
pip install -r bot/requirements.txt
```

### Step 2: Channel Dependencies

Choose **one** of the following approaches:

#### Option A: Install all channel dependencies

```bash
pip install -r bot/requirements-channels.txt
```

#### Option B: Install only the channels you need

```bash
# Telegram
pip install "python-telegram-bot>=21.0"

# Feishu (Lark)
pip install "lark-oapi>=1.3.0"

# DingTalk
pip install "websockets>=12.0"
# httpx is already in core requirements

# Discord
pip install "discord.py>=2.3.0"

# Slack
pip install "slack-sdk>=3.27.0" "aiohttp>=3.9.0"

# WeChat
# httpx + aiohttp already covered above — no additional install needed

# QQ
pip install qq-botpy

# Email
# No extra dependencies — uses Python standard library (imaplib, smtplib)

# iMessage (macOS only)
# No Python dependencies — requires imsg CLI:
brew install anthropics/tap/imsg
```

### Dependency Summary

| Channel | Python Package | External Tool | Notes |
|---------|---------------|---------------|-------|
| Telegram | `python-telegram-bot>=21.0` | — | |
| Feishu | `lark-oapi>=1.3.0` | — | |
| DingTalk | `websockets>=12.0` | — | `httpx` already in core |
| Discord | `discord.py>=2.3.0` | — | |
| Slack | `slack-sdk>=3.27.0`, `aiohttp>=3.9.0` | — | |
| WeChat | *(covered by core + Slack deps)* | — | Needs `httpx` + `aiohttp` |
| QQ | `qq-botpy` | — | |
| Email | *(none — stdlib only)* | — | Uses `imaplib`, `smtplib` |
| iMessage | *(none)* | `imsg` CLI (macOS) | `brew install anthropics/tap/imsg` |

---

## Configuration

### 1. Create `.env` (project root)

```bash
cp .env.example .env
# edit with your values
```

### 2. Environment Variables

| Variable | Purpose | Required by |
|---|---|---|
| `LLM_PROVIDER` | Provider preset (see table below) — *optional if provider-specific key is set* | All |
| `LLM_API_KEY` | API key (generic) — *optional if provider-specific key is set* | All |
| `LLM_BASE_URL` | Override endpoint URL (optional, auto-set by provider) | All |
| `OMICSCLAW_MODEL` | Override model name (optional, auto-set by provider) | All |
| `TELEGRAM_BOT_TOKEN` | From @BotFather on Telegram | Telegram |
| `TELEGRAM_CHAT_ID` | Admin chat ID (optional) | Telegram |
| `FEISHU_APP_ID` | From Feishu developer console | Feishu |
| `FEISHU_APP_SECRET` | From Feishu developer console | Feishu |
| `DINGTALK_CLIENT_ID` | Robot App Key | DingTalk |
| `DINGTALK_CLIENT_SECRET` | Robot App Secret | DingTalk |
| `DISCORD_BOT_TOKEN` | Discord bot token | Discord |
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (xoxb-...) | Slack |
| `SLACK_APP_TOKEN` | App-Level Token (xapp-...) for Socket Mode | Slack |
| `WECOM_CORP_ID` | Corp ID (企业微信) | WeChat (WeCom) |
| `WECOM_AGENT_ID` | Agent ID (企业微信) | WeChat (WeCom) |
| `WECOM_SECRET` | App Secret (企业微信) | WeChat (WeCom) |
| `WECHAT_APP_ID` | App ID (公众号, alternative to WeCom) | WeChat (MP) |
| `WECHAT_APP_SECRET` | App Secret (公众号) | WeChat (MP) |
| `QQ_APP_ID` | QQ Bot App ID | QQ |
| `QQ_APP_SECRET` | QQ Bot App Secret | QQ |
| `EMAIL_IMAP_HOST` | IMAP server hostname (e.g. `imap.gmail.com`) | Email |
| `EMAIL_IMAP_USERNAME` | IMAP login username | Email |
| `EMAIL_IMAP_PASSWORD` | IMAP login password / app password | Email |
| `EMAIL_SMTP_HOST` | SMTP server hostname (e.g. `smtp.gmail.com`) | Email |
| `EMAIL_SMTP_USERNAME` | SMTP login username | Email |
| `EMAIL_SMTP_PASSWORD` | SMTP login password / app password | Email |
| `EMAIL_FROM_ADDRESS` | Sender address for outbound emails | Email |
| `IMESSAGE_CLI_PATH` | Path to `imsg` CLI binary (macOS only) | iMessage |
| `IMESSAGE_ALLOWED_SENDERS` | Comma-separated allow-list (phones/emails) | iMessage |
| `RATE_LIMIT_PER_HOUR` | Max messages/user/hour (default: 10) | All |

### LLM Provider Quick Start

OmicsClaw supports **12 LLM providers** through a unified OpenAI-compatible interface:

| Provider | `LLM_PROVIDER` | Default Model | API Key Env Var |
|---|---|---|---|
| DeepSeek | `deepseek` | `deepseek-chat` | `DEEPSEEK_API_KEY` |
| OpenAI | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| Anthropic | `anthropic` | `claude-sonnet-4-5` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini` | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| NVIDIA NIM | `nvidia` | `deepseek-ai/deepseek-r1` | `NVIDIA_API_KEY` |
| SiliconFlow | `siliconflow` | `DeepSeek-V3` | `SILICONFLOW_API_KEY` |
| OpenRouter | `openrouter` | `deepseek-chat-v3` | `OPENROUTER_API_KEY` |
| Volcengine 火山引擎 | `volcengine` | `doubao-1.5-pro-256k` | `VOLCENGINE_API_KEY` |
| DashScope 阿里云 | `dashscope` | `qwen-max` | `DASHSCOPE_API_KEY` |
| Zhipu AI 智谱 | `zhipu` | `glm-4-flash` | `ZHIPU_API_KEY` |
| Ollama (local) | `ollama` | `qwen2.5:7b` | *(none)* |
| Custom endpoint | `custom` | *(set `OMICSCLAW_MODEL`)* | *(set `LLM_API_KEY`)* |

**Two ways to configure:**

**Option 1 — Explicit** (set LLM_PROVIDER + LLM_API_KEY):

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Option 2 — Auto-detect** (set only the provider-specific API key):

```bash
# Just set this — the system auto-detects DeepSeek
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Provider-specific examples:

```bash
# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx

# Google Gemini
GOOGLE_API_KEY=AIzaSyxxxxxxxx

# NVIDIA NIM
NVIDIA_API_KEY=nvapi-xxxxxxxx

# Alibaba DashScope (Qwen)
DASHSCOPE_API_KEY=sk-xxxxxxxx
OMICSCLAW_MODEL=qwen-max

# Local Ollama
LLM_PROVIDER=ollama
OMICSCLAW_MODEL=qwen2.5:7b
```

You can also override the auto-configured defaults:

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxx
OMICSCLAW_MODEL=deepseek-reasoner   # Use R1 instead of default V3
```

---

## Channel Deployment Guides

### Telegram

**Install:** `pip install "python-telegram-bot>=21.0"`

**Prerequisites:**

1. Search for [@BotFather](https://t.me/BotFather) in Telegram, send `/newbot`, and follow the prompts
2. BotFather will return a Bot Token (format: `123456789:ABCdefGHI...`) — save it securely
3. Get your user ID: send any message to [@userinfobot](https://t.me/userinfobot)
4. (Optional) For group use: in BotFather send `/setprivacy` → `Disable`

**Configuration:**

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=           # Optional: admin user ID
```

**Technical details:** Long polling mode, `drop_pending_updates=True` on startup. Markdown to Telegram HTML auto-conversion. Media routed by extension to `send_photo`/`send_video`/`send_audio`/`send_document`. In groups, only responds when @mentioned. Typing indicator refreshes every 4s. Retry: 3 attempts. Text chunk limit: 4000 chars.

---

### Feishu (Lark)

**Install:** `pip install "lark-oapi>=1.3.0"`

**Prerequisites:**

1. Create an app at [Feishu Open Platform](https://open.feishu.cn/app) (international: [Lark Developer](https://open.larksuite.com/app))
2. Copy the **App ID** and **App Secret**
3. **CRITICAL**: See [bot/CHANNELS_SETUP.md](./CHANNELS_SETUP.md#2-feishu-lark) for detailed instructions on configuring permissions (`im:message`, `im:resource`), subscribing to events, enabling Long Connection, and **Publishing a Version** (strictly required for receiving messages)

**Configuration:**

```bash
FEISHU_APP_ID=cli_xxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxx
```

**Technical details:** WebSocket long connection via `lark_oapi.ws.Client`. Event-driven message handling. Markdown to Feishu rich text conversion. Group @mention filtering. Media: images via `/im/v1/images`, files via `/im/v1/files`. Text chunk limit: 4096 chars.

---

### DingTalk 钉钉

**Install:** `pip install "websockets>=12.0"`

**Prerequisites:**

1. Create a robot at [DingTalk Open Platform](https://open-dev.dingtalk.com)
2. Enable **Stream Mode** (WebSocket, no public IP needed)
3. Publish the app and add the bot to a group, or test via direct message

**Configuration:**

```bash
DINGTALK_CLIENT_ID=ding...
DINGTALK_CLIENT_SECRET=xxxxxxxxxxxxxxxxxx
```

**Technical details:** Stream Mode via WebSocket — connects to DingTalk gateway. Automatic ticket-based auth. Sends via Markdown format. Group @mention detection via `isInAtList`. `accessToken` auto-refresh. Text chunk limit: 4096 chars.

---

### Discord

**Install:** `pip install "discord.py>=2.3.0"`

**Prerequisites:**

1. Go to [Discord Developer Portal](https://discord.com/developers/applications) → New Application
2. Bot → Reset Token → copy the Bot Token
3. Under **Privileged Gateway Intents**, enable **Message Content Intent**
4. OAuth2 → URL Generator: Scopes `bot`, Permissions: `Send Messages`, `Read Message History`, `Attach Files`, `Add Reactions`
5. Open the generated URL in browser, select a server to invite the bot

**Configuration:**

```bash
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.xxxx.xxxxx
```

**Technical details:** WebSocket Gateway (`discord.py`). In server channels, only responds when @mentioned; DMs respond directly. Thread-aware replies via `MessageReference`. Media sent via `discord.File`. Typing indicator refreshes every 8s. Text chunk limit: 2000 chars.

---

### Slack

**Install:** `pip install "slack-sdk>=3.27.0" "aiohttp>=3.9.0"`

**Prerequisites:**

1. Go to [Slack API](https://api.slack.com/apps) → Create New App → From scratch
2. **Socket Mode** → enable → Generate App-Level Token (scope `connections:write`) → copy `xapp-...`
3. **OAuth & Permissions** → add Bot Token Scopes: `chat:write`, `channels:history`, `groups:history`, `im:history`, `files:read`, `files:write`, `reactions:write`
4. Click **Install to Workspace** → copy Bot Token `xoxb-...`
5. **Event Subscriptions** → enable → Subscribe: `message.channels`, `message.groups`, `message.im`, `app_mention`

**Configuration:**

```bash
SLACK_BOT_TOKEN=xoxb-xxxx-xxxx-xxxx
SLACK_APP_TOKEN=xapp-1-xxxx-xxxx
```

**Technical details:** Socket Mode (no public URL needed). Markdown to mrkdwn conversion. Thread replies via `thread_ts`. Attachments via `files_upload_v2`. Runs `auth_test()` on startup to verify credentials. Text chunk limit: 4000 chars.

---

### WeChat 企业微信 / 公众号

**Install:** `pip install httpx aiohttp` *(both already in core/Slack deps)*

Two backends supported: **WeCom** (recommended, free) and **WeChat Official Account** (requires verified service account).

#### WeCom

1. Log in to [WeCom Admin Console](https://work.weixin.qq.com/) → App Management → create a custom app
2. Copy the **Corp ID**, **AgentId**, and **Secret**
3. In app details → Receive Messages → Set API Receive → URL: `http://your-host:9001/wechat/callback`
4. Copy **Token** and **EncodingAESKey**
5. In app details → **Trusted IP** → add your server's public IP address

```bash
WECOM_CORP_ID=ww...
WECOM_AGENT_ID=1000002
WECOM_SECRET=xxxxxxxxxxxxxxxxxx
WECOM_TOKEN=xxxxxxxxxxxxxxxxxx          # Optional
WECOM_ENCODING_AES_KEY=xxxxxxxxxxxxxxxxxx  # Optional
```

#### Official Account

1. Log in to [WeChat Official Account Platform](https://mp.weixin.qq.com/)
2. Settings & Development → Basic Configuration
3. Copy **AppID** and **AppSecret**

```bash
WECHAT_APP_ID=wx...
WECHAT_APP_SECRET=xxxxxxxxxxxxxxxxxx
```

> ⚠️ Requires a public IP for webhook callbacks (port 9001 by default). For local development, use `ngrok http 9001`.

**Technical details:** Webhook HTTP server for inbound XML message parsing. `access_token` auto-refresh (2h TTL). WeCom supports Markdown; Official Account uses plain text only. Supports text, image, voice, video message types. Text chunk limit: 4096 chars.

---

### QQ

**Install:** `pip install qq-botpy`

**Prerequisites:**

1. Register as a developer at [QQ Open Platform](https://q.qq.com/)
2. Create a bot → complete developer verification
3. Copy the **App ID** and **App Secret**
4. Enable the "C2C消息" and "群聊消息" intents in the bot dashboard
5. Search for and add the bot as a friend in QQ, or add it to a group

**Configuration:**

```bash
QQ_APP_ID=xxxxxxxxxx
QQ_APP_SECRET=xxxxxxxxxxxxxxxxxx
```

> **Note**: QQ bots require intent declarations. The bot uses WebSocket Gateway mode — no public IP required.

**Technical details:** Uses `qq-botpy` SDK via WebSocket to connect to QQ Bot Gateway. Supports C2C (direct) and group messages. Message deduplication (1000-entry LRU cache). Group @mention filtering. Intents: `public_messages=True`, `direct_message=True`. Text chunk limit: 4096 chars.

---

### Email

**Install:** No extra Python dependencies — uses only standard library (`imaplib`, `smtplib`, `email`).

**Prerequisites:**

1. Prepare an email account with IMAP + SMTP support (Gmail, Outlook, self-hosted, etc.)
2. **Gmail**: Enable 2FA → generate an [App Password](https://myaccount.google.com/apppasswords)
3. **Outlook/Office 365**: IMAP: `outlook.office365.com:993`, SMTP: `smtp.office365.com:587`
4. Ensure IMAP access is enabled in your email settings

**Configuration:**

```bash
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_IMAP_USERNAME=your-email@gmail.com
EMAIL_IMAP_PASSWORD=your-app-password
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=your-email@gmail.com
EMAIL_SMTP_PASSWORD=your-app-password
EMAIL_FROM_ADDRESS=your-email@gmail.com
EMAIL_POLL_INTERVAL=30                    # Optional (default: 30s)
EMAIL_MARK_SEEN=1                         # Optional (default: 1)
EMAIL_ALLOWED_SENDERS=                    # Optional: comma-separated
```

> **Common providers:**
> | Provider | IMAP Host | SMTP Host | SMTP Port |
> |---|---|---|---|
> | Gmail | `imap.gmail.com` | `smtp.gmail.com` | 587 |
> | Outlook/365 | `outlook.office365.com` | `smtp.office365.com` | 587 |
> | QQ Mail | `imap.qq.com` | `smtp.qq.com` | 587 |
> | 163 Mail | `imap.163.com` | `smtp.163.com` | 25 |

**Technical details:** IMAP polling mode, checks for UNSEEN emails periodically (max 20 per cycle). Auto-parses multipart emails (prefers text/plain, falls back text/html). Replies set `In-Reply-To` and `References` headers to maintain threads. Sends HTML + plain text dual format. IMAP auto-reconnects. No public IP needed.

---

### iMessage (macOS only)

**Install:** No Python dependencies. Requires the [imsg](https://github.com/anthropics/imsg) CLI tool.

**Requirements:** macOS only — iMessage is Apple-proprietary. Requires a signed-in Apple ID with Messages.app.

**Prerequisites:**

1. Install imsg CLI:
   ```bash
   brew install anthropics/tap/imsg
   ```
2. Verify: `imsg --version`
3. Grant Terminal/IDE **Full Disk Access** in System Settings → Privacy & Security
4. Ensure Messages.app is signed in and working

**Configuration:**

```bash
IMESSAGE_CLI_PATH=/opt/homebrew/bin/imsg    # or $(which imsg)
IMESSAGE_ALLOWED_SENDERS=+1234567890,user@icloud.com
IMESSAGE_SERVICE=auto                       # Optional: imessage | sms | auto
IMESSAGE_REGION=US                          # Optional: phone number region
```

**Allowlist formats:** phone (`+1234567890`), email (`user@icloud.com`), `chat_id:123`, `chat_guid:iMessage;-;+1234567890`, wildcard `*`.

> ⚠️ The iMessage channel performs a runtime macOS check. On non-macOS systems it will raise a clear error at startup.

**Technical details:** JSON-RPC over stdio with imsg CLI. Creates `watch.subscribe` on startup for real-time message streaming (not polling). Supports iMessage + SMS dual channel. Attachments read from local paths. No public IP needed.

---

## Usage

```bash
# Single-channel (traditional, backward-compatible)
python bot/telegram_bot.py
python bot/feishu_bot.py

# Multi-channel runner (runs any combination in one process)
python -m bot.run --channels telegram
python -m bot.run --channels feishu
python -m bot.run --channels telegram,feishu
python -m bot.run --channels dingtalk
python -m bot.run --channels discord
python -m bot.run --channels slack
python -m bot.run --channels wechat
python -m bot.run --channels qq
python -m bot.run --channels email
python -m bot.run --channels imessage        # macOS only
python -m bot.run --channels telegram,feishu,dingtalk --health-port 8080
python -m bot.run --list  # list all 9 available channels

# Makefile shortcuts
make bot-telegram
make bot-feishu
make bot-multi CHANNELS=telegram,feishu
make bot-list
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

---

## Security and Access Control

### Sender Allowlist

Every channel supports restricting who can interact with the bot via `allowed_senders`:

```bash
TELEGRAM_CHAT_ID=123456789                   # Telegram user IDs
DISCORD_ALLOWED_SENDERS=111222333444555666   # Discord user IDs
SLACK_ALLOWED_SENDERS=U0123ABCDEF            # Slack Member IDs
FEISHU_ALLOWED_SENDERS=ou_xxxxxxxxxxxx       # Feishu open_ids
EMAIL_ALLOWED_SENDERS=alice@example.com      # Email addresses
IMESSAGE_ALLOWED_SENDERS=+1234567890         # Phone or email
QQ_ALLOWED_SENDERS=12345678                  # QQ user IDs
```

> **For production deployments, always set an allowlist.** When the allowlist is empty, the channel accepts messages from anyone.

### Data Security

- All data stays on the local machine — no cloud uploads
- File paths are validated against a trusted directory whitelist (`data/`, `examples/`, `output/`, `OMICSCLAW_DATA_DIRS`)
- Path traversal attempts (e.g. `../../etc/passwd`) are blocked and logged
- File size limits enforced for uploads (50 MB files, 20 MB photos)
- Bot token redacted from all log output
- All path resolutions are logged in the audit trail

---

## Troubleshooting

### Bot not responding to messages

1. Check that the channel is configured correctly (bot token, app ID, etc.)
2. If using `allowed_senders`, ensure your user/chat ID is listed
3. For group chats, ensure the bot is @mentioned (default behavior)
4. Check logs for errors: `python -m bot.run --channels <name> --verbose`

### "channel X not found" or import errors

Install the channel-specific dependencies:
```bash
# See the Dependency Summary table above, or install all:
pip install -r bot/requirements-channels.txt
```

### Webhook channels (WeChat) not receiving messages

1. Ensure the webhook URL is publicly reachable (not behind NAT without port forwarding)
2. For local development, use a tunnel: `ngrok http 9001`
3. Verify the callback URL matches exactly (including path)
4. For WeCom: add your server's public IP to the app's **Trusted IP** list

### WeChat API error `60020`

Add your server's public IP to the WeCom app's **Trusted IP** list in the admin console.

### Feishu "event loop already running" error

This is a known issue with `lark_oapi` — it uses a module-level event loop variable. OmicsClaw patches this automatically when running via `python -m bot.run`. If you see this error, ensure you're using the latest version of `bot/channels/feishu.py`.

### Token refresh failures

- Feishu/WeChat/DingTalk tokens auto-refresh with a safety margin before expiry
- If the refresh endpoint is unreachable (network issues), messages will fail until the next successful refresh
- Check proxy settings if your server requires a proxy

### Debug Logging

Enable verbose mode for detailed channel logs:

```bash
python -m bot.run --channels telegram --verbose
# or set environment variable:
export LOG_LEVEL=DEBUG
```

## Logging

Structured audit logs are written to `bot/logs/audit.jsonl`. Each entry includes timestamp, event type, and relevant metadata.
