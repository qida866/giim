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


  ## Day 3 - 2026-05-10

### 完成内容

完整实现 RSS 采集系统的四阶段:
- A 阶段:单源拉取(rss_fetcher.py)
- B 阶段:双 hash 去重+批量入库(deduplicator.py)
- C 阶段:多源并发+错误隔离(orchestrator.py)
- D 阶段:POST /api/v1/ingestion/trigger HTTP 接口

实测从 5 个真实 RSS 源拉取 462 条新闻,
端到端验证 HTTP 触发的完整链路。

### 工程问题 14:Docker Desktop 开发环境断档

- 现象:断档 4 天后回来跑 docker compose exec 报
  "Cannot connect to the Docker daemon"
- 根因:Mac 重启后 Docker Desktop 不会自动启动,
  容器(postgres/qdrant/api)默认也不会自动恢复
- 解决:启动 Docker Desktop -> docker compose up -d
- 反思:
  - 这是开发环境工程化盲点
  - 改进:在 docker-compose.yml 加 restart: unless-stopped,
    Mac 重启后容器自动恢复
  - 真实生产环境这种问题不存在,因为 systemd / k8s 兜底

### 工程问题 15:httpx.AsyncClient timeout 范围误解

- 现象:HTTP 日志清晰显示 GET 200 OK,但程序报 Timeout after 10s
- 排查路径(这是最有价值的部分):
  1. 第一反应是网络问题,但 200 OK 排除
  2. 怀疑 feedparser 解析慢,量级不对
  3. 真相:整个 async with 块累计耗时超过 10s
- 根因:httpx.AsyncClient(timeout=10.0) 的 timeout 是
  整个上下文管理器的 cumulative deadline,
  不只是 HTTP 请求本身。链路是:
    HTTP 请求 + 重定向跟随 + RSS 下载 +
    feedparser 同步解析 + BeautifulSoup HTML 清洗 +
    36 个 Pydantic 模型构造
  全部累计可能超过 10s
- 解决:timeout 30s(治标),记 TODO:
  治本是把 feedparser.parse 拿到 with 块外
- 反思:
  - "异步上下文管理器的 deadline" 跟 "请求超时" 不是一个概念
  - 真实 RSS 采集器要面对很多源,有的服务器慢、有的解析重,
    必须把网络阶段和解析阶段分开计时
  - 这是 senior 工程师才会注意到的边界情况

### 重要技术债 TODO

1. **Dockerfile 依赖管理**(Day 3 工程问题 12 留下):
   - 当前:Dockerfile 硬编码 14 个包名,与 pyproject.toml 形成"双真相"
   - 目标:改用 uv pip install --system .,让 pyproject.toml 单一来源
   - 估时:1 小时,优先级中

2. **httpx timeout 拆分**(Day 3 工程问题 15 留下):
   - 当前:timeout=30 一刀切,网络+解析合计计时
   - 目标:把 feedparser.parse 拿到 with 块外
   - 估时:30 分钟,优先级低

3. **异步触发模式**:
   - 当前:POST /trigger 同步执行 3 秒
   - 目标:用 Celery/RQ 改成异步,立刻返回 task_id
   - 估时:2-3 小时,留给 Day 6+

4. **正式鉴权**:
   - 当前:query param + 静态 token,够开发用
   - 目标:JWT + 用户系统
   - 估时:Day 6 用户系统时一并做

5. **test_ingestion_trigger.py 验证**:
   - 当前:Cursor 自动写了测试,但还没在 CI 验证过能跑
   - 目标:Day 4 之前花 10 分钟跑 pytest tests/test_ingestion_trigger.py -v
   - 估时:10-30 分钟

## Day 4 - 2026-05-11 (A 阶段: LLM 客户端)

### 完成内容

- DeepSeek API 账户开通与充值（¥10），完成 key 配置并通过真实调用验证可用。
- 新增 LLM 模块 `apps/api/src/llm/`：
  - `schema.py`：定义 5 个 Pydantic 模型（消息/请求/用量/响应）+ `LLMErrorType` 枚举 + `LLMError` 异常；
  - `client.py`：封装 `AsyncOpenAI`，支持 3 次指数退避重试（1s/2s/4s）+ 双层超时（httpx 30s + `asyncio.wait_for` 60s）+ 5 类错误分类 + structlog 结构化日志；
  - `__init__.py`：对外导出 7 个核心符号，统一 import 入口。
- 新增 `tests/test_llm_client.py`：3 个测试（1 个 unit + 2 个 integration），当前全部通过。
- `pyproject.toml` 注册 pytest 自定义 marker：`integration`。
- `docker-compose.yml` 为 `api` service 增加只读挂载：`./pyproject.toml:/app/pyproject.toml:ro`。
- `Dockerfile` 与 `pyproject.toml` 同步追加 `openai>=1.50.0`，修复容器重建后依赖丢失问题。

