# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

基于 LangGraph 的 AI Agent 演示项目，包含三个注册在 `langgraph.json` 中的图（graph）：
- `agent` → `src/agent/graph.py:graph` — 模板 Agent（单节点，返回固定字符串）
- `graph` → `src/graph/graph-demo.py:graph_demo` — 三节点流水线演示（Input → Overall → Private → Output，含类型化状态转换）
- `demo_agent` → `src/demo/test-agent.py:graph` — 主聊天 Agent，支持工具调用、技能注册系统、MCP 协议集成
- `novel` → `src/novel/graph.py:graph` — AI 网络小说多 Agent 协作平台，6 个专业 Agent 流水线生成可发布章节
- `world_builder` → `src/world_builder/graph.py:graph` — 世界观编辑器，多轮对话补全小说世界观
- `outline_planner` → `src/outline_planner/graph.py:graph` — 大纲规划器，对话式迭代产出分卷分章大纲
- `character_builder` → `src/character_builder/graph.py:graph` — 人物定义器，对话式定义人物并生成关系图
- `serial_engine` → `src/serial_engine/graph.py:graph` — 连载引擎，多章连续写作 + 分层持久记忆（SQLite，支撑几万章）
- `reader_simulator` → `src/reader_simulator/graph.py:graph` — 读者模拟，从读者视角评估黄金三章/爽点/追读
- `book_packager` → `src/book_packager/graph.py:graph` — 发布包装，书名/简介/章节标题/金句
- `idea_generator` → `src/idea_generator/graph.py:graph` — 创意生成，高概念选题 + 卖点分析
- `director` → `src/director/graph.py:graph` — 一键串联导演，对话式调度全部创作 Agent 从目标到成书

## 常用命令

```bash
# 启动 LangGraph 本地开发服务器（主要开发方式）
langgraph dev

# 启动 Web 前端（Agent Chat UI, 需两个终端）
.venv/bin/langgraph dev --no-browser      # 终端1: 后端 API (localhost:2024)
cd web && pnpm dev                        # 终端2: 前端 (localhost:3000)
# 打开 http://localhost:3000, 默认连 director 图, 左上角可切换 assistant

# 测试
make test                        # 单元测试 (pytest tests/unit_tests/)
make integration_tests           # 集成测试 (pytest tests/integration_tests/)
python -m pytest tests/unit_tests/test_configuration.py -v  # 运行单个测试文件
python -m pytest -k "test_name"  # 按名称运行单个测试

# 代码质量
make lint                        # ruff check + ruff format --diff + ruff check --select I + mypy --strict
make format                      # ruff format + ruff check --select I --fix

# 技能管理
python src/demo/manage_skills.py list|enable|disable|install

# 调仓计划生成（独立脚本）
python generate_rebalance_schedule.py <start_date> <end_date> <exchange> <output_json>

# 连载压力测试（四指标: OOC/伏笔遗忘/剧情重复/套路化）
python scripts/pressure_test.py --story test1 --chapters 10 --premise "..." [--reader-gate] [--deep]
python scripts/pressure_test.py --analyze-only --story test1 --deep  # 只分析已有库
```

## 依赖管理

使用 **uv** 作为包管理器（`uv.lock` 存在）。安装开发依赖：
```bash
pip install -e . "langgraph-cli[inmem]"
```

## 架构要点

### demo_agent 图（核心组件）
- **StateGraph** 结构：`chatbot` 节点（LLM 推理）↔ `tools` 节点（工具执行），通过 `add_conditional_edges` 实现循环
- **技能注册系统**：`src/demo/skills/registry.json` 定义技能映射，运行时动态加载工具模块
- **MCP 集成**：通过 `langchain-mcp-adapters` 连接 ModelScope MCP 服务器获取外部工具
- **LLM 后端**：使用 `ChatTongyi`（通义千问 `qwen-plus` 模型），无 API Key 时回退到本地 echo 模式
- **内置金融工具**：Wind 全A指数K线数据（`wind_skill.py`）、上交所交易日历查询（`sse_calendar_skill.py`）

