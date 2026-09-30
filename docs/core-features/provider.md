# Provider：模型适配层

## 1. 架构总览

`omicsclaw/provider/` 是引擎与各家模型 API 之间的**同声传译**：`omicsclaw.schema` 的类型进去，`omicsclaw.schema` 的类型出来，所有厂商特有的字段名都只在各自的适配器模块里出现。新增一个后端就是新增一个文件，不需要改动主循环。

OmicsClaw 的这一层是 step 2 独立交付的包（plan 0026）。

```
            AgentEngine（omicsclaw/engine）
                    │  generate(messages, tools) / generate_stream(...)
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ LLMProvider (Protocol, base.py)   Completion · ProviderError         │
│                                                                      │
│   factory.provider_from_env(provider, model, **kw)                   │
│        │ resolve_config() ── config.py: PRESETS / DETECT_ORDER / 环境 │
│        ▼                                                             │
│   ProviderConfig (frozen) ──► provider_for(config, dialect=None)     │
│                                   │ ADAPTERS[ProviderDialect]        │
│                 ┌─────────────────┴──────────────────┐               │
│                 ▼                                    ▼               │
│   OpenAIProvider (openai_provider.py)   AnthropicProvider            │
│   Chat Completions，12 个预设             (anthropic_provider.py)      │
│   encode_* / decode_* 纯函数              Messages API，1 个预设        │
│                 │                                    │               │
│                 └──── _accumulator.ToolCallAccumulators ────┘        │
│                       _model_limits.get_model_limits                 │
└──────────────────────────────────────────────────────────────────────┘
                    │ 懒加载，首次需要 socket 时才 import
                    ▼
          openai.AsyncOpenAI            anthropic.AsyncAnthropic
```

| 组件 | 代码位置 | 职责 |
|------|---------|------|
| `LLMProvider` | `omicsclaw/provider/base.py` | 引擎依赖的唯一契约（结构化 `Protocol`） |
| `Completion` | `omicsclaw/provider/base.py` | 一次非流式调用的结果：`message`、`usage`、`finish_reason` |
| `ProviderError` | `omicsclaw/provider/base.py` | 本层自己的异常类型，带 `provider` 与 `status_code` |
| `OpenAIProvider` | `omicsclaw/provider/openai_provider.py` | Chat Completions 方言适配器 |
| `AnthropicProvider` | `omicsclaw/provider/anthropic_provider.py` | Anthropic Messages 方言适配器 |
| `ToolCallAccumulators` | `omicsclaw/provider/_accumulator.py` | 流式工具调用分片重组，两个适配器共用 |
| `ModelLimits` / `get_model_limits` | `omicsclaw/provider/_model_limits.py` | 静态表：上下文窗口与输出上限 |
| `ProviderPreset` / `PRESETS` / `DETECT_ORDER` | `omicsclaw/provider/config.py` | 13 个后端预设与 API key 自动探测顺序 |
| `ProviderConfig` / `resolve_config` | `omicsclaw/provider/config.py` | 一次解析好的调用配置，以及从参数和环境变量解析它的函数 |
| `ProviderDialect` / `dialect_for` | `omicsclaw/provider/config.py` | 请求语法（适配器选择的依据） |
| `ADAPTERS` / `provider_for` / `provider_from_env` | `omicsclaw/provider/factory.py` | 唯一的装配点：配置进，适配器出 |

**分层约束**：本包只导入 `omicsclaw.schema` 和标准库。厂商 SDK 在各适配器的客户端工厂函数**内部**用普通的 `import` 语句加载，不在模块顶层导入。所以导入本包不需要安装任何 SDK，而且依赖扫描工具仍能看到这些依赖。`tests/provider/test_provider_layering.py` 检查以下几点：契约模块不导入 SDK；适配器以可见的方式声明自己的 SDK；在两个 SDK 都被屏蔽的情况下每个模块仍能导入；旧的复数包 `omicsclaw/providers/` 已不存在。

## 2. 接口：`LLMProvider`

```python
@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    async def generate(self, messages: Sequence[Message],
                       tools: Sequence[ToolDefinition] | None = None) -> Completion: ...

    def generate_stream(self, messages: Sequence[Message],
                        tools: Sequence[ToolDefinition] | None = None
                        ) -> AsyncIterator[StreamChunk]: ...   # 不是 async def

    def bind(self, **overrides: Any) -> LLMProvider: ...
```

**接口里刻意没有的东西**：`generate` 只接收对话和本 Turn 可用的工具，没有 model、temperature、`max_tokens`、thinking budget。这些都在实例的 `ProviderConfig` 上，构造时就固定了，所以引擎无处存放模型配置，也就不可能沾上它。需要按请求变化时用 `bind()`，它返回一个**新的** provider：