### Day 4 工程问题

#### 工程问题 16: API key 长度的先验假设错误

- **现象**：用 `awk` 看到 key 长度是 35，误以为“正确 key 应该是 51”，来回验证浪费约 20 分钟。
- **根因**：不同平台 key 规则不同：OpenAI 常见约 51，Anthropic 约 108，DeepSeek 是 35；把“某个平台经验值”当成通用规则是错误先验。
- **解决**：不再用长度做真伪判断，直接做最小 API 调用验证。
- **反思**：
  - 先验在工程里只能作为“线索”，不能作为“证据”；
  - 能跑通的调用才是唯一真相（runtime truth > assumption）。

#### 工程问题 17: Docker 容器内 uv/包管理三重陷阱

- **现象**：容器重建后 `openai` 包消失，测试报 `ModuleNotFoundError`。
- **诊断过程**：
  - 18:14 首次执行 `docker compose exec api uv pip install openai`，报 `uv: not found`；
  - 18:14 改用 `pip install openai` 临时成功，测试通过；
  - 19:10 修改 `docker-compose.yml` 挂载 `pyproject.toml` 后执行 `docker compose up -d api`；
  - 19:11 再跑测试，重新报 `ModuleNotFoundError: No module named 'openai'`。
- **三重根因**：
  1. **uv binary 跨 stage 丢失**：Dockerfile 为 multi-stage；builder 装在 `/root/.local/bin/uv`，runtime 只 `COPY /usr/local`，导致 `uv` 命令不在最终镜像；
  2. **依赖双真相漂移**：Dockerfile 硬编码依赖列表 vs `pyproject.toml` 声明式依赖，两边都漏 `openai`；
  3. **运行时安装不持久**：`docker exec pip install` 只对当前容器生效，重建后必丢。
- **临时解决**：`openai` 同时加入 `pyproject.toml` + Dockerfile，然后 rebuild。
- **彻底解决（TODO）**：
  - Dockerfile 改为 `COPY pyproject.toml ./` + `uv pip install --system -e .`，消除依赖双真相；
  - runtime stage 显式复制 uv binary（`/root/.local/bin/uv`）；
  - 计划 Week 1 收官统一处理。
- **反思**：
  - “配置在哪儿存在”不等于“配置在哪儿生效”；
  - “装上了包”不等于“包会永久存在”；
  - Docker 的核心哲学是声明式构建，而不是命令式补丁。

#### 工程问题 18: Cursor 文件树显示名 vs 磁盘真实文件名

- **现象**：文件树看起来像 `test_llm`，执行 `cat test_llm.py` 报 `No such file`。
- **诊断信号**：底部状态栏显示 `Ini` 而非 `Python`，提示文件类型异常。
- **根因**：创建文件时漏了 `.py` 扩展名，磁盘真实文件名是 `test_llm`（无后缀）。
- **解决**：执行 `mv test_llm test_llm.py` 修正。
- **反思**：文件树有 UI 呈现层，真正可靠的是磁盘路径 + 语言识别信号。

#### 工程问题 19: pyproject.toml 未被容器看到导致 marker 不生效

- **现象**：宿主机 `pyproject.toml` 已加 `markers`，但容器内 pytest 仍提示 unknown marker warning。
- **根因**：Day 3 Dockerfile 依赖安装走硬编码列表，镜像内并未携带 `pyproject.toml`；同时 compose 未挂载根目录该文件。
- **诊断信号**：`docker compose exec api ls /app/pyproject.toml` 报 `No such file`。
- **解决**：在 compose 中增加只读挂载：
  - `./pyproject.toml:/app/pyproject.toml:ro`
- **反思**：
  - `.env` / Dockerfile / `pyproject.toml` 分别走不同路径（mount / COPY / 缺省不存在）；
  - 每种配置文件都要单独确认“是否进入容器、何时生效、谁负责更新”。

### 关键技术决策

1. **LLM 选型**：DeepSeek V4 Flash（`deepseek-chat` 路由）
   - 价格：$0.14/M input + $0.28/M output，适合高频实验；
   - 未选 Ollama：本机部署成本与速度/质量折中不划算；
   - 未选其他平台：切换成本高于当前阶段收益。
2. **Embedding 选型**：本地 `bge-m3`（留到 B 阶段实施）。
3. **重试策略**：仅 `RATE_LIMIT` / `TIMEOUT` 重试，`AUTH` 立即抛出，避免无效重试浪费时间与 token 成本。
4. **研发流程**：design-first（先设计草案 -> review -> 再编码），把返工前移到文字层，减少代码层重写。

