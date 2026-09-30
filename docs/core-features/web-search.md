# 网页搜索与抓取

OmicsClaw 用两个内置工具让 agent 访问互联网：`web_search` 搜索并返回标题、URL、摘要列表，`web_fetch` 抓取一个 URL 并把它化简成 Markdown。两者都**不需要 API Key**，**只用标准库**，每个请求都要经过同一道 SSRF 闸门，并且**会把 socket 钉到闸门验证过的那个 IP 上**。

对应重建步骤 Step 4.5（计划 0029）。安全边界的核心是：**两个工具都自己声明要求审批（`ASK`），审批卡片展示完整的 URL 或搜索词，并明确提示这些内容会离开本机**。因为对多组学 agent 来说，真正的风险是请求里带出去的数据，而不是抓回来的内容。

---

## 1. 设计决策

### 1.1 为什么内置，而不是交给 MCP

选择开箱即用：DuckDuckGo 的 HTML 端点不需要 Key，HTML 化简用标准库的 `html.parser` 完成，整条链路不依赖任何外部平台账号，也不需要 vendor SDK。`omicsclaw/tools/` 这一层只能 import 标准库，这也是唯一可行的形态。

### 1.2 工具保持原子化，深度搜索交给 LLM

工具只提供两种原子能力：搜索（给出候选链接）和抓取（读取一页）。要不要继续跟链接、要不要换关键词、什么时候停，都由模型在 ReAct 循环里决定。`web_search` 的描述明确要求"先搜索，再把一个 URL 交给 `web_fetch` 去读"。

### 1.3 审批针对请求，不针对响应

`SAFETY_RULES` 第 1 条是**遗传数据不离开本机**。URL 本身就是一条出站通道：路径和查询串会被完整发送出去，而模型在被要求"查一下这个标识符"时，会把标识符写进 URL 或搜索词。SSRF 闸门对这种泄漏无能为力，因为对它来说 `https://example.com/?q=<patient-id>` 和其他公网地址没有区别。所以：

- 两个工具都是 `ApprovalMode.ASK`，并且 `prompts_for_itself=True`，由工具自己用描述实际效果的文字发问；
- 审批卡片展示**完整 URL**或**完整搜索词**，不做任何省略，并明确写出"这些内容会离开本机，只有在其中不含用户文件里的数据时才批准"；
- 工具描述本身也用大写提醒模型：不要把用户文件、序列、样本标识、病人信息放进 URL 或搜索词。

### 1.4 "外部世界的失败"不等于"工具失败"

404、500、不支持的内容类型、连接重置、TLS 失败、超时、零结果，都是**关于外部世界的事实**，工具把它们作为普通文本返回，`is_error=False`。如果告诉模型"工具坏了"，它会去修工具。只有模型能通过**换一组参数**纠正的错误才会抛出：URL 格式不对、目标被拒（`UrlRefused`）、参数不符合 schema（`ToolArgumentError`）。这些由注册表转成 `is_error=True` 的 Observation。

### 1.5 注入当前日期

模型的训练截止日期与当前日期之间有差距。不注入日期时，模型搜索"最新版本"往往会带上过时的年份。`entry/assembly.py` 的 `_environment_source` 在 system prompt 的 `## Environment` 段里写入：

```
- Workspace: /path/to/workspace
- Platform: Linux (linux)
- Today: 2026-09-23
```

**只写日期，不写时间戳**：DeepSeek 和 OpenAI 都按字节精确的前缀缓存，日期每天只让缓存失效一次，时钟读数则每一轮都会让它失效。这一段在每轮渲染时重新求值，所以跨过午夜的进程也会拿到新日期。它排在 system prompt 的后部（skills 段之后、长期记忆段之前），尽量少影响缓存前缀。

---

## 2. 工具接口

### 2.1 `web_search`

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|:-:|---|---|
| `query` | string | ✅ | — | 搜索词，英文效果通常更好。去掉首尾空白后为空则抛 `ToolArgumentError` |
| `max_results` | integer | ❌ | 5 | 返回条数，超过 10 按 10 处理；非正数取默认值 |

输出格式：

```
[1] GSE123456 - GEO Accession viewer
URL: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE123456
Snippet: Single-cell RNA-seq of ...

[2] ...
```

没有摘要时省略 `Snippet:` 行。