```python
titler = provider.bind(model="claude-haiku-4-5", max_tokens=64)
# 两个适配器的实现都是一行：
return type(self)(self._config.with_overrides(**overrides))
```

接收者本身永远不会被修改：两个 Turn 持有同一 provider 的两次 bind 结果时，互相看不到对方的设置。

| 约定 | 说明 |
|------|------|
| `tools=None` 或空序列 | **去掉全部工具**，而不是"使用默认工具集"。separated Thinking 阶段靠的就是这一点：不给工具，模型只能推理 |
| `generate_stream` 不是 `async def` | 直接返回迭代器，写作 `async for chunk in p.generate_stream(...)`，中间没有 `await` |
| 流的最后一个 chunk | `StreamChunkType.DONE`，携带组装好的 `Message`、`Usage`、`finish_reason`。消费者要读到这里，底层连接才会释放 |
| 失败 | 一律抛 `ProviderError`。两个内置适配器都**不会** yield `ERROR` chunk；这个成员留给第三方适配器，引擎遇到它会转成 `ProviderError` |

### 2.1 `Completion`

| 字段 | 类型 | 说明 |
|------|------|------|
| `message` | `Message` | assistant 消息；`message.is_action` 决定循环是否继续 |
| `usage` | `Usage` | 默认全零而不是 `None`，所以跨 Turn 累加就是普通的 `+` |
| `finish_reason` | `str` | 厂商的原始值：`stop` / `end_turn` / `tool_calls` / `tool_use` / `length` / `max_tokens`。引擎据此判断 `TRUNCATED` |

### 2.2 `ProviderError`

```python
ProviderError(message, *, provider="", status_code=None)
str(err) == "[<provider>] <message>"      # provider 非空时带前缀
```

- `status_code`：厂商报告了 HTTP 状态码就填上；没到达线路的失败（配置错误、工具参数格式错误、连接失败）为 `None`。重试策略正是靠这个区分的（见 §7）。
- 适配器捕获 SDK 抛出的任何异常，重新包装成 `ProviderError`，所以调用方永远不用写 `except openai.APIError`。

## 3. 消息转换

两个适配器都把转换写成**模块级纯函数**（例如 `encode_messages` / `decode_message`、`encode_conversation` / `decode_content`），直接操作普通 dict 或 SDK 对象。这样测试可以直接对照字面量载荷做断言，不需要客户端、socket 或 SDK。读取字段统一经过各自的 `_field(source, name)`，它同时兼容 Mapping 和 SDK 对象；OpenAI 版本还会查 pydantic 的 `model_extra` 和 `__dict__`。

### 3.1 OpenAI（Chat Completions）

| schema | OpenAI 线格式 |
|--------|--------------|
| `Role.SYSTEM` / `Role.USER` | `{"role": ..., "content": ...}` |
| `Role.ASSISTANT` | `{"role": "assistant", "content"?, "reasoning_content"?, "tool_calls"?}` |
| `ToolCall` | `{"id", "type": "function", "function": {"name", "arguments"}}`，`arguments` 按原始字符串透传 |
| `Role.TOOL` | `{"role": "tool", "tool_call_id", "content", "name"?}`。**`is_error` 没有对应字段**，这个方言的 tool 消息只有文本 |
| `ToolDefinition` | `{"type": "function", "function": {"name", "description"?, "parameters"}}`，`input_schema` 为空时补 `{"type": "object", "properties": {}}` |

- **可选键直接省略，不发空值**。普通 assistant 消息上多一个 `"tool_calls": []` 会改变前缀字节，导致整段对话的 prompt 缓存失效。
- 只要有值就回传 `reasoning_content`。DeepSeek 的 thinking 端点要求历史 assistant 消息带回推理内容（否则报 "The reasoning_content in the thinking mode must be passed back"）。
- 解码方向：`content: null` 转成 `""`；推理内容依次尝试 `reasoning_content`、`reasoning`，取第一个非空值（DeepSeek-R1 用前者，OpenRouter 代理 GPT 时用后者）；`type` 明确不是 `function` 的工具调用（例如内建搜索）会被丢弃，缺少 `type` 的接受；参数如果已经是 dict，就重新编码成紧凑 JSON（`ensure_ascii=False`，中文参数保持可读）。

### 3.2 Anthropic（Messages）