### novel 图（AI 网络小说协作平台）
- **6 Agent 流水线**：outline → world(并行) → character(并行) → draft → review → (条件循环) → polish
- **审稿循环**：review_agent 输出质量评分(1-10)，低于阈值(7分)则返回 draft_agent 重写，最多 3 轮
- **去 AI 味策略**：内置禁词表(50+高频AI词)、句式变化要求、情感外化指令、人物语言差异卡
- **LLM 可配置**：通过 config 或环境变量切换后端(qwen/claude/openai)，默认 qwen-plus
- **节点模块**：`src/novel/nodes/` 下 6 个独立 Agent 文件，每个有明确的输入/输出职责

### world_builder 图（世界观编辑器）
- **对话式 Agent**：chatbot ↔ tools 循环，MemorySaver checkpointer 支持多轮对话持久化（thread_id）
- **完整性框架**：10 维度清单（力量体系/地理/社会/历史/经济/种族/需求/冲突/看点/规则边界），agent 逐项检测缺口并主动追问
- **核心方法论**：有需求才完整、有冲突才有看点、有边界才可信
- **三个工具**：check_completion（补全进度）/ analyze_consistency（矛盾检测）/ generate_world_bible（导出世界圣经）
- **无缝衔接**：导出的 world_bible 可直接作为 novel 图的 world_setting 输入
- **多轮调用**：同一 thread_id 持续对话，设定跨调用持久化

### outline_planner 图（大纲规划器）
- **对话式迭代**：与 world_builder 同构的 chat loop + MemorySaver 持久化
- **核心价值**：好的小说先有大纲，把世界观+人物转化为可执行的分卷分章大纲
- **规划方法论**：主线贯穿、起承转合、钩子分级(章/卷/全书)、伏笔网络、节奏控制、每章有用
- **结构框架**：核心主线 → 分卷规划(起承转合+卷末大钩子) → 分章大纲(核心事件/冲突/章末钩子/伏笔)
- **三个工具**：check_outline_completion / analyze_plot_consistency / generate_full_outline
- **主动体检**：自动检测主线断裂、伏笔丢失、逻辑矛盾，重焊因果链
- **闭环**：导出的 full_outline 每章可直接作为 novel 图 chapter_outline 输入

### character_builder 图（人物定义器）
- **对话式迭代**：与 world_builder / outline_planner 同构的 chat loop + MemorySaver 持久化
- **10 维度人物清单**：身份/外貌/性格内核/背景/能力树/语言风格/目标欲望/弱点恐惧/成长弧线/关系网络
- **结构化能力树**：能力名/类型/等级/限制与代价/成长方向，防止能力无解
- **人物关系图**：Mermaid 代码 + 渲染为可双击打开的 HTML 文件（`output/character_relations/`）
- **四个工具**：check_character_completion / analyze_character_consistency / generate_character_cards / generate_relationship_graph
- **衔接 novel**：导出的 character_cards 每张含 role/personality/background/speech_style，可直接作为 novel 图 characters 输入