### 2.2 `web_fetch`

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|:-:|---|---|
| `url` | string | ✅ | — | 绝对 URL，以 `http://` 或 `https://` 开头 |
| `max_chars` | integer | ❌ | 8,000 | 返回字符上限，超过 32,000 按 32,000 处理；非正数取默认值 |

HTML 页面的输出格式：

```markdown
# <title，或第一个 h1>

> Source: https://…

…正文（Markdown 形态）…

[Truncated: the first 7984 characters of 21530 are shown. Fetch the URL again with a larger max_chars, or read the rest another way]
```

两个 schema 都是 `additionalProperties: false`，参数不符合时，报错里会逐条列出问题。

### 2.3 策略

| 字段 | `web_fetch` | `web_search` | 说明 |
|---|---|---|---|
| `risk_level` | `HIGH` | `MEDIUM` | 风险等级跟随"影响范围"。`web_fetch` 的目标、路径、查询全由模型决定；`web_search` 只是把**一个字段**发往**固定端点** |
| `approval_mode` | `ASK` | `ASK` | 负载再小也是负载，发出去就收不回来 |
| `prompts_for_itself` | `True` | `True` | 工具自己发问，卡片上显示 URL 或搜索词 |
| `read_only` | `False` | `False` | 刻意不声明只读：一次 GET 也可能改动设计糟糕的 API，至少会在对方日志里留一行 |
| `concurrency_safe` | `True` | `True` | 不共享本地状态，`PinnedTransport` 不复用连接；同一轮里的多次抓取可以并行 |
| `touches_network` | `True` | `True` | — |
| `allowed_in_background` | `False` | `False` | 无人值守的 turn 里没有人能批准出站请求 |
| `tags` | `network, web, egress` | 同左 | — |

---

## 3. SSRF 防护（`omicsclaw/tools/_websafety.py`）

`_websafety.py` 对网络的作用，相当于 `_workspace.py` 对文件系统：每个会打开 socket 的工具都必须经过这道闸门，而 `PinnedTransport` 是唯一允许打开 socket 的东西。模块只用标准库，**连 `omicsclaw.schema` 都不 import**。

### 3.1 检查链

```
raw URL
  │
  ▼  inspect_url()  —— 离线，免费，在审批之前执行
① 非空
② 不含空格和控制字符（≤ 0x20 或 0x7f）
③ 能被 urlsplit 解析
④ scheme ∈ {http, https}（允许列表：file://、gopher://、http+unix:// 都会被拒）
⑤ 不含 userinfo（user:pass@host）
⑥ 端口可用、有主机名
  │  → UrlShape(url, scheme, host(小写), port(默认 80/443))
  ▼
  [审批]
  ▼  check_url() —— 在 PinnedTransport 内，经 asyncio.to_thread 调用
⑦ DNS：socket.getaddrinfo(AF_UNSPEC, SOCK_STREAM)，IPv4 与 IPv6 都查
     失败或无结果 → UrlNotResolvable（fail-closed）
⑧ 检查**每一个**解析结果：任何一个落在 BLOCKED_NETWORKS → UrlAddressBlocked
  │  → SafeTarget(shape, address=第一个结果)
  ▼
⑨ socket 钉到 SafeTarget.address（见 3.4）
```

拒绝类型的层次结构：`UrlRefused(ValueError)` → `UrlMalformed`、`UrlNotResolvable`、`UrlAddressBlocked`。区分这几个子类是为了读日志的运维人员：一次针对基础设施的尝试和一个手误不应出现在同一个标题下。

**第 ② 条是评估时发现的真实漏洞**：`urlsplit` 解析时会悄悄删掉 `\t`、`\r`、`\n`，但审批卡片展示的是原始字符串。于是 `?sample=\nHG00123` 在卡片上看起来像空查询，后面另起一行像是普通文字，实际发出的请求却把它们拼在了一起。原则是：**既然人的阅读是控制手段，人读到的就必须是实际发生的事。**

**第 ⑧ 条检查全部结果，而不只是第一个**：一个同时有公网 `A` 记录和 `127.0.0.1` 记录的域名，本身就构成一次不需要任何时间窗口的 rebinding 攻击。

### 3.2 `BLOCKED_NETWORKS`（14 段）