| 关注点 | schema | Anthropic |
|--------|--------|-----------|
| System prompt | `Role.SYSTEM` 消息 | 顶层 `system` 参数；多条会用 `"\n\n"` 拼接 |
| 工具调用 | `Message.tool_calls` | `tool_use` 内容块，`input` 是**对象** |
| 工具结果 | `Role.TOOL` 消息 | **user** 轮里的 `tool_result` 块，带 `is_error` |
| 推理 | `reasoning_content` | `thinking` 块 |
| 停止信号 | — | `stop_reason` |

- **连续的工具结果合并成一个 user 轮**（`encode_conversation`）。一个 Turn 并发请求了三个工具，就必须在**同一个** user 轮里回三个 `tool_result` 块，拆成多轮会被 API 拒绝。
- **出站时把参数解码成对象**（`decode_arguments`）。遇到无法解析或不是 object 的 JSON 直接抛 `ProviderError`，不会像 `ToolCall.parsed_arguments()` 那样退化成 `{}`，否则回放的历史里会出现一个模型从没发出过的调用。
- **`reasoning_content` 不会作为 `thinking` 块回放**。Anthropic 会用签发时的 `signature` 校验回传的 thinking 块，而 schema 没有地方存签名，回放必然 400。所以出站时只能丢掉，这是有损的（见 §9）。
- 入站时 `redacted_thinking` 被丢弃：它是密文，放进 `reasoning_content` 会让一个标明是 Thought 的字段装着不可读内容。
- `encode_tools` **原样透传完整 JSON Schema**（只 `setdefault` `type` 和 `properties`），`$defs`、`additionalProperties` 等都保留。

## 4. 流式累积

### 4.1 `ToolCallAccumulators`

两家都会把一个工具调用拆到多个 chunk 里：第一个 chunk 带 id 和 name，后续 chunk 带参数 JSON 的片段。

```
start(index, call_id, name)       # 允许重复调用；空值不会覆盖已有值
append_arguments(index, fragment)
finalize() -> tuple[ToolCall, ...]
    for _, acc in sorted(self._by_index.items())   # 遍历实际存在的键
        ToolCall(id, name, arguments="".join(fragments) or "{}")
```

**必须遍历实际存在的键，不能用 `range(len(self))`。** Anthropic 流里的 index 是**内容块**的位置：开启 extended thinking 或者前面有文本时，index 0 是 `thinking` / `text` 块，`tool_use` 从 1 开始。这时键集合是 `{1, 2, 3}`，按位置遍历会在 0 处找不到而提前结束，**悄悄丢掉最后一个工具调用**。累积中的状态在 `finalize()` 之前对外不可见。

### 4.2 OpenAI 流

```
payload["stream_options"] = {"include_usage": True}        # 不加就收不到 usage
async for raw in stream:
    先读 raw.usage（带用量的 chunk 的 choices 是空的）
    choices 为空 → continue
    finish_reason 非空 → 记下（通常在最后一个 delta 为空的 chunk 上）
    delta.reasoning_content / reasoning → yield REASONING_DELTA
    delta.content                       → yield TEXT_DELTA
    delta.tool_calls[]                  → 累积
finally: await _close_stream(stream)
yield DONE(Message.assistant(text, reasoning, calls.finalize()), usage, finish_reason)
```

### 4.3 Anthropic 流

| 事件 | 处理 |
|------|------|
| `message_start` | 从 `message.usage` 取输入侧用量 |
| `content_block_start`（`tool_use`） | `accumulators.start(index, id, name)` |
| `content_block_delta` / `text_delta` | yield `TEXT_DELTA` |
| `content_block_delta` / `thinking_delta` | yield `REASONING_DELTA` |
| `content_block_delta` / `input_json_delta` | `append_arguments(index, partial_json)` |
| `message_delta` | 输出侧用量；`delta.stop_reason` 即 `finish_reason` |

用量在 `message_start` 和 `message_delta` 里各报一半，所以用 `_merge_usage` 逐字段合并：新值非零才覆盖，这样先到的那一半不会被后到的零值清掉。

### 4.4 取消时释放连接

两个适配器的 `_stream` 都在 `finally` 里调用 `_close_stream`（它会吞掉关闭时的异常）。正常结束、出错、以及被取消的 Turn 在 `yield` 处抛入的 `GeneratorExit`，都会走到这里。只捕获 `Exception`，所以 `CancelledError` / `GeneratorExit` 不会被包装成 `ProviderError`。引擎这边用 `aclosing` 把关闭一路传递下来（见 [agent-loop.md](agent-loop.md) §2）。

## 5. 两个适配器的差异

