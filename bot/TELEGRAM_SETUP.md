# Telegram Bot Configuration Guide

Complete setup guide for OmicsClaw Telegram bot with memory-enabled conversational interface.

## Prerequisites

- Python 3.11+
- Telegram account
- LLM API access (DeepSeek, Gemini, OpenAI, or custom endpoint)

## Quick Start (5 minutes)

```bash
# 1. Install dependencies
pip install -r bot/requirements.txt

# 2. Create bot and get token (see Step 1 below)
# 3. Configure .env (see Step 2 below)
# 4. Run bot
python bot/telegram_bot.py
```

---

## Step 1: Create Telegram Bot

### 1.1 Talk to BotFather

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot` command
3. Follow prompts:
   - **Bot name**: `OmicsClaw` (or any display name)
   - **Bot username**: `omicsclaw_bot` (must end with `_bot`, must be unique)

4. BotFather will reply with your bot token:
   ```
   Done! Congratulations on your new bot.
   ...
   Use this token to access the HTTP API:
   123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
   ```

5. **Save this token** — you'll need it in Step 2

### 1.2 Configure Bot Settings (Optional but Recommended)

Send these commands to @BotFather to customize your bot:

```
/setdescription @omicsclaw_bot
```
Suggested description:
```
AI research assistant for multi-omics analysis. Supports spatial transcriptomics, single-cell, genomics, proteomics, and metabolomics. Remembers your datasets and preferences across sessions.
```

```
/setabouttext @omicsclaw_bot
```
Suggested about text:
```
OmicsClaw - Your persistent AI research partner for multi-omics analysis
```

```
/setcommands @omicsclaw_bot
```
Paste these commands:
```
start - Welcome message and instructions
skills - List all available analysis skills
demo - Run a skill demo (e.g., /demo preprocess)
status - Bot uptime and configuration
health - System health check
```

---

## Step 2: Configure Environment Variables

### 2.1 Create `.env` File

```bash
cd /path/to/OmicsClaw
cp .env.example .env
```

### 2.2 Edit `.env` with Required Variables

Open `.env` in your editor and configure:

```bash
# ============================================
# LLM Configuration (Required)
# ============================================

# Choose provider: deepseek, gemini, openai, custom
LLM_PROVIDER=deepseek

# API key from your LLM provider
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Override model (uses provider default if not set)
# OMICSCLAW_MODEL=deepseek-chat

# Optional: Override base URL (auto-set by provider)
# LLM_BASE_URL=https://api.deepseek.com

# ============================================
# Telegram Configuration (Required)
# ============================================

# Bot token from @BotFather (Step 1)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890

# Optional: Admin chat ID (bypass rate limits)
# Get your chat ID: send /start to @userinfobot
# TELEGRAM_CHAT_ID=123456789

# ============================================
# Bot Behavior (Optional)
# ============================================

# Rate limiting (messages per user per hour)
RATE_LIMIT_PER_HOUR=10

# Data directories (comma-separated, for large file access)
# OMICSCLAW_DATA_DIRS=/mnt/nas/spatial_data,/home/user/experiments
```

### 2.3 LLM Provider Configuration

Choose one provider and configure accordingly:

#### Option A: DeepSeek (Recommended for cost)

```bash
LLM_PROVIDER=deepseek
LLM_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Uses deepseek-chat by default
```

Get API key: https://platform.deepseek.com/api_keys

#### Option B: Google Gemini (Recommended for speed)

```bash
LLM_PROVIDER=gemini
LLM_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Uses gemini-2.0-flash by default
```

Get API key: https://aistudio.google.com/apikey

#### Option C: OpenAI

```bash
LLM_PROVIDER=openai
LLM_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Uses gpt-4o by default
```

Get API key: https://platform.openai.com/api-keys

#### Option D: Custom Endpoint

```bash
LLM_PROVIDER=custom
LLM_API_KEY=your-api-key
LLM_BASE_URL=https://your-endpoint.com/v1
OMICSCLAW_MODEL=your-model-name
```

---

## Step 3: Run the Bot

### 3.1 Start Bot

```bash
python bot/telegram_bot.py
```

Expected output:
```
2026-03-15 09:00:00 - INFO - Bot started successfully
2026-03-15 09:00:00 - INFO - LLM provider: deepseek
2026-03-15 09:00:00 - INFO - Model: deepseek-chat
2026-03-15 09:00:00 - INFO - Memory system initialized
2026-03-15 09:00:00 - INFO - Listening for messages...
```

### 3.2 Test Bot

1. Open Telegram and search for your bot username (e.g., `@omicsclaw_bot`)
2. Send `/start` command
3. Bot should reply with welcome message

### 3.3 Test Analysis

Send a natural language query:
```
User: "Run preprocessing demo"
Bot: ✅ [Executes spatial-preprocessing with demo data]
     📊 [Sends QC plots and report]
     💾 [Saves to memory: demo_visium.h5ad, 200 spots, normalized]