| 网段 | 说明 |
|---|---|
| `169.254.0.0/16` | 链路本地；AWS / Azure / GCP 的实例凭据端点 |
| `127.0.0.0/8` | IPv4 回环（整个 /8） |
| `10.0.0.0/8`、`172.16.0.0/12`、`192.168.0.0/16` | RFC 1918 私网 |
| `100.64.0.0/10` | 运营商 NAT |
| `fe80::/10` | IPv6 链路本地 |
| `fc00::/7` | IPv6 ULA |
| `::1/128` | IPv6 回环 |
| `0.0.0.0/8` | 在 Linux 上 `http://0.0.0.0:8080/` 能访问绑定在 `INADDR_ANY` 的服务，而它不在 `127.0.0.0/8` 内 |
| `224.0.0.0/4` | IPv4 组播 |
| `240.0.0.0/4` | 保留地址（含 `255.255.255.255`） |
| `::/128` | IPv6 未指定地址 |
| `64:ff9b::/96` | NAT64：`64:ff9b::7f00:1` 在有 NAT64 网关的网络里会路由到 `127.0.0.1` |

- **IPv4-mapped IPv6**（`::ffff:169.254.169.254`）在 `blocked_reason` 里先展开成 IPv4 再比较，一条 IPv4 规则同时覆盖两种写法。
- **`ipaddress` 无法解析的地址一律拒绝**。
- 刻意**不用** `IPv4Address.is_private`：它和这张表相近但不相等（不含 `100.64.0.0/10`，却包含文档地址段），审计部署时会读错表。

**Docker 沙箱不改变这一点**：沙箱只把 `bash` 放进容器，两个 web 工具仍在宿主机进程里运行，边界就是这道闸门。

### 3.3 重定向

重定向循环写在 `PinnedTransport.request` 里，不交给 `urllib`，因为 `urllib` 会在任何人看到之前就跟过去。

| 规则 | 说明 |
|---|---|
| 只跟随 `301 / 302 / 303 / 307 / 308` | `304`、`305` 不是重定向，所以不能用 `300 <= s < 400` 判断 |
| 最多 `MAX_REDIRECTS = 5` 跳 | 超过就抛 `UrlRefused`（多半是循环） |
| **每一跳都重新执行 `check_url` 并重新钉住** | 外网 URL 被 301 到内网地址时，在那一跳被拒 |
| `301/302/303` | 非 GET/HEAD 改为 GET，丢弃请求体 |
| `307/308` 且跨源、带请求体 | **直接拒绝**。这两个状态码要求"原样重发"，而原样重发给一个没人批准过的主机正是本模块要防的事；也不存在诚实的降级办法 |
| 跨源跳转 | 调用方的请求头全部换成 `{"Accept": "*/*"}` 加 `User-Agent`。API Key、cookie、bearer token 只属于原来的主机 |

"同源"指 `(scheme, host, port)` 三元组相同。评估发现最初的实现在 307/308 跨源时会重发请求体和全部请求头。

### 3.4 Socket pinning

如果只检查解析出来的地址，交给 HTTP 客户端的却是**主机名**，客户端会**再解析一次**。只要一条 TTL 很短的记录，就能让"检查过的连接"和"实际发生的连接"不是同一个。

OmicsClaw 的做法（`_connection` / `_pinned_connector`）：

```python
connection = http.client.HTTPSConnection(target.host, target.port, ...)   # host 仍是主机名
connection._create_connection = _pinned_connector(target)                 # 按实例替换连接器
# connect() 丢弃 http.client 传入的 (hostname, port)，
# 改为 socket.create_connection((target.address, target.port), ...)
```

- `HTTPConnection.host` 仍是主机名，所以 `Host` 请求头和 TLS SNI（`server_hostname`）都正确，**证书校验不受影响**。直接用 IP 构造会破坏所有虚拟主机和证书。
- 如果某个 Python 版本的 `HTTPConnection` 不再按实例持有 `_create_connection`，代码会 **`raise RuntimeError`**，而不是悄悄退回未经检查的解析器。
- 每个请求自己开连接、自己关，**不复用连接池**：多一次握手的代价，换来 DNS 变化后绝不会复用一条通往"曾经安全"的地址的连接。

### 3.5 超时与大小：整次调用只有一个预算