| 维度 | `OpenAIProvider` | `AnthropicProvider` |
|------|------------------|---------------------|
| 覆盖的预设 | 12 个（openai、deepseek、gemini、nvidia、siliconflow、openrouter、volcengine、dashscope、moonshot、zhipu、ollama、custom） | 1 个（anthropic），也可指向任何 Anthropic 兼容端点 |
| SDK | `openai.AsyncOpenAI`，在 `_create_client` 里加载 | `anthropic.AsyncAnthropic`，在 `_load_sdk` / `_build_async_client` 里加载 |
| 空 API key | 传占位值 `"not-needed"`（Ollama 等本地端点） | 省略该参数，交给 SDK 自己解析凭据 |
| 超时对象 | `openai.Timeout(total, connect=...)` | 从 SDK 模块上取 `sdk.Timeout`；取不到时退化为浮点总超时 |
| `max_tokens` | 只在 `config.max_tokens > 0` 时发送 | **每次必发**，值为 `config.max_output_tokens`（未设置时用模型已知的输出上限） |
| temperature | 始终发送 | 与 thinking 互斥，两者只发一个 |
| thinking | 不读 `thinking_budget_tokens`；base URL 含 `openrouter` / `requesty` 时自动加 `include_reasoning: True`；其他厂商的开关放在 `extra` 里 | `encode_thinking`，见 §5.1 |
| prompt 缓存断点 | `apply_cache_breakpoints`，只对 Claude 家族生效，见 §5.2 | **没有** |
| 用量 | `prompt_tokens` 本身已包含缓存命中；缓存命中数取自 `prompt_tokens_details.cached_tokens` 或 DeepSeek 的 `prompt_cache_hit_tokens`；`cache_write_tokens` 恒为 0 | `input_tokens` 不含缓存读取，会把 `cache_read_input_tokens` **加回去**；`cache_creation_input_tokens` 记入 `cache_write_tokens` |
| 错误包装 | `"{what}: {ExcType}: {exc}"`，带 `status_code` | `"Anthropic Messages request failed: {exc}"`；已经是 `ProviderError` 的原样返回 |
| 请求在何处构造 | `_stream` 内部（第一次 `__anext__` 时） | `generate_stream` 调用时就构造，历史里的坏参数会在调用处立刻报错 |
| `extra` | 最后 `update` 进请求体，优先级最高 | 同样最后合并；如果 `extra` 开启了 thinking 且没给 temperature，会撤掉适配器自己设置的 temperature |

### 5.1 Anthropic 的 extended thinking

`encode_thinking(model, budget, max_tokens)` 先用 `thinking_support_for_model` 判断模型属于哪一代（名字经过 `bare_model_name` 处理并把 `.` 换成 `-`，所以 `anthropic/claude-opus-4.7` 和 `claude-opus-4-7` 会得到相同结论）：

| `ThinkingSupport` | 匹配（子串） | 发送内容 |
|-------------------|------------|---------|
| `ADAPTIVE_ONLY` | `fable-5`、`opus-5`、`opus-4-8`、`opus-4-7`、`sonnet-5` | `{"thinking": {"type": "adaptive"}, "output_config": {"effort": ...}}` |
| `ADAPTIVE_PREFERRED` | `opus-4-6`、`sonnet-4-6` | 同上（`budget_tokens` 在后续模型上已被移除，默认模型如果固定用旧形态，就埋下了一个迟早出现的 400） |
| `BUDGET_ONLY` | 其他（包括未知名字） | `{"thinking": {"type": "enabled", "budget_tokens": clamp_thinking_budget(...)}}` |

- `budget <= 0` 时什么都不发，走 temperature。
- `effort_for_budget`：`< 4096` → `low`，`< 16384` → `medium`，`< 32768` → `high`，`< 65536` → `xhigh`，其余 → `max`。这个阶梯是**本适配器自己的约定**，不是厂商公布的对应关系，它只保证单调：要更多预算就得到更深的思考。
- `clamp_thinking_budget`：最低 `MIN_THINKING_BUDGET_TOKENS = 1024`，最高 `max_tokens - 1`；`max_tokens <= 1024` 时无法满足，直接抛 `ProviderError`，不会悄悄关掉 thinking。

### 5.2 prompt 缓存断点（ADR 0024）

OmicsClaw 设计了一段字节稳定的 system + tools 前缀。OpenAI、DeepSeek 会自动缓存它，Anthropic 却必须有显式断点才缓存。`apply_cache_breakpoints` 在满足全部以下条件时，给**最后一条 system 消息**和**最后一个工具**加上 `cache_control: {"type": "ephemeral"}`：

