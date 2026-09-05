# 小说创作工作台计划

本仓库已初始化 OpenSpec 1.12.0，接入 Claude Code 和 Codex。规划正文使用中文，结构标题保留 OpenSpec 格式。

当前变更：`author-workbench`。状态：计划已编制，业务功能尚未实施；任务框仅在完成对应验证后勾选。

## 阅读顺序

1. [提案](changes/author-workbench/proposal.md)：目标、范围和四项能力。
2. [设计与分期](changes/author-workbench/design.md)：技术决定、P0–P3 门槛、迁移和验证。
3. [任务清单](changes/author-workbench/tasks.md)：可逐项跟踪的实施和验收任务。
4. [需求规格](changes/author-workbench/specs/)：每项能力的行为要求和场景。

## 推进顺序

| 阶段 | 核心结果 |
| --- | --- |
| P0 | 同一本书内确认大纲、生成、手改、保存、续写和导出 |
| P1 | 版本恢复、选区修改、冲突保护与失败恢复 |
| P2 | 旧章记忆更新、出处明确的一致性反馈和风格控制 |
| P3 | 用量预算、十章验证与作者试用 |

## 使用方式

- 查看状态：`openspec status --change author-workbench`
- 校验计划：`openspec validate author-workbench --strict`
- Claude Code：`/opsx:apply author-workbench`；可在请求中限定仅实施 P0。
- Codex：`$openspec-apply-change author-workbench`；可在请求中限定仅实施 P0。
- 调整范围使用已安装的 `openspec-update-change` 技能；完成全部阶段后再使用归档技能。

新技能未出现在工具界面时，重新打开项目或会话。不要仅凭规划状态完成就宣称业务功能已通过验收。`openspec/specs/` 在本变更归档前保持为空，拟新增需求位于变更目录。