| 常量 | 值 | 作用 |
|---|---|---|
| `FETCH_TIMEOUT`（`web_fetch.py`） | 15 s | `web_fetch` 一次调用的总预算 |
| `SEARCH_TIMEOUT`（`web_search.py`） | 20 s | `web_search` 一次调用的总预算 |
| `DIAL_TIMEOUT` | 10 s | 单独限制 TCP 握手；握手完成后 socket 超时恢复为剩余预算 |
| `MAX_BODY_BYTES`（`_html.py`） | 1 MiB | 响应体最多读取这么多，超出部分截掉并置 `truncated=True` |

- **`timeout` 覆盖整次调用**，包括所有重定向跳和所有字节，不是每跳单独计时。按跳计时会让预算最多变成六倍。
- **读取用 `read1` 加单调时钟截止时间**：`BufferedReader.read` 会在内部循环直到读够字节，一个每次只滴一个字节、每个字节都落在 socket 超时内的服务器，可以让单次 `read` 永远不返回。`read1` 只要有数据就返回，截止时间因此能被及时检查。**最初的修复本身也不完整，是新写的测试发现的。**
- `_open` 通过 `asyncio.to_thread` 执行阻塞的 `http.client`。turn 被取消时 `await` 立即返回，后台线程则由自己的截止时间收尾。
- 网络失败（重置、TLS 错误、截止时间到）统一抛 `TransportFailed`（继承 `RuntimeError`，不是 `OSError`，这样不会被为别的目的写的 `except OSError` 吞掉），工具把它作为普通文本返回。
- `User-Agent: OmicsClaw/1.0`。

### 3.6 测试接缝，没有"关闭检查"的开关

`PinnedTransport(resolver=..., opener=...)`：

- `resolver` **削弱不了任何检查**：它返回的地址本身还要经过判定，测试可以把一个域名指到 `127.0.0.1` 看它被拒，却没法让 `127.0.0.1` 变得可接受。
- `opener` 是真正打开 socket 的东西，**位于信任边界之内**，这和 `bash` 的 `BashEnvironment` 一样，由组装注册表的人负责。

OmicsClaw 没有关闭安全检查的开关。

---

## 4. HTML 内容提取（`omicsclaw/tools/_html.py`）

这一层只能用标准库，**没有 readability，也没有 HTML→Markdown 转换器**。实际交付的管线如下：

```
响应体（最多 1 MiB）
  │ 按 Content-Type 的 charset 解码（未知或缺失时用 UTF-8，errors="replace"）
  ▼
Content-Type 分支（web_fetch.render）
  ├─ text/html、application/xhtml+xml → extract_page()
  ├─ text/*、application/json、application/xml、application/javascript → truncate_text()（原样返回）
  └─ 其他（PDF、图片、压缩包…）→ "returned content of type …, which this tool does not read (N bytes)"
                                     并建议用 bash 下载后交给能理解它的程序
  │
  ▼  _Extractor（html.parser.HTMLParser，单遍、无树）
  丢弃：script style noscript template svg canvas iframe          （_SKIP_TAGS）
  丢弃：nav header footer aside form                             （_BOILERPLATE_TAGS）
  保留结构：h1–h6 → "#"…；li → "- "；a → [text](url)；pre → ``` 围栏；
            td/th → " | "；块级标签 → 空行；br → 换行
  标题：<title>，没有则取第一个 h1–h6 的文字
  ▼
assemble_page(url, title, content, max_chars)
  "# 标题\n\n> Source: <url>\n\n<正文>"，超出上限时截断并附提示
```

要点：

- **截断尽量落在段落边界**：切在上限之前的最后一个换行处，但只在这个换行位于上限一半之后时才这样做，否则一个第 40 个字符处就换行的页面会被截成 40 个字符。截断提示会如实写出看到的字符数和总字符数。
- **按字符计数，不按字节计数**：对英文两者一致；对中文页面，同样的字数在字节上宽松约三倍，但模型付出的成本一样。
- **响应体超过 1 MiB 时不丢弃**：截掉超出部分，照常化简，并附 `[The page was larger than 1024 KiB and was cut off …]`。
- `javascript:` 和 `#` 开头的链接不输出链接语法；空锚点整个删掉，不留 `[](url)`。
- 重复的属性**取第一个**，与 HTML5 树构建算法一致，`web_search` 的 `_attribute` 也用同一规则。
- **与 readability 的差距要明说**：readability 通过给节点打分找出正文，所以会丢掉 `<div class="sidebar">`；固定标签表做不到。文档页和博客文章上两者相近，满是推广内容的新闻站点上这里会带回更多噪声。整个正文都放在 `<header>` 里的页面会得到空结果。