### TODO (技术债)

[继承自 Day 3]
1. Dockerfile 改用 `uv pip install --system -e .` 走 `pyproject.toml`，消除依赖双真相（Week 1 收官做）。
2. RSS 模块的 httpx timeout 细分（连接/读取/总超时拆分），当前 30s 先够用。

[Day 4 新增]
3. Dockerfile runtime stage COPY uv binary，保留 `uv` 命令（与 TODO #1 一起做）。
4. `.env` 清理：当前存在 2 行 `DEEPSEEK_API_KEY`（一空一真），保留真实值那行。
5. integration 测试默认在 CI 跳过，避免外部 API 成本与环境波动：

```bash
pytest -m "not integration"
```

### 时间统计

- 17:45-18:14：Day 4 准备（注册 + 充值 + 配 key）
- 18:14-18:20：安全教训（key 截图泄露，作废并重建）
- 18:20-18:25：LLM 选型决策
- 18:25-19:00：A 阶段代码生成 + review + 测试
- 19:00-19:25：marker 配置 + 容器重建踩坑 + 修复
- **总计约 1 小时 40 分钟**（其中约 50 分钟用于 Docker 环境调试）

## Day 4 - 2026-05-11 (B 阶段: 本地 Embedding 集成) 续

### 完成内容

- 新增 Embedding 模块 `apps/api/src/embedding/`：
  - `schema.py`：5 个 Pydantic 模型（`EmbeddingRequest` / `EmbeddingResult` / `EmbeddingBatchResponse`）+ `EmbeddingText`（`Annotated[str, max_length=8192]`）类型别名 + `EmbeddingErrorType` 4 类枚举 + `EmbeddingError` 异常（4 字段，含 `batch_size`）；
  - `client.py`：`EmbeddingClient` 封装 sentence-transformers：
    - 懒加载 + 双重检查锁（`threading.Lock` 防止并发首次请求重复加载）；
    - `asyncio.to_thread` 包装同步 `model.encode`（避免阻塞 FastAPI event loop）；
    - 业务级输入校验（空白/超长直接报错，不截断保持语义）；
    - 6 个日志事件（`loading` / `loaded` / `load_failed` / `encode_start` / `success` / `failed`）；
    - 4 类错误分类（`MODEL_LOAD` / `INVALID_INPUT` / `ENCODE` / `UNKNOWN`）；
    - device 可配置（`cpu` / `cuda` / `mps`），从环境变量读取；
  - `__init__.py`：6 个核心符号统一导出。
- 新增 `tests/test_embedding.py`：3 个 integration 测试：
  - `test_embed_single`（单条 1024 维向量）；
  - `test_embed_batch`（3 条批量，顺序保持）；
  - `test_embed_semantic_similarity`（跨语言相似度，“美联储宣布降息”和“Fed cuts interest rates”余弦相似度 > 0.7）。
- 模型选型：`BAAI/bge-m3`（1024 维，中英双语，8192 上下文）。
- 配置变更：
  - `pyproject.toml`：追加 `sentence-transformers>=3.0.0` + `torch>=2.0.0`；
  - `Dockerfile`：分两步安装，torch CPU 版使用 `--index-url https://download.pytorch.org/whl/cpu`（避免 NVIDIA 全家桶）；
  - `docker-compose.yml`：追加 volume `./.model_cache:/app/.cache/huggingface` + 3 个 `EMBEDDING_*` 环境变量；
  - `.env.example`：追加 3 个占位符（`EMBEDDING_MODEL_NAME` / `EMBEDDING_CACHE_DIR` / `EMBEDDING_DEVICE`）；
  - `.gitignore`：追加 `.model_cache/`（模型 2.3GB，不进 git）。

### 测试结果

- 首次跑（含模型下载）：`3 passed in 156.02s`（2 分 36 秒）。
- 第二次跑（缓存命中）：`3 passed in 32.27s`（32 秒，5 倍提速）。
- 缓存挂载有效：宿主机 `.model_cache` 持久化 2.3GB，容器重启秒加载。

### Day 4 B 阶段工程问题

#### 工程问题 20: torch 默认装 GPU 版，触发 NVIDIA 全家桶下载

