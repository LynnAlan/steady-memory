# Steady Memory

让 AI 为生活服务，但不把人生交给某一家 AI。

Steady Memory 是一个本地优先、模型无关、人类可读的个人记忆协议和工具层。你可以用自然语言向 Codex、Claude、Cursor、本地模型或其他 Agent 讲述生活，它们通过同一套确定性工具读取上下文、记录事实、计算趋势和维护长期记忆。

项目源自一个持续使用的减脂与日常树洞实践，但公开仓库只包含通用代码、空白模板和完全虚构的示例数据。

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

## 五分钟开始

需要 Python 3.10+。

```powershell
git clone <your-repository-url> steady-memory
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

工具当前覆盖：

- 上下文和搜索：`get_context`、`search_records`
- 趋势：`get_weight_trend`、`get_exercise_summary`
- 写入：`record_weight`、`record_body_metrics`、`record_exercise`、`record_daily_event`、`record_asset`
- 长期记忆：`append_long_term_memory`、`patch_long_term_memory`
- 维护：`validate_archive`、`rebuild_index`、`backup_archive`、`verify_backup`

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

公开仓库和私人档案必须分离。本项目的 `.gitignore` 默认忽略 `vault/`、`media/`、密钥和本地索引，但最安全的方式仍然是把私人档案建在代码仓库之外。

如果你 fork 本项目，不要把自己的真实日记、健康数据、照片或 Git 历史提交到公开仓库。更多说明见 [SECURITY.md](SECURITY.md)。

## 开发

```powershell
py -3 -m unittest -v
py -3 -m steady_memory --root examples/demo-vault validate
```

MIT License。Steady Memory 不是医疗器械，不提供医疗诊断或紧急监护。
