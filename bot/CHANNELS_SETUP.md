# OmicsClaw Channels Setup Guide

This document provides detailed, step-by-step configuration guides for all supported messaging platforms in OmicsClaw.

## Table of Contents
- [Telegram (Recommended for quick start)](#1-telegram)
- [Feishu / Lark (Recommended for enterprise)](#2-feishu-lark)
- [DingTalk 钉钉](#3-dingtalk-)
- [Discord](#4-discord)
- [Slack](#5-slack)
- [WeChat企业微信 / 公众号](#6-wechat---)
- [QQ](#7-qq)
- [Email](#8-email)
- [iMessage (macOS only)](#9-imessage-macos-only)

---

## 1. Telegram

Telegram is the easiest channel to set up. It offers quick bot creation, unlimited messaging, and built-in rate limiting capabilities.

### 1.1 Create Telegram Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send the `/newbot` command
3. Follow prompts:
   - **Bot name**: `OmicsClaw` (or any display name)
   - **Bot username**: `omicsclaw_bot` (must end with `_bot`, must be unique)
4. BotFather will reply with your bot token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890`). **Save this token securely.**

### 1.2 Configure Bot Settings (Recommended)

Send these commands to @BotFather to customize your bot:

- `/setdescription @omicsclaw_bot` -> "AI research assistant for multi-omics analysis. Supports spatial transcriptomics, single-cell, genomics, proteomics, and metabolomics."
- `/setabouttext @omicsclaw_bot` -> "OmicsClaw - Your persistent AI research partner."
- `/setcommands @omicsclaw_bot` -> 
  ```text
  start - Welcome message and instructions
  skills - List all available analysis skills
  demo - Run a skill demo
  status - Bot uptime and configuration
  health - System health check
  ```

### 1.3 Configure `.env`

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567890

# Optional: Admin chat ID to bypass rate limits
# Get your chat ID by sending /start to @userinfobot
# TELEGRAM_CHAT_ID=123456789
```

---

## 2. Feishu (Lark)

**⚠️ CRITICAL WARNING:** Feishu's mechanism dictates that any changes to permissions or event subscriptions **do not take effect immediately upon saving! You must create and publish a new application version.** 90% of developers get stuck here.

### 2.1 Prepare and Run the Connection Test

Before diving into console configuration, you must have the long connection script running locally because Feishu validates webhook/connection status.

```bash
# Start the bot locally first!
python -m bot.run --channels feishu
```
If you see debugging messages indicating WebSocket connection success, leave the terminal running and proceed to the next step.

### 2.2 Configure Permissions and Event Subscriptions

1. Log in to the [Feishu Developer Console](https://open.feishu.cn/app) (or [Lark Developer](https://open.larksuite.com/app)) and create a custom app.
2. **Add Bot Capability**: Navigate to **Add Features** on the left menu and enable the **"Bot"** feature.
3. **Manage Permissions**: Go to **Permissions** on the left menu. **Permission type must be "Application Permission"**. Add these required permissions:
   - ✅ Read single/group chat messages (`im:message.p2p_msg` / `im:message.receive_v1`)
   - ✅ Receive @bot events in groups
   - ✅ Send messages as bot (`im:message:send_as_bot`)
   - ⚠️ **Get all messages in group chat** (`im:message.group_msg`) - **Critical permission for group chats.**
   - ✅ Upload and download resource files (`im:resource`)
   - ✅ Read group info (`im:chat`)
4. **Enable Long Connection**: Go to **Event Subscriptions**. **Do not configure a Request URL (Webhook)**. Instead, directly enable the **"Long Connection"** option.
5. **Add Event Subscriptions**: Still in "Event Subscriptions", click "Add events", then search and add the **Receive message** (`im.message.receive_v1`) event.

### 2.3 Publish a New Version (Crucial Step!)

1. Navigate to **Version Management & Release**.
2. Click **"Create a version"**.
3. Provide an App version number (e.g., `1.0.1`) and update notes.
4. Double-check the "Requested privileges" list at the bottom to ensure ALL permissions you added above are included.
5. Click **Submit for release**. 

Your bot will only be able to receive messages properly **after** the version status successfully transitions to "Published".

### 2.4 Configure `.env`

```bash
FEISHU_APP_ID=cli_xxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxx
```

---

## 3. DingTalk 钉钉

1. Create a robot at [DingTalk Open Platform](https://open-dev.dingtalk.com).
2. Go to **Features** -> **Robot** and enable it.
3. Enable **Stream Mode (长连接)** - This allows receiving messages via WebSocket without needing a public IP.
4. Publish the app and add the bot to a group, or test via direct message.
5. Set variables in `.env`:
   ```bash
   DINGTALK_CLIENT_ID=ding...
   DINGTALK_CLIENT_SECRET=xxxxxxxxxxxxxxxxxx
   ```

---

## 4. Discord

1. Go to [Discord Developer Portal](https://discord.com/developers/applications) and create a New Application.
2. Left menu **Bot** -> Reset Token -> Copy the Bot Token.
3. **CRITICAL**: Under **Privileged Gateway Intents**, enable **Message Content Intent**.
4. Left menu **OAuth2** -> URL Generator:
   - Scopes: check `bot`
   - Bot Permissions: check `Send Messages`, `Read Message History`, `Attach Files`, `Add Reactions`
   - Copy the generated URL, open in browser, select a server to invite the bot.
5. Set variables in `.env`:
   ```bash
   DISCORD_BOT_TOKEN=MTIzNDU2Nzg5.xxxx.xxxxx
   ```

---

## 5. Slack

1. Go to [Slack API App Dashboard](https://api.slack.com/apps) and Create New App (From scratch).
2. Go to **Socket Mode** -> enable -> Generate App-Level Token (scope `connections:write`). Copy this `xapp-...` token.
3. Go to **OAuth & Permissions** -> add these Bot Token Scopes: 
   `chat:write`, `channels:history`, `groups:history`, `im:history`, `files:read`, `files:write`, `reactions:write`
4. Click **Install to Workspace** -> copy the Bot User OAuth Token (`xoxb-...`).
5. Go to **Event Subscriptions** -> enable -> Subscribe to bot events: `message.channels`, `message.groups`, `message.im`, `app_mention`.
6. Set variables in `.env`:
   ```bash
   SLACK_BOT_TOKEN=xoxb-xxxx-xxxx-xxxx
   SLACK_APP_TOKEN=xapp-1-xxxx-xxxx
   ```

---

## 6. WeChat 企业微信 / 公众号

WeChat requires a publicly accessible webhook URL (port `9001` by default). For local development, use `ngrok http 9001`.

### Option A: WeCom (企业微信) - Recommended
1. Log in to [WeCom Admin Console](https://work.weixin.qq.com/) -> App Management -> create a custom app.
2. Copy the **Corp ID** (from "My Enterprise"), **AgentId**, and **Secret** (from the App).
3. In app details -> **Receive Messages** -> Set API Receive -> URL: `http://your-server-ip:9001/wechat/callback`
4. Copy **Token** and **EncodingAESKey**.
5. **CRITICAL**: In app details -> **Trusted IP** -> add your server's public IP address. Without this, WeChat APIs will fail with error `60020`.
6. Configure `.env`:
   ```bash
   WECOM_CORP_ID=ww...
   WECOM_AGENT_ID=1000002
   WECOM_SECRET=xxxxxxxxxxxxxxxxxx
   WECOM_TOKEN=xxxxxxxxxxxxxxxxxx          
   WECOM_ENCODING_AES_KEY=xxxxxxxxxxxxxxxxxx 
   ```

### Option B: WeChat Official Account (微信公众号)
1. Log in to [WeChat Official Account Platform](https://mp.weixin.qq.com/) -> Settings & Development -> Basic Configuration.
2. Copy **AppID** and **AppSecret**.
3. Configure Server URL: `http://your-server-ip:9001/wechat/callback`
4. Configure `.env`:
   ```bash
   WECHAT_APP_ID=wx...
   WECHAT_APP_SECRET=xxxxxxxxxxxxxxxxxx
   ```

---

## 7. QQ

1. Register as a developer at [QQ Open Platform](https://q.qq.com/).
2. Create a bot application and complete developer verification.
3. Copy the **App ID** and **App Secret**.
4. In the bot dashboard, ensure you enable the "C2C消息" (Direct Message) and "群聊消息" (Group Chat) intents.
5. Search for and add the bot as a friend in QQ, or add it to a group.
6. Configure `.env`:
   ```bash
   QQ_APP_ID=xxxxxxxxxx
   QQ_APP_SECRET=xxxxxxxxxxxxxxxxxx
   ```

---

## 8. Email

Email operates as a channel by polling an IMAP inbox and responding via SMTP.

1. Prepare an email account (Gmail, Outlook, custom domain).
2. For **Gmail**, you must enable 2FA and generate an **App Password** (standard passwords will not work). Go to [Google App Passwords](https://myaccount.google.com/apppasswords).
3. Ensure IMAP access is enabled in the account settings.
4. Configure `.env`:
   ```bash
   EMAIL_IMAP_HOST=imap.gmail.com
   EMAIL_IMAP_PORT=993
   EMAIL_IMAP_USERNAME=your-bot@gmail.com
   EMAIL_IMAP_PASSWORD=your-app-password
   
   EMAIL_SMTP_HOST=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   EMAIL_SMTP_USERNAME=your-bot@gmail.com
   EMAIL_SMTP_PASSWORD=your-app-password
   
   EMAIL_FROM_ADDRESS=your-bot@gmail.com
   ```

---

## 9. iMessage (macOS only)

iMessage integration relies on the `imsg` CLI and requires a macOS host natively signed into Messages.app.

1. Ensure Messages.app is signed into iCloud and functioning locally.
2. Install the `imsg` CLI via Homebrew:
   ```bash
   brew install anthropics/tap/imsg
   ```
3. Verify installation: `imsg --version`
4. **CRITICAL**: Grant your Terminal app (or IDE) **"Full Disk Access"** in macOS `System Settings -> Privacy & Security`. This is required to read the iMessage `chat.db`.
5. Configure `.env`:
   ```bash
   IMESSAGE_CLI_PATH=/opt/homebrew/bin/imsg    # Or $(which imsg)
   IMESSAGE_ALLOWED_SENDERS=+1234567890,user@icloud.com
   ```
   > Recommended: Always set an allowlist for iMessage to prevent the bot from responding to unintended personal messages.