- **现象**：`docker compose build api` 失败，`nvidia-cudnn-cu13`（414MB）下载超时。
- **诊断信号**：build 日志出现 `nvidia-cublas`（517MB）/ `nvidia-cusparselt-cu13`（210MB）/ `nvidia-nccl-cu13`（187MB）/ `nvidia-cufft`（204MB）/ `nvidia-cusolver`（213MB）等一系列 GPU 包。
- **根因**：`pip install torch` 默认 wheel 包含 CUDA 链接，自动拉取 2-3GB NVIDIA 全家桶。
- **解决**：Dockerfile 拆两步安装，torch 先用 `--index-url https://download.pytorch.org/whl/cpu` 单独安装 CPU 版。
- **副作用（正向）**：build 时间从约 18 分钟降到 3-5 分钟，镜像缩小约 2GB。
- **反思**：
  - PyPI 默认 wheel 常面向“最常见硬件配置”（torch 默认 GPU）；
  - CPU-only 部署必须显式声明，否则会被动承受 GPU 依赖膨胀；
  - **ML 部署的隐藏成本：依赖膨胀往往比代码膨胀严重一个数量级。**

#### 工程问题 21: mypy 下载网络超时

- **现象**：第二次 docker build 失败，`mypy`（13.2MB）下载超时。
- **根因**：PyPI 国际访问偶发不稳定。
- **解决**：直接重试 `docker compose build api`；uv 会复用已下载缓存，只补缺失包，1-2 分钟恢复成功。
- **反思**：
  - 大批量依赖一次性安装时，任何单包超时都会导致整层失败；
  - **理想做法是按依赖分组多个 RUN 层**，降低单点失败重试成本；
  - 国内 PyPI 直连不稳是常态，Week 1 收官可评估 `--default-index` 使用清华镜像。

#### 工程问题 22: ML 模型缓存差点被 git 追踪

- **现象**：测试通过后 `git status` 显示 `.model_cache/`（2.3GB）在 untracked 列表。
- **风险**：若 commit + push，GitHub 100MB 单文件上限会导致 push 失败，同时污染协作者仓库历史。
- **根因**：`docker-compose.yml` 挂载 `./.model_cache` 到容器，模型下载落在宿主机该目录，git 自动可见。
- **解决**：`.gitignore` 追加 `.model_cache/`。
- **反思**：
  - 任何 GB 级文件都不应进 git；
  - ML 项目要 day-one 配置 `.gitignore`，不能等下载后补救；
  - **添加 volume 挂载时，要同步检查 `.gitignore`。**

### 关键技术决策

1. Embedding 模型：`BAAI/bge-m3`（1024 维，中英双语，8192 上下文）。
2. 库：sentence-transformers（API 友好度高于 FlagEmbedding）。
3. 设备：容器内 CPU（Mac MPS 容器访问不到，且生产部署通常优先 CPU 基线）。
4. 加载策略：懒加载 + 双重检查锁（避免并发首次请求重复加载 2.3GB 模型）。
5. 缓存策略：volume 挂载到宿主机，持久化 + 5 倍提速。
6. 异步策略：`asyncio.to_thread` 包装同步 encode（CPU 密集任务不能阻塞 event loop）。
7. torch wheel：使用 CPU index 安装，规避 GPU 全家桶。

### TODO (技术债)

[继承自 Day 4 A 阶段]
1-5 见 A 阶段记录。

[Day 4 B 阶段新增]
6. Dockerfile 一次性安装 24 个包，任一失败会导致整层重做；Week 1 收官评估 BuildKit `--mount=type=cache` 或按依赖分组多 RUN 层。
7. 国内 PyPI 网络不稳，Week 1 收官评估 `--default-index` 切换清华镜像。
8. `huggingface_hub` 的 `hf_xet.download_files()` DeprecationWarning：等待 upstream 升级自动消除，当前不做主动处理。

### 时间统计

- 19:16-19:35：B1.1 方案对齐 + B1.2 设计草案 v1
- 19:35-20:00：B1.2 设计草案 v2 + 第 1 批代码生成（只展示）
- 20:00-20:10：第 1 批代码真实落地 + review
- 20:10-20:15：第 2 批配置变更（4 个 diff）
- 20:15-20:35：第一次 build 失败（NVIDIA 全家桶 18 分钟超时）
- 20:35-20:50：第二次 build 失败（mypy 网络超时）
- 20:50-21:00：第三次 build 成功（重试）
- 21:00-21:04：测试通过（3 passed in 156.02s）
- 21:04-21:10：缓存验证 + `.gitignore` 修复
- **总计约 1 小时 55 分钟**（其中约 35 分钟用于 Docker build 失败与重试）

### 当前 Day 4 累计进度

- A 阶段（LLM 客户端）：✅ 完成 + commit + push
- B 阶段（Embedding 集成）：✅ 完成，待 commit
- 后续：Day 5 做 Qdrant 集合初始化 + 462 条新闻批量回填 embedding + 语义搜索接口