```

---

## Step 4: Verify Memory System

Test that memory persists across sessions:

### Session 1:
```
You: "Run preprocessing demo"
Bot: ✅ Done. [Saves DatasetMemory + AnalysisMemory]
```

### Stop and restart bot:
```bash
# Press Ctrl+C to stop
python bot/telegram_bot.py  # Restart
```

### Session 2:
```
You: "What data do I have?"
Bot: 🧠 "You have demo_visium.h5ad (Visium, 200 spots, normalized)"
```

If the bot remembers your data, memory system is working correctly!

---

## Advanced Configuration

### Admin Access (Bypass Rate Limits)

Get your Telegram chat ID:
1. Send `/start` to [@userinfobot](https://t.me/userinfobot)
2. Copy your chat ID (e.g., `123456789`)
3. Add to `.env`:
   ```bash
   TELEGRAM_CHAT_ID=123456789
   ```

Admin users bypass rate limits and get priority processing.

### Large File Access

For datasets > 50 MB (typical for spatial transcriptomics):

1. Place files in server directories:
   ```bash
   mkdir -p data/
   cp /path/to/brain_visium.h5ad data/
   ```

2. Configure data directories in `.env`:
   ```bash
   OMICSCLAW_DATA_DIRS=/mnt/nas/spatial_data,/home/user/experiments
   ```

3. Reference files in chat:
   ```
   You: "Preprocess data/brain_visium.h5ad"
   Bot: ✅ [Processes file from server]
   ```

Bot automatically searches: `data/`, `examples/`, `output/`, and `OMICSCLAW_DATA_DIRS`.

### Custom Rate Limits

Adjust rate limiting in `.env`:
```bash
# Allow 20 messages per user per hour
RATE_LIMIT_PER_HOUR=20

# Disable rate limiting (not recommended for public bots)
# RATE_LIMIT_PER_HOUR=0
```

---

## Troubleshooting

### Bot doesn't respond

**Check 1: Token is correct**
```bash
# Test token with curl
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

Should return bot info. If error, token is invalid.

**Check 2: Bot is running**
```bash
ps aux | grep telegram_bot.py
```

**Check 3: Check logs**
```bash
tail -f bot/logs/audit.jsonl
```

### LLM errors

**Check 1: API key is valid**
```bash
# Test DeepSeek
curl https://api.deepseek.com/chat/completions \
  -H "Authorization: Bearer $LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"test"}]}'
```

**Check 2: Provider is correct**
```bash
# Verify .env
grep LLM_PROVIDER .env
grep LLM_API_KEY .env
```

### Memory not persisting

**Check 1: Database exists**
```bash
ls -lh bot_memory.db
```

Should show SQLite database file.

**Check 2: Check memory logs**
```python
# In Python console
import aiosqlite
import asyncio

async def check():
    async with aiosqlite.connect("bot_memory.db") as db:
        async with db.execute("SELECT COUNT(*) FROM sessions") as cursor:
            count = await cursor.fetchone()
            print(f"Sessions: {count[0]}")

asyncio.run(check())
```

### Rate limit issues

**Temporary bypass for testing:**
```bash
# In .env
RATE_LIMIT_PER_HOUR=0
```

**Or add yourself as admin:**
```bash
TELEGRAM_CHAT_ID=<your_chat_id>
```

---

## Security Best Practices

### 1. Protect Your Tokens

```bash
# Never commit .env to git
echo ".env" >> .gitignore

# Set restrictive permissions
chmod 600 .env
```