- `is_anthropic_family(provider, model)`：provider 是 `anthropic`，或模型名包含 `claude`，或以 `anthropic/` 开头；
- base URL 不含 `localhost` / `127.0.0.1`（本地代理会拒绝块形态的 content）；
- `breakpoints_enabled()`：`OMICSCLAW_PROMPT_CACHE_BREAKPOINTS` 不为 `"0"`。

实际上这只在"经 OpenAI 兼容网关访问的 Claude"（例如 OpenRouter 默认的 `anthropic/claude-sonnet-4.6`）上生效。原生 Anthropic 走的是另一个适配器，**没有**这一步（见 §9）。

## 6. 配置

### 6.1 预设（`PRESETS`）

| name | tier | dialect | 默认 base_url | 默认模型 | key 变量 |
|------|------|---------|--------------|---------|---------|
| `deepseek` | primary | openai_chat | `https://api.deepseek.com` | `deepseek-v4-flash` | `DEEPSEEK_API_KEY` |
| `openai` | primary | openai_chat | （SDK 默认） | `gpt-5.5` | `OPENAI_API_KEY` |
| `anthropic` | primary | **anthropic_messages** | `https://api.anthropic.com/v1/` | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `gemini` | primary | openai_chat | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-3-flash-preview` | `GOOGLE_API_KEY` |
| `nvidia` | primary | openai_chat | `https://integrate.api.nvidia.com/v1` | `nvidia/nemotron-3-super-120b-a12b` | `NVIDIA_API_KEY` |
| `siliconflow` | aggregator | openai_chat | `https://api.siliconflow.cn/v1` | `Pro/zai-org/GLM-5` | `SILICONFLOW_API_KEY` |
| `openrouter` | aggregator | openai_chat | `https://openrouter.ai/api/v1` | `anthropic/claude-sonnet-4.6` | `OPENROUTER_API_KEY` |
| `volcengine` | aggregator | openai_chat | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-2-0-pro-260215` | `VOLCENGINE_API_KEY` |
| `dashscope` | aggregator | openai_chat | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.6-plus` | `DASHSCOPE_API_KEY` |
| `moonshot` | aggregator | openai_chat | `https://api.moonshot.cn/v1` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| `zhipu` | aggregator | openai_chat | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.1` | `ZHIPU_API_KEY` |
| `ollama` | local | openai_chat | `http://localhost:11434/v1` | `qwen2.5:7b` | （无） |
| `custom` | local | openai_chat | （无） | （无） | （无） |

**方言跟随端点，而不是模型名**：OpenRouter 的默认模型虽然是 `anthropic/claude-sonnet-4.6`，走的仍然是 Chat Completions。`dialect` 字段放在预设上，而不是在工厂旁边另建一张表：如果另建一张表，新增预设时忘了在表里加一行，也不会报错，而是悄悄落到多数派适配器上。

`DETECT_ORDER`（自动探测顺序）：`deepseek → openai → anthropic → gemini → nvidia → siliconflow → openrouter → volcengine → dashscope → moonshot → zhipu`。`ollama` 和 `custom` 没有 key 可探测，所以不在其中。

### 6.2 `resolve_config` 的解析优先级

```
resolve_config(provider="", model="", *, base_url="", api_key="", env=None, **overrides)
```

1. 显式参数；
2. 针对该 provider 的环境变量 `<PROVIDER>_BASE_URL`（例如 `DEEPSEEK_BASE_URL`）；
3. 根据 provider 专属 API key 自动探测（`detect_provider_from_env`：`LLM_PROVIDER` 最优先，否则按 `DETECT_ORDER` 找第一个已设置的 key 变量）；
4. 通用变量 `LLM_*` / `OMICSCLAW_*`；
5. 预设默认值；模型的最后兜底是 `FALLBACK_MODEL = "deepseek-v4-flash"`。

**通用变量只在"它们大概率描述的就是当前后端"时才生效**：环境变量 `LLM_PROVIDER` / `OMICSCLAW_PROVIDER` 指定的正是这个 provider；或者什么都没请求；或者请求的是 `custom` 且环境没指定 provider。否则，为上一个厂商留下的 `LLM_BASE_URL` 会悄悄劫持对另一个厂商的显式请求。API key 的顺序是：预设自己的 key 变量 → `LLM_API_KEY` / `OMICSCLAW_API_KEY`（仅在通用变量生效时）→ provider 为空或 `openai` 时再退到 `OPENAI_API_KEY`。

`normalize_model_for_provider` 修复最常见的配置错误：切换了 `LLM_PROVIDER` 却没改模型名。只有当模型名**恰好**是另一个预设的默认模型，或者是已退役模型（`deepseek-chat`、`deepseek-reasoner`）时才改写。以下情况不改写：`custom`、`ollama`、`openrouter`、`siliconflow`、`nvidia`（模型标识开放，不宜改写），以及显式给了 base URL 的情况。

