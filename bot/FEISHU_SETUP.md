# 飞书机器人配置极简指南 / Feishu Bot Setup Guide

[English version below](#feishu-lark-bot-configuration-guide-english)

为了成功运行并测试飞书长连接机器人，必须在飞书开发者后台完成权限配置与版本发布流程。因为配置事件订阅等操作时，飞书往往需要检验目的地的存活情况，所以**你需要先保证长连接脚本在本地跑起来**，再去后台配置。

## 飞书机器人配置指南 (中文)

### 第一步：准备并运行长连接测试 (`run_longConnect.py`)
在正式进行后台配置和运行主代码之前，先跑通基础连通性测试代码并让其保持运行。

1. **新建测试脚本 `run_longConnect.py`**：将以下内容保存到你的项目根目录下。
   ```python
   import os
   from dotenv import load_dotenv
   import lark_oapi as lark

   def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
       print(f'[ do_p2_im_message_receive_v1 access ], data: {lark.JSON.marshal(data, indent=4)}')

   def do_message_event(data: lark.CustomizedEvent) -> None:
       print(f'[ do_customized_event access ], type: message, data: {lark.JSON.marshal(data, indent=4)}')

   event_handler = lark.EventDispatcherHandler.builder("", "") \
       .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
       .register_p1_customized_event("out_approval", do_message_event) \
       .build()

   def main():
       load_dotenv()
       app_id = os.environ.get("FEISHU_APP_ID")
       app_secret = os.environ.get("FEISHU_APP_SECRET")
       
       if not app_id or not app_secret:
           print("Error: 请先在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
           return

       cli = lark.ws.Client(app_id, app_secret,
                            event_handler=event_handler,
                            log_level=lark.LogLevel.DEBUG)
       cli.start()

   if __name__ == "__main__":
       main()
   ```
2. **配置凭证**：由于代码引入了 `dotenv` 去读取 `.env` 环境变量，你不再需要硬编码密钥（保证了安全）。执行前请确保你在根目录下的 `.env` 文件里已填好好真实的 `FEISHU_APP_ID` 和 `FEISHU_APP_SECRET`。
3. **运行测试脚本**：
   ```bash
   pip install lark-oapi  # 确保依赖已安装
   python run_longConnect.py
   ```
   如果在终端看到 `connected to wss://...` 等 debug 日志，说明程序在本地监听成功。**请保持该终端窗口运行，不要关闭**，继续进行后续的后台配置！

### 第二步：飞书后台补全权限与事件订阅
1. 登录 [飞书开发者后台](https://open.feishu.cn/app)，点击进入你的应用。
2. **添加机器人能力**：在左侧导航树 -> **添加应用能力** 中，确认你已经成功开启了 **“机器人”** 功能。
3. **配置权限管理**：在左侧导航树 -> **权限管理** 中，搜索并添加以下必备权限：
   - 接收单聊、群聊消息 (`im:message.p2p_msg` / `im:message.receive_v1`)
   - 获取与发送单聊、群组消息 / 以应用身份发送消息 (`im:message:send_as_bot`)
   - 接收群聊中@机器人消息事件
   - 获取与上传图片或文件资源 (`im:resource`)，用于读取用户发送的数据和图片文件
   - 获取群组信息 (`im:chat`)
4. **开启长连接**：在左侧导航树 -> **事件与回调** 中。由于我们第一步运行的代码使用的是 WebSocket 长连接，**不要在页面上配置请求网址 (Webhook)**，而是直接开启右上角的 **“长连接（云端到本地设备）”** 或客户端模式。
5. **添加事件订阅**：在“事件与回调 / 事件订阅”页面，点击“添加事件”，搜索并添加 **接收消息** (`im.message.receive_v1`) 事件。

### 第三步：发布新版本（极其关键的易错点）
> ⚠️ **核心机制警示**：飞书机制规定，你在后台修改的任何权限、事件订阅配置，**点击保存后都不会立刻生效！必须创建一个全新的应用版本并走完发布流程。** 90% 的初学者都会卡在这里，导致发消息没反应。

1. 在左侧导航树 -> **版本发布与审核** (Version Management & Release)。
2. 点击页面右上角的 **“创建版本”**。
3. 随机填写一个版本号（例如 `1.0.1`）以及更新说明。
4. 在页面底部的“已申请的权限”列表中仔细核对，确保你上面添加的“接收消息”等权限都在其中。
5. 点击 **申请发布**。（如果是企业测试环境通常会自动审核通过生效；如果是线上则需管理员审批）。

只有版本状态显示为“已发布”上线后，刚才运行在终端的长连接或者后续的 `feishu_bot.py` 才能真正接收到平台下发的消息。这时你可以试着向机器人发条消息，如果第一步的终端打印出 JSON 事件回调，说明配置 100% 成功！
测试完成后，你可以按 `Ctrl+C` 停止运行 `run_longConnect.py`，然后启动正式代码：`python bot/feishu_bot.py`。

---

## Feishu (Lark) Bot Configuration Guide (English)

To successfully run and test the Feishu long-connection bot, you must configure permissions and publish a version in the Feishu Developer Console. Because configuring things like event subscriptions often checks if the destination logic is alive, **you should have the long connection script running locally first**.

### Step 1: Prepare and Run the Connection Test (`run_longConnect.py`)
Before diving into console configuration, run the basic connection test script and let it stand by.

1. **Create the test script `run_longConnect.py`**: Save the following in your project root.
   ```python
   import os
   from dotenv import load_dotenv
   import lark_oapi as lark

   def do_p2_im_message_receive_v1(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
       print(f'[ do_p2_im_message_receive_v1 access ], data: {lark.JSON.marshal(data, indent=4)}')

   def do_message_event(data: lark.CustomizedEvent) -> None:
       print(f'[ do_customized_event access ], type: message, data: {lark.JSON.marshal(data, indent=4)}')

   event_handler = lark.EventDispatcherHandler.builder("", "") \
       .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1) \
       .register_p1_customized_event("out_approval", do_message_event) \
       .build()

   def main():
       load_dotenv()
       app_id = os.environ.get("FEISHU_APP_ID")
       app_secret = os.environ.get("FEISHU_APP_SECRET")
       
       if not app_id or not app_secret:
           print("Error: Please set FEISHU_APP_ID and FEISHU_APP_SECRET in .env first")
           return

       cli = lark.ws.Client(app_id, app_secret,
                            event_handler=event_handler,
                            log_level=lark.LogLevel.DEBUG)
       cli.start()

   if __name__ == "__main__":
       main()
   ```
2. **Configure Credentials**: The script uses `python-dotenv` to securely retrieve tokens. Ensure that your actual `FEISHU_APP_ID` and `FEISHU_APP_SECRET` are correctly set inside the `.env` file so you do not have to hardcode them.
3. **Run the test**:
   ```bash
   pip install lark-oapi
   python run_longConnect.py
   ```
   If you see debugging messages like `connected to wss://...`, the script is listening correctly. **Do not close this terminal!** Leave it running while you proceed to step 2.

### Step 2: Configure Permissions and Event Subscriptions
1. Log in to the [Feishu Developer Console](https://open.feishu.cn/app) and enter your app.
2. **Add Bot Capability**: Navigate to **Add Features** on the left menu and confirm you have successfully enabled the **"Bot"** feature.
3. **Manage Permissions**: Go to **Permissions** on the left menu, search for, and add the following required permissions:
   - Read single/group chat messages (`im:message.p2p_msg` / `im:message.receive_v1`)
   - Receive @bot events in groups
   - Send messages as bot (`im:message:send_as_bot`)
   - Upload and download resource files (`im:resource`)
   - Read group info (`im:chat`)
4. **Enable Long Connection**: Go to **Event Subscriptions** on the left menu. Since our terminal script actively uses a WebSocket, **do not configure a Request URL (Webhook)**. Instead, directly enable the **"Long Connection"** option.
5. **Add Event Subscriptions**: Still in "Event Subscriptions" settings, click "Add events", then search and add the **Receive message** (`im.message.receive_v1`) event.

### Step 3: Publish a New Version (Crucial Step!)
> ⚠️ **CAUTION**: Feishu's mechanism dictates that any changes to permissions or event subscriptions **do not take effect immediately upon saving! You must create and publish a new application version.** 90% of developers get stuck here.

1. Navigate to **Version Management & Release** on the left menu.
2. Click the **"Create a version"** button in the upper right corner.
3. Provide an App version number (e.g., `1.0.1`) and update notes.
4. Double-check the "Requested privileges" list at the bottom of the page to ensure your newly added permissions (like "Receive message", "Send as bot") are included.
5. Click **Submit for release**. (Requires approval unless you are in a test tenant.)

Your Python bot execution will only be able to receive messages properly **after** the version status successfully transitions to "Published". Once published, send a test message to the bot. If your terminal from step 1 prints the JSON event payload, your permissions and setup are 100% correct! You can press `Ctrl+C` to close the test script and launch the primary bot via `python bot/feishu_bot.py`.