---

## 5. 搜索后端：DuckDuckGo HTML（`builtin/web_search.py`）

### 5.1 请求

```
POST https://html.duckduckgo.com/html/
Content-Type: application/x-www-form-urlencoded
User-Agent: OmicsClaw/1.0
Accept: text/html
Body: q=<urlencoded query>
```

使用 HTML 端点而不是 `api.duckduckgo.com`：后者返回 JSON，解析容易得多，但它只回答有结构化答案的查询，对普通查询几乎什么都不返回。请求同样走 `PinnedTransport`，同样受闸门和钉住约束，预算 20 s，响应体上限 1 MiB。

`WebSearchTool(endpoint=...)` 允许部署指向自建的元搜索实例。**构造时就用 `inspect_url` 校验**，拼写错误会让启动失败，而不是在某次对话中途被拒绝。每次请求仍然会执行 gate 并钉住，指向 `127.0.0.1` 的端点会被拒绝，这是有意为之。`build_app` 用默认参数构造它（`WebSearchTool()`），`AppConfig` 没有提供修改端点的配置项。

### 5.2 解析

`_ResultParser` 是基于流的 `HTMLParser`，自己维护嵌套深度：

| 选择器 | 目标 |
|---|---|
| `div.result`（排除 `div.result--more`） | 一条结果的容器；class 按空白切分后整词比较，`results-wrapper` 不会匹配 |
| `.result__a` | 标题文本和 `href` |
| `.result__snippet` | 摘要。**任何元素都接受**（DuckDuckGo 用过 `<a>` 和其他元素） |

- `_VOID_TAGS`（`br`、`img`、`input` 等）不计深度，否则摘要里的一个 `<br>` 会让计数器永远多一层，后面的结果全部被吞进第一条。
- 同时有标题和 URL 的块才保留，以此过滤广告和"相关搜索"。
- **`decode_redirect`**：DuckDuckGo 把每个结果包装成 `/l/?uddg=<encoded>&rut=…`，这里用 `parse_qs` 取出真实目标，**只解码一次**，重复解码会破坏含 `%2B`、`%25` 的目标。解包还有安全意义：下一轮 `web_fetch` 的审批卡片上显示的是真实目标，而不是一串 `duckduckgo.com/l/?uddg=…`。

### 5.3 三种"不是错误"的结果

| 情形 | 返回给模型 |
|---|---|
| 后端返回非 2xx（常见的是限流） | "The search backend answered HTTP … That is the backend's response rather than a tool failure — it rate-limits automated queries …" |
| 页面解析出零条 | 同时点出两种可能：查询确实没有匹配（换词），**或者后端改了页面结构**（换词也没用，需要修代码） |
| 网络失败 | "The search could not be delivered: … Try again later, or fetch a known URL directly with web_fetch." |

第二种是最可能真实发生的情况：`div.result`、`a.result__a` 这些 class 名随时可能因为改版而变化，而那时的失败形态是**零结果，不是报错**，所以返回文本必须能和改版区分。

---

## 6. 与权限、审计、子代理的关系

- **权限 gate**：两个工具都是 `prompts_for_itself=True`。默认模式下 gate 把问题交给工具，卡片显示工具自己的 `_reason`。规则文件按**主参数**匹配：`web_fetch` 是 `url`，`web_search` 是 `query`。例如：

  ```json
  {
    "permissions": {
      "allow": ["web_fetch(https://www.ncbi.nlm.nih.gov/*)", "web_fetch(https://eutils.ncbi.nlm.nih.gov/*)"],
      "deny":  ["web_search"]
    }
  }
  ```

  规则文件位于 `<workspace>/.omicsclaw/settings.json`。注意 glob 中的 `*` 可以匹配 `/`，但**只按字面匹配**：`web_fetch(https://www.ncbi.nlm.nih.gov/*)` 放行的是这个前缀下的**任何**查询串，其中也可能带着数据。