### 6.3 环境变量

| 变量 | 读取方 | 说明 |
|------|-------|------|
| `LLM_PROVIDER` / `OMICSCLAW_PROVIDER` | `resolve_config`、`detect_provider_from_env` | 指定预设；为空时按 key 探测 |
| `LLM_API_KEY` / `OMICSCLAW_API_KEY` | `resolve_config` | 通用 key，前者优先 |
| `<VENDOR>_API_KEY` | `resolve_config` | 见 §6.1 表；优先于通用 key |
| `LLM_BASE_URL` / `OMICSCLAW_BASE_URL` | `resolve_config` | 通用端点，前者优先 |
| `<PROVIDER>_BASE_URL` | `resolve_config` | 针对单个 provider 的端点，优先于通用端点 |
| `OMICSCLAW_MODEL` / `LLM_MODEL` / `SPATIALCLAW_MODEL` | `resolve_config` | 通用模型名，按此顺序 |
| `OMICSCLAW_LLM_TIMEOUT_SECONDS` / `LLM_REQUEST_TIMEOUT_SECS` | `resolve_config` | 单次调用总超时，默认 `120.0` |
| `OMICSCLAW_LLM_CONNECT_TIMEOUT_SECONDS` | `resolve_config` | 连接超时，默认 `10.0` |
| `OMICSCLAW_LLM_MAX_RETRIES` / `LLM_MAX_RETRIES` | `resolve_config` | 传给 SDK 的重试次数，默认 `5`；`0` 表示禁用 |
| `OMICSCLAW_PROMPT_CACHE_BREAKPOINTS` | `breakpoints_enabled` | 设为 `0` 关闭 §5.2 的断点 |

超时和重试这几个数值变量如果无法解析，或者超出合法范围（超时须 > 0，重试须 ≥ 0），会**静默回退到默认值**。配置模块不能依赖日志系统的初始化，所以不打日志。这与 `omicsclaw/entry/config.py` 的做法不同：后者遇到坏值会抛 `AppConfigError`。

`.env` 不由本层读取。`omicsclaw.launch._adopt_dotenv` 在进程启动时把 `.env` 叠加到进程环境上，且**不覆盖**已经导出的变量。`provider_from_env` 直接读取进程环境，这是 plan 0031 Q8 唯一声明过的例外：密钥不经过 `AppConfig`，免得多出一个可能把它打印出来的地方。

### 6.4 `ProviderConfig`

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `provider` | （必填） | 预设 key；为空表示什么都没解析出来 |
| `model` | （必填） | |
| `base_url` | `""` | 空表示使用 SDK 默认端点 |
| `api_key` | `""` | 约定不写进日志 |
| `max_tokens` | `0` | `0` 表示未设置，由 `max_output_tokens` 取模型的已知上限 |
| `temperature` | `0.3` | `DEFAULT_TEMPERATURE` |
| `thinking_budget_tokens` | `0` | `0` 表示关闭；只记录请求值，合法化由适配器负责 |
| `timeout_seconds` | `120.0` | 交互式 surface 不应在挂起的连接上等太久 |
| `connect_timeout_seconds` | `10.0` | |
| `max_retries` | `5` | SDK 层重试 429/5xx，仅限首字节之前 |
| `extra` | `{}`（只读） | 厂商特有、没有中立含义的开关，最后合并进请求且优先级最高 |

派生属性 `limits` 返回 `get_model_limits(model)`，`max_output_tokens` 返回 `max_tokens` 或 `limits.output_tokens`。`with_overrides` 遇到未知字段时抛 `ProviderError`（`EngineConfig` 在同样情况下抛的是 `TypeError`）。

### 6.5 模型上限表（`_model_limits.py`）

- 先按完整标识精确匹配，再去掉最后一个 `/` 之前的网关前缀后匹配（`bare_model_name`，统一小写）。
- 查不到时返回 `DEFAULT_MODEL_LIMITS = ModelLimits(256_000, 8_192)`。宁可保守，也不返回 0。
- 上下文窗口以仓库原有的模型目录为准（例如 `claude-opus-4-7` 为 1M）；输出上限只对有明确数据的模型采用，其余用 8192，**表示"未知"，不是"已知为 8192"**。
- 下游使用者：`ProviderConfig.max_output_tokens`（Anthropic 每次请求都要带），以及 `entry.assembly.build_budget` 为上下文预算读取的窗口大小。

## 7. 重试与错误分类

