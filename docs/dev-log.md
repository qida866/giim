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



## Day 2 - 2026-05-06

### 完成内容
- 6 张核心业务表设计与建立
- 第一个业务接口 GET /api/v1/news,支持分页+过滤
- 10 条多语言仿真数据 seeding
- 端到端验证:数据库 → ORM → API → JSON

### 工程问题 9:ruff F821 与 SQLAlchemy 字符串 forward reference 冲突
- 现象:在 model 文件里用 `Mapped[list["EventEntity"]]` 写法时,
  ruff 静态分析报 F821 Undefined name "EventEntity"
- 根因:SQLAlchemy 的字符串 forward reference 是运行时解析的,
  ruff 看不到它的定义
- 解决:在每个 model 文件顶部加 TYPE_CHECKING 块:
```python
  from typing import TYPE_CHECKING
  if TYPE_CHECKING:
      from src.models.event import Event, EventEntity
```
  这样 mypy/ruff 能看到类型,运行时不会真的执行 import
- 反思:这是"静态分析工具"和"运行时框架"的语义鸿沟。
  TYPE_CHECKING 是 PEP 484 给出的标准解法,值得记住。

### 工程问题 10:scripts 目录漏挂载到容器(与 Day 1 tests 同因)
- 现象:docker compose exec api python scripts/seed_news.py
  报 No such file or directory
- 根因:docker-compose.yml 的 api 服务 volumes 没挂载 ./scripts
- 解决:追加 - ./scripts:/app/scripts,然后 docker compose down + up -d
- 反思:同类问题一周内出现两次("配置漂移"),
  说明项目层面缺少"必挂目录的清单约束"。
  改进方向:在 README 里维护"必须挂载的目录清单",
  或用 docker compose profiles 区分 dev/prod 配置。

### 工程问题 11:Pydantic response_model 缺失导致 OpenAPI schema 不完整
- 现象:Swagger 上 200 响应的 Example Value 显示 {"additionalProp1": {}}
  占位符,而不是真实的返回结构
- 根因:路由 @router.get() 没声明 response_model 参数,
  FastAPI 不知道返回的 dict 是什么类型
- 解决:新建 NewsListResponse(BaseModel) 包装分页结构,
  在路由装饰器加 response_model=NewsListResponse
- 反思:response_model 不是"可选的文档美化"——
  它同时承担返回值类型校验、序列化优化、API 契约文档三个职责。
  这是面向接口编程的工程素养基础。


  ## Day 3 - 2026-05-06

### 完成内容(A 阶段)
- 添加 3 个采集相关依赖(feedparser/beautifulsoup4/python-dateutil)
- ingestion 模块骨架建立(rss_fetcher/deduplicator/orchestrator)
- rss_fetcher.py 完整实现:异步 HTTP + RSS 解析 + HTML 清洗
- 端到端验证:从真实 BBC RSS 拉取 36 条新闻

### 工程问题 12:Dockerfile 硬编码依赖与 pyproject.toml 漂移

- 现象:在 pyproject.toml 添加新依赖,docker compose build 显示 38 秒
  "build 完成",但容器内 import feedparser 仍报 ModuleNotFoundError
  
- 排查路径(这才是最有价值的部分):
  1. 第一反应是缓存陷阱,加 --no-cache 重 build,仍失败
  2. 怀疑 Cursor 没把依赖加进 pyproject.toml,grep 验证后排除
  3. 怀疑加错位置(进了 dev-only 段),检查后排除
  4. 检查 Dockerfile 实际安装命令,发现 RUN uv pip install --system
     后跟的是硬编码 14 个包名,根本不读 pyproject.toml
  
- 根因:Day 1 Dockerfile 用了硬编码包名列表,与 pyproject.toml 形成
  "双真相",任一改动不会触发另一处更新——典型"配置漂移"
  
- 解决:在 Dockerfile RUN uv pip install 列表里手动追加 3 个新依赖
  
- 反思:
  - Day 2 已踩过一次配置漂移(scripts 目录),今天又是同类——
    项目里有多份"真相",治标不治本
  - 长期改进:Dockerfile 改用 uv pip install --system .
    让 pyproject.toml 成为唯一依赖来源(标记为 TODO,不在 Day 3 处理)
  - 排查路径本身的价值:"build 时间从 4s 变 38s"是关键诊断信号
  - 真实工作中,每个"看似奇怪的现象"都有它的精确含义,
    工程师的训练就是从中拎出"关键诊断信号"

### 工程问题 13:httpx 默认不跟随 HTTP 重定向

- 现象:第一次跑 RSS 拉取测试,BBC 拉取失败,error='HTTP 302'
  
- 根因:
  - httpx.AsyncClient 默认 follow_redirects=False
    (这与 requests 库默认行为相反)
  - 大量历史 RSS feed URL 仍是 http://, 服务都迁了 https://
  - 不跟随重定向时,302 被 raise_for_status() 抛成错误
  
- 解决:创建 client 时显式传 follow_redirects=True
  
- 反思:
  - HTTP 客户端库的"默认行为"差异是经典坑——
    requests/httpx/aiohttp 三家在重定向、超时、SSL 默认值都不同
  - 真实工程实践:写 HTTP 客户端时把 timeout/redirects/headers
    全部 explicitly 配置,不依赖任何默认值
  - 也是 RSS 采集系统的经典坑:大量 feed 仍用历史 HTTP URL