### 2. Limit Data Access

Only add trusted directories to `OMICSCLAW_DATA_DIRS`:
```bash
# ✅ Good: Specific project directories
OMICSCLAW_DATA_DIRS=/mnt/nas/spatial_data,/home/user/omics_projects

# ❌ Bad: Root or home directories
# OMICSCLAW_DATA_DIRS=/,/home/user
```

### 3. Monitor Usage

Check audit logs regularly:
```bash
# View recent activity
tail -n 100 bot/logs/audit.jsonl | jq .

# Count messages per user
jq -r '.user_id' bot/logs/audit.jsonl | sort | uniq -c | sort -rn
```

### 4. Rate Limiting

Keep rate limits enabled for public bots:
```bash
RATE_LIMIT_PER_HOUR=10  # Reasonable default
```

---

## Running in Production

### Using systemd (Linux)

Create `/etc/systemd/system/omicsclaw-telegram.service`:

```ini
[Unit]
Description=OmicsClaw Telegram Bot
After=network.target

[Service]
Type=simple
User=omicsclaw
WorkingDirectory=/path/to/OmicsClaw
Environment="PATH=/path/to/OmicsClaw/.venv/bin"
ExecStart=/path/to/OmicsClaw/.venv/bin/python bot/telegram_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable omicsclaw-telegram
sudo systemctl start omicsclaw-telegram
sudo systemctl status omicsclaw-telegram
```

### Using Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . /app

RUN pip install -e . && pip install -r bot/requirements.txt

CMD ["python", "bot/telegram_bot.py"]
```

Build and run:
```bash
docker build -t omicsclaw-telegram .
docker run -d --name omicsclaw-bot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/bot_memory.db:/app/bot_memory.db \
  omicsclaw-telegram
```

### Using screen (Quick solution)

```bash
# Start in detached screen
screen -dmS omicsclaw python bot/telegram_bot.py

# Reattach to view logs
screen -r omicsclaw

# Detach: Ctrl+A, then D
```

---

## Bot Commands Reference

| Command | Description | Example |
|---------|-------------|---------|
| `/start` | Welcome message | `/start` |
| `/skills` | List all 50+ skills | `/skills` |
| `/demo <skill>` | Run skill demo | `/demo preprocess` |
| `/status` | Bot uptime & config | `/status` |
| `/health` | System health check | `/health` |

---

## Natural Language Examples

The bot understands natural language queries:

```
"Preprocess my Visium data" → spatial-preprocessing
"Find spatial domains" → spatial-domain-identification
"Detect spatially variable genes" → spatial-svg-detection
"Run differential expression" → spatial-de
"Analyze cell communication" → spatial-cell-communication
```

---

## Memory System Features

The bot remembers across sessions:

- 📁 **Datasets** — File paths, platforms, dimensions, preprocessing state
- 📊 **Analyses** — Methods, parameters, execution time, lineage
- ⚙️ **Preferences** — Clustering methods, plot styles, defaults
- 🧬 **Insights** — Biological annotations (cluster labels, domains)
- 🔬 **Project context** — Species, tissue type, research goals

See [docs/MEMORY_SYSTEM.md](../docs/MEMORY_SYSTEM.md) for detailed comparison.

---

## Support

- **Documentation**: [bot/README.md](./README.md)
- **Issues**: https://github.com/TianGzlab/OmicsClaw/issues
- **Memory system**: [docs/MEMORY_SYSTEM.md](../docs/MEMORY_SYSTEM.md)

---

## Comparison: Telegram vs Feishu

| Feature | Telegram | Feishu |
|---------|----------|--------|
| Setup complexity | ⭐ Simple (5 min) | ⭐⭐⭐ Complex (requires version publish) |
| Public IP required | ❌ No | ❌ No (WebSocket) |
| File upload limit | 50 MB | 20 MB |
| Image support | ✅ Yes | ✅ Yes |
| Rate limiting | ✅ Built-in | ⚠️ Manual |
| Admin bypass | ✅ Via chat ID | ❌ No |
| Best for | Individual researchers, small teams | Enterprise, Chinese users |

**Recommendation**: Start with Telegram for easier setup. Switch to Feishu if you need enterprise integration or are in China.