重试分两层，各管一段：

| 层 | 在哪里 | 处理什么 | 预算 |
|----|--------|---------|------|
| SDK | `ProviderConfig.max_retries` 传给 `AsyncOpenAI` / `AsyncAnthropic` | 首字节之前的 429 / 5xx，遵守 `Retry-After` | 默认 5 |
| 引擎 | `omicsclaw/engine/retry.py` 的 `generate_with_retry` | 流中途断开、5xx、连接失败、流没有 `DONE` 就结束 | `generate_retries=3` / `network_retries=6` |

引擎层根据 `ProviderError.status_code` 分类：429 或 ≥500 → 一般预算；其他 4xx → 不重试；`None` → 消息文本命中 `_TRANSPORT_MARKERS`（例如 `connection error`，对应 SDK 把连接拒绝、DNS、TLS 失败统一成的 `APIConnectionError: Connection error.`；以及 `OpenAIProvider._wrap` 加在前面的类名 `apiconnectionerror`）时用宽预算，否则用一般预算。详见 [agent-loop.md](agent-loop.md) §6。

适配器还会**自己**抛出几种 `ProviderError`：SDK 未安装；OpenAI 返回的响应没有 `choices`；Anthropic 历史里的工具参数无法解析；thinking 预算无法满足；`with_overrides` 收到未知字段；`provider_for` 找不到对应方言的适配器。这些都没有 `status_code`。

## 8. 工厂与装配

```python
ADAPTERS = MappingProxyType({
    ProviderDialect.OPENAI_CHAT: OpenAIProvider,
    ProviderDialect.ANTHROPIC_MESSAGES: AnthropicProvider,
})

provider_for(config, *, dialect=None)          # 默认 dialect_for(config.provider)
provider_from_env(provider="", model="", **kw) # = provider_for(resolve_config(provider, model, **kw))
```

- `dialect_for` 遇到未知名字（包括空字符串）时返回 `OPENAI_CHAT`，而不是报错。只有在代码里直接调用 `provider_for(config, dialect=ProviderDialect.ANTHROPIC_MESSAGES)`，才能让 `custom` 指向 Anthropic 兼容端点。
- `provider_for` 不构造客户端，也不导入 SDK。客户端在首次调用时创建并缓存在实例上（`OpenAIProvider._client`、`AnthropicProvider._cached_client`）。测试可以替换这个属性，在没有 SDK、不开 socket 的情况下走完整条请求路径。
- 新增第三种后端需要：新写一个适配器模块、加一个 `ProviderDialect` 成员、在 `ADAPTERS` 里加一行。`factory.py` 里的分支逻辑不用改。

**部署时的使用方式**（`omicsclaw/entry/assembly.py` 的 `build_app`）：

```python
model = resolve_config(config.provider, config.model).model     # 预算按实际调用的模型计算
provider = observing.trace_provider(
    provider_from_env(config.provider, config.model), model=model
)
summarizer = build_summarizer(provider, config)   # summary_model 非空时 provider.bind(model=...)
engine = AgentEngine(provider, registry, config.engine_config(), prompt=app_prompt)
```

- `config.provider` / `config.model` 来自 `AppConfig`，取值依次为 `--provider` / `OMICSCLAW_PROVIDER` / `LLM_PROVIDER` 和 `--model` / `OMICSCLAW_MODEL` / `LLM_MODEL`。它们以**显式参数**的身份传给 `provider_from_env`。
- `Telemetry.trace_provider` 在 `OTEL_ENABLED=true` 时用 `omicsclaw/observability/provider.py` 的 `TracedProvider` 包一层，未启用时原样返回。
- 子 agent 定义里指定了模型时，`omicsclaw/entry/subagent.py` 用 `self._provider.bind(model=definition.model)` 得到自己的 provider。

## 9. 已知限制

