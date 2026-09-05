# Repository Guidelines

## 项目结构与模块划分

本项目是 AI 小说创作平台，后端使用 Python 和 LangGraph，前端使用 Next.js、React 和 TypeScript。

- `src/` 存放工作流模块，包括 `novel`、`world_builder`、`serial_engine`、`setting_studio` 等。通常按 `graph.py`、`state.py`、`prompts.py`、`tools.py` 拆分流程、状态、提示词与工具；小说生成节点位于 `src/novel/nodes/`。
- `langgraph.json` 注册工作流入口，`pyproject.toml` 声明 Python 依赖和打包模块。新增工作流包时同步检查这两处配置。
- `web/src/` 下的 `app/`、`components/`、`hooks/`、`providers/` 分别存放路由、组件、钩子和上下文提供者。
- `tests/unit_tests/` 和 `tests/integration_tests/` 存放后端测试；`scripts/` 提供导出和压力测试工具；`static/` 存放静态资源。生成产物放入已忽略的 `output/`。

## 安装、开发与检查命令

后端命令在仓库根目录执行，要求 Python 3.10 或以上版本：

- `uv sync --group dev`：安装项目依赖和开发工具。
- `uv run langgraph dev`：根据 `langgraph.json` 启动本地工作流服务。
- `uv run pytest tests/unit_tests/`：运行单元测试。
- `uv run pytest tests/integration_tests/`：运行集成测试。
- `uv run ruff check .`：检查 Python 代码规范。
- `uv run ruff format .`：格式化 Python 代码。
- `uv run mypy --strict src/`：执行严格类型检查。

前端命令在 `web/` 执行：`pnpm install` 安装依赖，`pnpm dev` 启动开发服务，`pnpm build` 构建生产版本。提交前端改动前运行 `pnpm lint` 和 `pnpm format:check`。

## 代码风格与命名

Python 使用四空格缩进，函数和模块使用 `snake_case`，类使用 `PascalCase`；补充类型注解，采用 Google 风格文档字符串，并遵循 Ruff 的导入排序规则。

TypeScript/TSX 使用两空格缩进，组件使用 `PascalCase`，函数使用 `camelCase`；通过 Prettier 统一格式和 Tailwind 类名顺序。修改前端代码前，遵循 `web/AGENTS.md`，阅读已安装 Next.js 包中的相关文档。

## 测试要求

使用 pytest，测试文件命名为 `test_*.py`，测试函数以 `test_` 开头。异步集成测试使用 AnyIO 的 asyncio 后端。现有测试主要是基础冒烟测试，尚未配置覆盖率门槛。

修改工作流行为时添加针对性的回归测试；单元测试中模拟外部模型调用。前端尚未配置测试脚本，界面改动需说明手动验证步骤和结果。

## 提交与合并请求

近期提交使用 `feat:` 前缀和中文说明；沿用简洁、描述明确的提交风格。合并请求应说明行为变化、关联相关问题、列出已执行的检查；界面改动附截图，并注明配置变化及尚未验证的部分。

## 安全与配置

将 `.env.example` 复制为 `.env` 配置本地环境。不要提交 API 密钥、生成的小说正文或运行时数据库；新增配置项使用占位值说明。