### serial_engine 图（连载引擎）
- **多章连续写作**：init → mem_assemble → contract → write_chapter(封装 novel 图) → reader_check(可选) → mem_update → 条件循环
- **两种模式**：single(单章) / continuous(连续, 输入 chapter_outlines 自动连写)
- **分层记忆**（支撑几万章）：近景(最近3章全文) / 中景(卷摘要+最近5章摘要) / 远景(全书摘要) / 动态状态(人物/伏笔/势力/事件)
- **谁知道什么**：状态提取含每角色 known_info/unknown_info，写作时注入，防 OOC/防提前透传
- **Chapter Contract**：`contract.py` 每章写前生成任务单（目标/必须发生/禁止透露/伏笔推进/预期状态变化/钩子），注入写作硬约束
- **State Diff**：写完对比 contract 预期 vs 实际提取，差异反馈到下一章任务单
- **reader PASS/FAIL 门控**：可选（`reader_gate: bool`），FAIL 带反馈重写整章（≤2次），判定基于追读率预测
- **存储可替换**：`serial_engine/storage.py` 的 StoryRepository 抽象 + SQLiteStoryRepository 实现，未来可换 MySQL
- **摘要压缩**：每章存摘要 → 每10章聚合卷摘要 → 每卷聚合全书摘要，防记忆膨胀
- **断点续写**：同一 story_id 从上次进度继续（SQLite 持久化）
- **压力测试**：`scripts/pressure_test.py` 四指标监控（人物OOC/伏笔遗忘/剧情重复/套路化）
- **场景级重写**：`scene_rewrite.py` reader FAIL 时定位问题场景只重写局部（split→locate→rewrite），替代整章重写
- **番茄风格**：`fanqie_style/guide.py` 内置指南（开篇即炸/高频爽点/短句快节奏），`profile.py` 用户样本风格提取；写作默认注入，`style_mode="generic"` 可关闭
- **每章字数控制**：`chapter_targets` 逐章目标 [{min_words,max_words}]，写前注入 contract、大章节自动调高 max_tokens、写后 `word_check.py` 迭代压缩/扩写（±15%容差），默认番茄 2000-2200

### director 图（一键串联导演）
- 对话式导演：按阶段调用各 Agent（idea→world→character→outline→serial→package），关键节点向作者汇报确认
- 6 个阶段工具复用现有 agent 导出逻辑（generate_idea/build_world/build_characters/plan_outline/prepare_serial/package_book）
- 阶段产物累积在 DirectorState 并**注入导演上下文**（防止"失忆"重复/脑补），可随时调整任一阶段
- **双版本**：`graph`（无 checkpointer，langgraph dev 平台持久化）/ `local_graph`（带 MemorySaver，供本地 python 脚本多轮直接调用）

### reader_simulator / book_packager / idea_generator 图（对话式增强 Agent）
- 三者均为 chat loop + MemorySaver 模式（同 world_builder）
- reader_simulator：assess_chapter(黄金三章/爽点/追读) + suggest_improvements
- book_packager：generate_title / write_blurb / generate_chapter_titles / extract_hooks
- idea_generator：generate_ideas(高概念选题) + assess_idea(市场评估)

### graph-demo 图（三节点流水线）
- 演示 LangGraph 的类型化状态管理：`InputState` → `OverallState` → `PrivateState` → `OutputState`
- 三个节点顺序执行：`node_1` → `node_2` → `node_3`

### 配置文件
- `langgraph.json` — LangGraph 服务器配置，注册所有图入口点
- `pyproject.toml` — Python 项目元数据、依赖、ruff/mypy 配置
- `.env` — 运行时密钥（LangSmith、Qwen、ZhiPu），已在 `.gitignore` 中
- `web/.env` — Agent Chat UI 配置（前端走 `/api` 代理避免 CORS；`LANGGRAPH_API_URL` 指定真实后端）

### Web 前端（Agent Chat UI）
- 官方聊天前端（Next.js），克隆自 `github.com/langchain-ai/agent-chat-ui`
- **代理模式**：前端连自己的 `/api` 代理路由 → 转发到 `LANGGRAPH_API_URL`（默认 localhost:2024），避免 CORS、不暴露后端地址
- 默认连接 `director` 图，可用 URL 参数 `?apiUrl=...&assistantId=...` 覆盖
- 启动需两个终端：后端 `langgraph dev --no-browser` + 前端 `cd web && pnpm dev`
- 前端支持多轮对话、流式输出、工具调用展示；可切换 assistant（12 个图）

## 注意事项

- 项目使用中文系统提示词（`src/demo/test-agent.py` 中的 `system_prompt`）
- `src/demo/test-agent.py` 包含 `if __name__ == "__main__": run_demo()` 可直接运行2轮对话演示
- 单元测试验证图是否为 `Pregel` 实例；集成测试异步调用图并验证输出