| 限制 | 现状 |
|------|------|
| Anthropic thinking 签名 | `Message` 存不了 thinking 块的 `signature`，Thought 在历史里可读，但**无法回放**给产生它的模型，适配器出站时只能丢掉。修复需要改 schema（ADR 0077） |
| 原生 Anthropic 没有 `cache_control` | 断点只在 OpenAI 适配器里实现。原生 Anthropic 恰恰是不加显式断点就**完全不缓存**的后端，受影响最大 |
| 从未连过真实端点 | 客户端构造的测试用的是按适配器形状伪造的 SDK 模块，验证的是连接逻辑而不是厂商兼容性。step 3 的评估已经证明这种代价是真实的：重试分类器最初按 Python SDK 不会产生的错误文本编写，一个真实错误也匹配不上，它的测试却都通过了，因为测试里的字符串也是编的 |
| SDK 依赖声明不完整 | `environment.yml` 只声明了 `openai>=1.0.0`；`anthropic` 在任何清单里都没有声明（`pyproject.toml` 里只有 `langchain-anthropic`，靠它间接引入）。在 `rapids_singlecell` 测试环境里两个 SDK 都没装，调用时会得到"SDK 未安装"的 `ProviderError` |
| 输出上限大多未知 | 表中很多条目的 8192 表示"未知"。需要更大输出时要显式设置 `max_tokens` |
| 阻塞路径无法表达"用量未报告" | `Completion.usage` 不可为 None，引擎只能拿到零值 |
| OpenAI 方言没有 `is_error` | tool 消息只有文本，失败只能靠文本本身表达 |
| `thinking_budget_tokens` 没有部署入口 | `AppConfig` 和 entry 层都不设置它；OpenAI 适配器也不读它。要开启只能在代码里 `bind(thinking_budget_tokens=...)`，或者通过 `extra` 传厂商参数 |
| 新 Claude 模型需要手动登记 | 未知名字按 `BUDGET_ONLY` 处理。新一代只接受 adaptive 的模型必须加进 `_ADAPTIVE_ONLY_MARKERS`，否则会 400 |
| Anthropic 兼容的 `custom` 端点无法通过环境变量配置 | `provider_from_env` 没有 `dialect` 参数，`custom` 一定走 OpenAI 适配器 |
| 只有 `LLM_API_KEY` 时的默认值 | provider 解析为 `""`，模型为 `deepseek-v4-flash`，base URL 为空（即 OpenAI SDK 的默认端点）。这时必须同时设置 `LLM_PROVIDER` 或 `LLM_BASE_URL` |
| 确定性错误也会被重试 | 例如 Anthropic 历史里的工具参数无法解析，抛出的 `ProviderError` 没有 `status_code`，引擎会用一般预算重试，而结果必然相同 |
| docstring 过时 | `config.py`、`_model_limits.py`、`openai_provider.py`、`anthropic_provider.py`、`__init__.py` 里仍把 `omicsclaw/providers/`（复数）描述为"仍然在用"。该包已被删除（`test_the_plural_package_is_gone`），plan 0026 §10 的收尾任务中 `ccproxy.py` 适配器**没有**移植 |

## 10. 文件索引

| 文件 | 内容 |
|------|------|
| `omicsclaw/provider/__init__.py` | 公开面：契约、两个适配器、配置、工厂、模型上限 |
| `omicsclaw/provider/base.py` | `LLMProvider`、`Completion`、`ProviderError` |
| `omicsclaw/provider/openai_provider.py` | `OpenAIProvider`；`encode_*` / `decode_*`；`apply_cache_breakpoints`、`breakpoints_enabled`、`wants_include_reasoning`、`is_anthropic_family` |
| `omicsclaw/provider/anthropic_provider.py` | `AnthropicProvider`；`encode_conversation`、`encode_tools`、`decode_content`、`decode_usage`、`decode_arguments`；`ThinkingSupport`、`thinking_support_for_model`、`encode_thinking`、`clamp_thinking_budget`、`effort_for_budget` |
| `omicsclaw/provider/_accumulator.py` | `ToolCallAccumulators` |
| `omicsclaw/provider/_model_limits.py` | `ModelLimits`、`DEFAULT_MODEL_LIMITS`、`KNOWN_MODEL_LIMITS`、`bare_model_name`、`get_model_limits` |
| `omicsclaw/provider/config.py` | `ProviderTier`、`ProviderDialect`、`ProviderPreset`、`PRESETS`、`DETECT_ORDER`、`ProviderConfig`、`resolve_config`、`detect_provider_from_env`、`normalize_model_for_provider`、`dialect_for`、`preset_for` |
| `omicsclaw/provider/factory.py` | `ADAPTERS`、`provider_for`、`provider_from_env` |
| `omicsclaw/engine/retry.py` | 引擎层的重试与错误分类 |
| `omicsclaw/entry/assembly.py` | `build_app`、`build_summarizer`：部署时如何使用 provider |
| `omicsclaw/observability/provider.py` | `TracedProvider` |
| `tests/provider/` | 契约、转换、流式、配置、工厂、分层测试 |
| `docs/plans/0026-provider-layer-simultaneous-interpreter.md` | 计划、§5 九个陷阱、§11 交付结果与遗留项 |
| `docs/FRAMEWORK-REBUILD.md` | Step 2 小节、"Debts carried forward" 表 |
| `.env.example` | 第 1 节：LLM provider 变量 |
