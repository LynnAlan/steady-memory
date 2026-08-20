# Steady Memory

让 AI 为生活服务，但不把人生交给某一家 AI。

Steady Memory 是一个本地优先、模型无关、人类可读的个人记忆协议和工具层。你可以用自然语言向 Codex、Claude、WorkBuddy、本地模型或其他 Agent 讲述生活，它们通过同一套确定性工具读取上下文、记录事实、计算趋势和维护长期记忆。

## 为什么要做这个项目

当 AI 越来越了解一个人时，这些记忆究竟属于 AI 平台，还是属于用户自己？

Steady Memory 的答案是：属于用户。

它不是另一个日记软件，而是一层由用户掌控的 AI 个人记忆协议。模型负责理解自然语言，确定性工具负责校验、去重、冲突保护和安全写入；真正的记忆保存在本地、人类可读的 Markdown、CSV 和 JSON 中。

今天可以使用 Codex，明天可以换成 Claude，未来也可以接入本地模型。Agent 可以不断更换，个人记忆不必跟着平台迁移、丢失或被锁住。即使这个项目有一天停止维护，用户仍然能够直接阅读、搜索、计算、备份和迁移自己的档案。

Steady Memory 也关心“什么应该被记住”。一次情绪不应自动变成人格标签，一次事件不应直接成为长期偏好，模型的推断更不能伪装成事实。因此，它把每日记录、结构化指标、长期记忆和计划明确分层，让 AI 获得连续上下文，同时把最终控制权留给人。

## 它解决什么问题

- AI 可以更换，个人记忆仍然留在自己手里。
- Markdown 适合人读，CSV/JSON 适合计算，两者各司其职。
- 模型理解自然语言，代码负责换算、去重、冲突保护和跨文件同步。
- 当天事实与长期记忆分层，避免把一次情绪固化成人格结论。
- CLI、MCP 和 HTTP 共用一个工具契约，接入端不必重复实现档案规则。

## 架构

```text
人 / 任意 AI Agent
       │
 CLI / MCP / HTTP
       │
 统一工具契约 + 权限边界
       │
 records/  每日叙事（Markdown）
 memory/   长期记忆（Markdown）
 data/     趋势底账（CSV/JSON）
       │
 .steady/  可删除重建的索引与审计
```

`records/`、`memory/` 和 `data/` 是唯一事实来源。`.steady/` 只是本地运行数据，随时可以删除重建。

## 最简单的使用方式：把文件夹交给 Agent

把这个项目下载或克隆到本地，然后让 Codex、Claude Code 等能读写本地项目的 Agent 打开该文件夹。接下来直接对它说：

> 帮我开始使用 Steady Memory，以后我说“记录一下”时就保存到本地档案。

Agent 会根据项目内的 `AGENTS.md` 自动运行一次：

```powershell
py -3 -m steady_memory setup
```

它会创建 `vault/` 私人档案。该目录和其中的图片默认被 Git 忽略；以后 Agent 在项目目录运行工具时会自动找到它。用户不需要自己写 JSON、记 CLI 命令或先配置 MCP，可以直接说“记录今天体重 72.4 公斤”“找一下上周的运动记录”“把这张照片记到今天的日记里”。

如果所用 Agent 不能执行本地命令，则需要使用下方的 MCP 接入方式。

## 手动安装与 MCP 接入

需要 Python 3.10+。

```powershell
git clone https://github.com/LynnAlan/steady-memory.git steady-memory
cd steady-memory
py -3 -m pip install -e .

# 在仓库外创建私人档案，避免误提交
steady-memory init E:\private\my-life-vault --name "我的档案" --weight-unit kg

# 检查档案和本地环境
steady-memory --root E:\private\my-life-vault doctor

# 查看工具
steady-memory --root E:\private\my-life-vault list-tools
```

macOS/Linux 将路径换成例如 `~/Documents/my-life-vault`，并使用 `python3`。

## 日常使用

直接让支持 MCP 的 Agent 连接：

