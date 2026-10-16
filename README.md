<p align="center"><img src="logo.png" width="96" alt="Keenable"></p>

# Keenable 联网搜索 · Keenable Web Search for AstrBot

[中文](#中文) · [English](#english)

## 中文

为 AstrBot 提供联网搜索和网页读取。**无需注册、无需 API Key**，安装即用。

由 [Keenable](https://keenable.ai)（面向 AI Agent 的搜索引擎）官方维护。

### 功能

| 名称 | 类型 | 说明 |
|---|---|---|
| `keenable_web_search` | LLM Tool | 搜索网页，返回标题、链接和页面正文摘录，多数问题凭摘录即可回答。支持 `site`（限定域名）和 `published_after`（只看某日期之后发布的页面，适合新闻）。 |
| `keenable_fetch_page` | LLM Tool | 读取指定 URL，返回 Markdown 格式的正文。可在设置中关闭。 |
| `/keenable <关键词>` | 指令 | 直接在聊天中搜索，返回前 5 条结果。 |

### 安装

在 AstrBot WebUI 的插件市场中搜索 “Keenable” 安装，或在“从链接安装”中填写：

```
https://github.com/keenableai/astrbot_plugin_keenable
```

需要 AstrBot ≥ 4.9.2。

### 配置

全部可选，默认即可使用：

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `api_key` | 空 | 留空使用免费的无 Key 通道（按 IP 限流：每小时 1000 次，每秒 10 次）。在 [keenable.ai/console](https://keenable.ai/console) 免费获取 Key 可提高额度。 |
| `max_results` | 8 | 默认结果数（1-50），模型可在调用时指定。 |
| `snippet_max_length` | 500 | 每条结果的正文摘录长度。 |
| `enable_fetch` | 开 | 是否提供网页读取工具，修改后重载插件。 |
| `fetch_max_chars` | 20000 | 网页读取返回的最大字符数。 |
| `timeout_seconds` | 30 | 请求超时。 |

本插件与 AstrBot 自带的网页搜索互不影响。如果只想让模型使用 Keenable，可在配置的“网页搜索”部分关闭“启用网页搜索”。

请求会发送到 `api.keenable.ai`，并携带 `X-Keenable-Title: astrbot-plugin` 请求头以标识来源。支持 `HTTP(S)_PROXY` 代理环境变量。

## English

Web search and page reading for AstrBot. **No signup and no API key needed**; it works as soon as it is installed.

Maintained by [Keenable](https://keenable.ai), the company behind the search API.

### What it adds

| Name | Kind | What it does |
|---|---|---|
| `keenable_web_search` | LLM tool | Searches the web and returns titles, URLs and an excerpt of each page's text, enough to answer most questions without a second call. Supports `site` (one domain) and `published_after` (pages published on or after a date, for news). |
| `keenable_fetch_page` | LLM tool | Reads a URL and returns its main content as Markdown. Can be turned off in the settings. |
| `/keenable <query>` | Command | Searches from the chat and replies with the top 5 results. |

### Install

Search for "Keenable" in the plugin market of the AstrBot WebUI, or use "Install from URL" with:

```
https://github.com/keenableai/astrbot_plugin_keenable
```

Requires AstrBot 4.9.2 or newer.

### Settings

All optional; the defaults work:

| Setting | Default | Notes |
|---|---|---|
| `api_key` | empty | Empty uses the free keyless tier (rate-limited per IP: 1,000 requests an hour, 10 a second). A free key from [keenable.ai/console](https://keenable.ai/console) raises the limit. |
| `max_results` | 8 | Default number of results (1-50); the model can ask for another number per call. |
| `snippet_max_length` | 500 | Page-text excerpt per result, in characters. |
| `enable_fetch` | on | Whether to offer the page-reading tool; reload the plugin after changing it. |
| `fetch_max_chars` | 20000 | Maximum characters returned by page reading. |
| `timeout_seconds` | 30 | Request timeout. |

The plugin works alongside AstrBot's built-in web search. To have the model use only Keenable, turn off "Enable Web Search" in the Web Search section of the config.

Requests go to `api.keenable.ai` with an `X-Keenable-Title: astrbot-plugin` header that identifies the source. `HTTP(S)_PROXY` is honoured.

### Development

```bash
# from an AstrBot checkout with its environment installed (uv sync)
.venv/bin/pytest /path/to/astrbot_plugin_keenable
```

The client tests run against a local stand-in server; the plugin tests import AstrBot and are skipped without it. The way the fetch tool is taken out of the registry when disabled follows [astrbot_plugin_kimi_web_search](https://github.com/Tsukumi233/astrbot_plugin_kimi_web_search).

## License

MIT
