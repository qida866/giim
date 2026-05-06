# GIIM 开发日志

## Day 1（2026-05-06）

### 概述
GIIM 项目从 0 到 1 启动。完成项目骨架搭建、Docker Compose 三服务编排、健康检查接口与异步测试框架。
- 首次 git commit：`b6c629d`
- 39 文件，873 行代码
- 历时约 1 小时（17:00 - 17:41）
- 解决 8 个真实工程问题

### 完成清单
- [x] 项目目录结构与基础配置（19+ 文件骨架）
- [x] Docker Compose 三服务编排（Postgres / Qdrant / API）
- [x] FastAPI + lifespan 应用骨架
- [x] SQLAlchemy 2.0 异步 + Alembic 迁移配置
- [x] structlog 结构化日志
- [x] 自定义异常体系与全局处理器
- [x] 三个健康检查接口 200 OK
- [x] pytest + httpx.AsyncClient 异步测试通过
- [x] First Git commit (b6c629d)

### 八个工程问题与解法

#### 1. Docker Compose 命令演进（v1 vs v2）
- **现象**：`zsh: command not found: docker-compose`
- **根因**：Docker Compose v2 已合并进 Docker CLI，命令从 `docker-compose`（带横杠的独立二进制）改为 `docker compose`（空格，CLI 子命令）
- **解决**：所有命令改用 `docker compose`
- **反思**：项目 README 应统一使用新命令，避免新人入门卡壳。AI 训练数据里很多还是老命令，要主动识别并修正。

#### 2. docker.com 域名解析失败
- **现象**：浏览器访问 docker.com 报 ERR_NAME_NOT_RESOLVED
- **根因**：国内网络访问 docker.com 受限
- **解决**：通过国内镜像/代理下载 Docker Desktop
- **反思**：国内做产品级项目时，要提前准备好 npm/pip/docker hub 等海外资源的镜像源——这是隐性的环境基建成本，新手最容易低估。

#### 3. Docker Desktop 安装与基础设施前置
- **现象**：本机未装 Docker
- **解决**：下载安装 Docker Desktop，启动后等鲸鱼图标稳定
- **反思**：项目 README 必须在"快速启动"一节明确列出环境前置（Docker Desktop 已安装且正在运行 / Python 3.11+ 等），否则新人一上来就会卡住。

#### 4. Qdrant healthcheck 失败但服务正常
- **现象**：Qdrant 服务实际正常运行（监听 6333/6334），但被 docker 标记 unhealthy，导致 api 因 `depends_on: condition: service_healthy` 无法启动
- **根因**：Qdrant 镜像是 distroless 极简镜像，不包含 wget/curl/bash，默认配置的 healthcheck 命令在容器内无可用工具，永远失败
- **解决**：
  1. 删除 qdrant 服务的 healthcheck 配置
  2. 把 api depends_on 中 qdrant 的 condition 改为 `service_started`
- **反思**：
  - "depends_on + healthcheck" 看似标准但容易踩坑
  - 用第三方镜像必须先确认它支持你假设的 healthcheck 命令
  - 实际上应用层的 lifespan.py 已主动探活 Qdrant，容器层 healthcheck 反而冗余

#### 5. structlog PrintLogger 与 add_logger_name 不兼容
- **现象**：API 启动失败，报 `AttributeError: 'PrintLogger' object has no attribute 'name'`
- **排查过程**：
  - v1 假设：模块导入顺序问题。在模块加载时调用 `configure_logging()` → 失败
  - v2 看堆栈最后一行：`event_dict["logger"] = logger.name` 在 `add_logger_name` 处理器中崩溃
  - 真正根因：`structlog.PrintLoggerFactory` 创建的 PrintLogger 是极简实现没有 `.name` 属性，与 stdlib 处理器 `add_logger_name` 不兼容
- **解决**：从处理器链中移除 `structlog.stdlib.add_logger_name`
- **反思**：
  - AI 生成代码时容易把"看起来都属于 structlog 的"组件随意拼接，忽略它们之间的兼容性约束
  - 修 bug 第一假设可能是错的，看错误堆栈最后一条到第一条逐层向上找根因，比凭直觉猜更可靠
  - 这种"组件兼容性 bug"在 vibe coding 时很常见，未来 review 要把"组件来源一致性"作为重点

#### 6. Dockerfile 缺少 dev 依赖
- **现象**：`docker compose exec api pytest` 报 `"pytest": executable file not found in $PATH`
- **根因**：Dockerfile 的 `uv pip install --system` 只装了核心依赖，没装 [dev-dependencies] 中的 pytest
- **解决**：在 builder 阶段显式追加 pytest、pytest-asyncio、pytest-cov、ruff、mypy 等 dev 依赖
- **反思**：依赖管理是软件工程常见难题。生产镜像 vs 测试镜像的依赖应该明确分层——保持镜像精简但要保证测试可在容器内运行。

#### 7. Docker volumes 漏挂载 tests 目录
- **现象**：pytest 启动成功但 `collected 0 items, no tests ran`
- **根因**：docker-compose.yml 的 volumes 挂载列表里漏挂了 `./tests` 目录，容器内 `/app/tests` 不存在
- **解决**：volumes 增加一行 `./tests:/app/tests`
- **反思**：
  - "代码挂载到容器"是个常被忽视的列表，要把所有需要在容器里访问的目录都列出来
  - "collected 0 items" 不是 bug，是字面意思——找不到文件。遇到"看似没出错但什么都没发生"的输出，要回头检查环境/路径假设

#### 8. pytest 9 + pytest-asyncio strict 模式
- **现象**：pytest 找到测试，但报 `PytestRemovedIn9Warning: 'test_health' requested an async fixture` + `async def functions are not natively supported`
- **根因**：pytest 9 进一步收紧了对异步 fixture 的支持，必须用 `@pytest_asyncio.fixture` 显式标注异步 fixture，且测试函数必须用 `@pytest.mark.asyncio` 装饰，否则不会被 pytest-asyncio 接管
- **解决**：
  1. test_health.py 顶部 `import pytest`，给 test_health 函数加 `@pytest.mark.asyncio`
  2. conftest.py 把异步 fixture 改用 `@pytest_asyncio.fixture` 装饰
- **反思**：
  - Python 库 deprecation → removal 演进的典型案例，pytest 9 把 8.x 时的 warning 升级为 error
  - vibe coding 时 Cursor 可能给出旧版语法，要根据实际安装的版本修正
  - 看 warning 不要忽略——"This will turn into an error in pytest 9" 就是明确的升级指引

### 收获
1. 学会用 Cursor 高效构建产品级项目骨架，但每一处都自己 review 过、跑通过
2. 第一次完整经历从下载 Docker → 部署服务 → 修 bug → 提交代码的全流程
3. 第一次理解 Docker depends_on + healthcheck 的真实工作机制
4. 第一次读懂 structlog 处理器链与 logger factory 的关系
5. 第一次面对 8 个独立问题且全部独立解决——长出了"工程嗅觉"

### 明日计划（Day 2）
- 设计核心数据模型：news, events, event_news, entities, briefings
- Alembic 跑通第一次迁移
- GET /api/v1/news 接口 + seeding 脚本（10 条假数据）
- 用 DBeaver 连上 Postgres 看到结构化数据