- **`--permission-mode read-only` 会拒绝两者**：它们都没有声明 `read_only`，而且搜索词发往搜索引擎，本地什么都不写，却仍然是一次对外披露（`permission/modes.py`）。只想"读加搜索"的部署应该用 `default` 模式加规则文件。
- **`auto-approve`（CLI `/auto on`）**：没有规则或危险模式介入时直接放行，出站请求不再询问。这对组学数据来说是需要想清楚的选择。
- **审计 hook**：记录调用，但工具的错误消息往往会回显 URL，所以审计文件只保留异常类名，不保留消息（`hooks/audit.py`）。
- **子代理**：`general-purpose` 继承父代理的全部工具，包括这两个。子代理里的审批请求会经 contextvars 送到父 turn 的审批通道，照常需要人工批准（见 `sub-agent.md`）。

---

## 7. 组学场景示例

**查 GEO 数据集元信息**（公开标识符，可以批准）：

```
用户：GSE123456 是什么实验？用的什么平台？

Agent:
  1. web_search({"query": "GSE123456 GEO single-cell"})
       审批卡片：send this search query to html.duckduckgo.com:
                 GSE123456 GEO single-cell
  2. web_fetch({"url": "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE123456"})
       审批卡片：send an HTTP GET to www.ncbi.nlm.nih.gov and fetch:
                 https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE123456
       → HTML 被化简成 "# … > Source: …" 的 Markdown
  3. 根据抓取到的内容回答，并注明来源 URL
```

**查文献摘要**：NCBI E-utilities 返回 `application/json`，这种类型会**原样返回**（受 `max_chars` 约束），不经过 HTML 化简：

```
web_fetch({"url": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id=12345678&retmode=json",
           "max_chars": 16000})
```

**全文 PDF 不能用 `web_fetch` 读**：`application/pdf` 会得到"不支持的内容类型"提示。需要 PDF、DOI、PubMed ID 解析时，应走 `literature` skill 的流程（参阅它的 SKILL.md）。

**不应批准的请求**：模型把用户 h5ad 里的样本条码、病人 ID、变异位点写进搜索词或 URL 查询串，例如 `web_search({"query": "patient P0231 BRCA1 c.68_69delAG"})`。闸门会放行（目标是公网地址），**唯一的拦截点是审批卡片前的人**。

---

## 8. 配置

两个工具随 `build_app` 的 `foundation_tools()` 无条件挂载，**没有 AppConfig 配置项**，也不需要环境变量或 API Key。

| 常量 | 值 | 位置 |
|---|---|---|
| `SEARCH_ENDPOINT` | `https://html.duckduckgo.com/html/` | `builtin/web_search.py` |
| `DEFAULT_RESULTS` / `MAX_RESULTS` | 5 / 10 | `builtin/web_search.py` |
| `SEARCH_TIMEOUT` | 20.0 s | `builtin/web_search.py` |
| `FETCH_TIMEOUT` | 15.0 s | `builtin/web_fetch.py` |
| `DEFAULT_MAX_CHARS` / `HARD_MAX_CHARS` | 8,000 / 32,000 字符 | `_html.py` |
| `MAX_BODY_BYTES` | 1 MiB | `_html.py` |
| `MAX_REDIRECTS` | 5 | `_websafety.py` |
| `DIAL_TIMEOUT` | 10.0 s | `_websafety.py` |
| `USER_AGENT` | `OmicsClaw/1.0` | `_websafety.py` |
| `BLOCKED_NETWORKS` | 14 段 | `_websafety.py` |

部署代码可以用 `WebFetchTool(transport=..., timeout=...)`、`WebSearchTool(transport=..., endpoint=..., timeout=...)` 自行构造，再通过 `build_app(tools=...)` 传入。`transport` 位于信任边界之内（3.6）。引擎侧每次工具调用的上限 `tool_timeout_s`（默认 600 s）远大于两个工具自己的预算，但它会把审批等待时间也算进去。

---

## 9. 已知限制

