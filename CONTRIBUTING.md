# 参与贡献

感谢你帮助改进 Steady Memory。这个项目会接触高度敏感的个人档案，因此隐私、兼容性和可恢复性优先于功能数量。

## 提交 Issue

- Bug 报告只使用最小合成数据，不上传真实档案、照片、健康信息、姓名、地址、凭据或 `.steady/` 内容。
- 安全和隐私漏洞按照 `SECURITY.md` 使用 GitHub Security Advisory 私密报告，不创建公开 Issue。
- 功能建议先描述用户问题，并说明对 schema、工具契约、备份和图片存储的可能影响。

## 开发与 PR

1. 从 `main` 创建单一目的的短分支，保持改动范围小且可审查。
2. 行为发生变化时增加或更新测试，测试数据必须完全合成。
3. 保持 Markdown、CSV 和 JSON 为权威数据；`.steady/` 索引始终可删除重建。
4. 不兼容的 schema、CSV 字段、MCP 工具或备份格式变更必须先在 Issue 中讨论，并提供版本升级和迁移方案。
5. 不随意增加运行时依赖；确有必要时，在 PR 中说明收益、体积、安全和维护成本。

提交前运行：

```powershell
python -m unittest -v
python -m steady_memory --root examples/demo-vault validate
python -m compileall -q steady_memory
```

提交信息使用 Conventional Commits，例如 `fix: 修复备份校验错误`、`feat: 增加批量图片导入`、`docs: 补充 Agent 接入说明`。