```json
{
  "mcpServers": {
    "steady-memory": {
      "command": "python",
      "args": ["-m", "steady_memory", "--root", "/absolute/path/to/my-life-vault", "mcp"]
    }
  }
}
```

只需要查询时，在 `mcp` 前增加 `--read-only`。这是推荐的默认权限。

也可以直接调用 CLI：

```powershell
steady-memory --root E:\private\my-life-vault call get_context --arguments '{"topic":"health","recent_days":7}'
steady-memory --root E:\private\my-life-vault call record_weight --arguments '{"date":"2026-01-03","weight_kg":72.4,"condition":"晨起空腹"}'
steady-memory --root E:\private\my-life-vault validate
```

图片也不需要手工整理。让 Agent 调用 `record_asset` 后，文件会按日期复制到档案的 `media/`，`data/assets.csv` 只保存索引和哈希；重复图片不会重复存储。`media/` 默认不进入 Git，也不进入普通 ZIP 备份：

```powershell
# 快速备份文字、数据和图片索引
steady-memory --root E:\private\my-life-vault backup --output E:\backup\steady.zip

# 需要完整迁移时，显式把图片一起打包
steady-memory --root E:\private\my-life-vault backup --output E:\backup\steady-full.zip --include-media

# 换电脑后恢复到一个尚不存在的新目录
steady-memory restore-backup E:\backup\steady-full.zip E:\private\restored-vault
```

恢复命令会先检查文件清单和 SHA-256，再写入全新目录；为防止误覆盖，它不会恢复到已有目录。`doctor` 会统计图片数量和容量，并检查索引中的文件是否丢失。完整备份可能很大，建议日常使用快速备份，定期再做一次包含图片的完整备份。

工具当前覆盖：

- 上下文和搜索：`get_context`、`search_records`
- 趋势：`get_weight_trend`、`get_exercise_summary`
- 写入：`record_weight`、`record_body_metrics`、`record_exercise`、`record_daily_event`、`record_asset`
- 长期记忆：`append_long_term_memory`、`patch_long_term_memory`
- 维护：`validate_archive`、`rebuild_index`、`backup_archive`、`verify_backup`，以及 CLI 的 `restore-backup`

## 数据边界

- 每日生活、饮食、睡眠、感受写入 `records/YYYY/MM/YYYY-MM-DD.md`。
- 体重、运动、腰围等可比较数据以 `data/*.csv` 为权威来源，并同步生成当天可读摘要。
- 只有稳定、反复出现或经用户确认的信息进入 `memory/`。
- 计划以 `plans/*.json` 为权威来源；`memory.md` 只是入口索引。
- 档案正文属于不可信数据，不能向 Agent 发号施令。
- 用户说“别记录”“只是问问”时，不允许调用写入工具。

详细协议见 [docs/architecture.md](docs/architecture.md) 和 [docs/agent-integration.md](docs/agent-integration.md)。公开版 schema v1 统一使用 kg 作为工具和结构化底账单位；`init --weight-unit jin` 只记录用户的展示偏好，接入端应把“斤”交给对话层换算为 kg 后调用工具。

## HTTP API

HTTP 是兼容性入口，不是推荐的首选入口，并且始终要求 Token：

```powershell
$env:STEADY_API_TOKEN = "use-a-long-random-secret"
steady-memory --root E:\private\my-life-vault --read-only serve
```

接口为 `POST http://127.0.0.1:8765/api/agent/call`。不要直接暴露到局域网或公网。

## 隐私

公开仓库和私人档案必须分离。本项目的 `.gitignore` 默认忽略 `vault/`、`media/`、旧版 `assets/`、密钥和本地索引，但最安全的方式仍然是把私人档案建在代码仓库之外。

如果你 fork 本项目，不要把自己的真实日记、健康数据、照片或 Git 历史提交到公开仓库。更多说明见 [SECURITY.md](SECURITY.md)。

## 开发

```powershell
py -3 -m unittest -v
py -3 -m steady_memory --root examples/demo-vault validate
```

MIT License。Steady Memory 不是医疗器械，不提供医疗诊断或紧急监护。