- **SSRF 闸门不能防数据外泄**，只能靠 `ASK` 审批和看卡片的人。开启 `auto-approve` 或写宽泛的 `allow` 规则，就等于放弃了这道防线。
- **没有 readability**，是固定标签表加结构保留；在推广内容多的页面上噪声更大。旧工具用 `markdownify`，能处理表格、强调、嵌套，这一层不能 import 它。
- **不执行 JavaScript**，只靠前端渲染的 SPA 页面拿不到正文。
- **只读 HTML 和文本类内容**，PDF、图片、压缩包需要用 `bash` 下载后另行处理。
- **`HARD_MAX_CHARS` 是 32,000**，旧 `web_fetch` 是 100,000。
- **`User-Agent` 是 `OmicsClaw/1.0`**：放在 WAF 后面的文档站可能对非浏览器 UA 返回 403，旧工具发送的是浏览器 UA。
- **依赖 DuckDuckGo 的页面结构**：改版后的失败形态是零结果（`_report` 会提示这种可能）。没有官方 SLA，频繁调用会触发限流。没有备用后端（Brave、Tavily 等）。
- **旧 `web_search` 的能力没有保留**：`topic` 枚举（general/news/finance），以及"抓取每条结果、直接返回整页"的行为。现在一次旧调用对应一次搜索加 N 次 `web_fetch`，每次都要审批。
- **`web_fetch` 只发 GET**，无法提交表单或调用 POST API。
- **没有和真实 HTTP 端点通信过**：所有测试都通过注入的 transport 或假 `opener` 在真实闸门下运行（`tests/tools/test_websafety.py`、`test_web_fetch.py`、`test_web_search.py`、`test_html.py`）。
- **负载敏感的不稳定测试**：`tests/tools/test_websafety.py::test_a_server_dripping_bytes_cannot_outlast_the_budget` 是已登记的负载相关 flake。失败时先单独重跑它和它所在的目录，**不要为了让它稳定而修改 `_websafety.py`**。
- 源码 docstring 里多次提到的旧 `runtime/tools/builders/engineering.py` 同名工具，已随 2026-09-20 的迁移删除，现在只有本层这一对工具。

---

## 10. 模块结构

```
omicsclaw/tools/
├── _websafety.py        SSRF 闸门 + PinnedTransport（只用标准库，不 import omicsclaw）
├── _html.py             HTML → Markdown 形态文本；DEFAULT/HARD_MAX_CHARS、MAX_BODY_BYTES
└── builtin/
    ├── web_fetch.py     WebFetchTool、render()、FETCH_SCHEMA、FETCH_TIMEOUT
    └── web_search.py    WebSearchTool、parse_results()、decode_redirect()、SEARCH_*

依赖：
web_fetch.py ─┬─→ _websafety.py（inspect_url、PinnedTransport、TransportFailed、header）
web_search.py ┘    └─ _html.py（web_fetch：extract_page / truncate_text；web_search：MAX_BODY_BYTES）
两者 ─→ tools.base（ToolPolicy）、tools.context（require_approval、report_progress）、
        tools.function_tool（decode_arguments、validate_arguments、ToolArgumentError）、schema
```

---

## 11. 文件索引

| 文件 | 职责 |
|---|---|
| `omicsclaw/tools/_websafety.py` | `inspect_url`、`check_url`、`safe_target`、`blocked_reason`、`BLOCKED_NETWORKS`、`PinnedTransport`、`TransportFailed`、`UrlRefused` 系列、`HttpResponse`、`header` |
| `omicsclaw/tools/_html.py` | `extract`、`extract_page`、`assemble_page`、`truncate_text`、`Document` |
| `omicsclaw/tools/builtin/web_fetch.py` | `WebFetchTool`、`render`、策略与描述 |
| `omicsclaw/tools/builtin/web_search.py` | `WebSearchTool`、`parse_results`、`decode_redirect`、`SearchResult` |
| `omicsclaw/entry/assembly.py` | `foundation_tools()` 挂载两个工具；`_environment_source()` 注入 `Today:` |
| `omicsclaw/permission/rules.py` | `principal_argument`：`url` / `query` 作为规则的匹配对象 |
| `omicsclaw/permission/modes.py` | `READ_ONLY` 为什么拒绝 `web_search` |
| `tests/tools/test_websafety.py` | 闸门、钉住、重定向、预算 |
| `tests/tools/test_web_fetch.py` | 审批、内容类型分支、截断、失败即输出 |
| `tests/tools/test_web_search.py` | 解析、`uddg` 解码、结果上限、零结果提示 |
| `tests/tools/test_html.py` | 提取、结构保留、截断 |

参考：`docs/plans/0029-foundation-tools.md`，`docs/FRAMEWORK-REBUILD.md` Step 4.5 与 "Named here so it stops being invisible" 一节。
