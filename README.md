# GIIM

GIIM（Global Intelligence & Impact Monitor）是一个全球事件智能监测与影响分析系统。
它会从多源新闻聚合信息，并通过 LLM Agent 完成事件聚类、时间线重建、实体识别与影响分析，最终输出结构化简报。
当前仓库处于工程化初始化阶段，重点是搭建可扩展的后端基础设施。

## 技术栈

| 类别 | 技术 |
| --- | --- |
| 语言与依赖 | Python 3.11 + uv |
| API 框架 | FastAPI + Uvicorn |
| 数据库 | PostgreSQL 16 + SQLAlchemy 2.0(Async) + Alembic |
| 向量数据库 | Qdrant |
| 日志 | structlog |
| 测试 | pytest + pytest-asyncio |
| 部署 | Docker Compose |

## 快速启动

1. 复制环境变量模板  
   `cp .env.example .env`
2. 启动全部服务  
   `docker-compose up --build`
3. 打开接口文档  
   [http://localhost:8000/docs](http://localhost:8000/docs)

## 项目结构

核心目录说明：
- `apps/api/src/core/`：配置、日志、异常与生命周期管理
- `apps/api/src/db/`：异步数据库连接与依赖注入
- `apps/api/src/vector/`：Qdrant 向量存储封装
- `apps/api/src/routers/`：API 路由层
- `tests/`：接口与模块测试
- `docs/`：开发文档与日志

## 开发计划（8 周简版）

- Week 1：工程骨架、基础服务、健康检查、迁移框架
- Week 2：RSS 数据采集与清洗流程
- Week 3：向量化与事件聚类基线
- Week 4：多 Agent 编排与任务流
- Week 5：影响分析与结构化简报输出
- Week 6：评估体系与质量回归
- Week 7：前端与可视化联调
- Week 8：稳定性优化与交付准备

## 当前进度

Week 1 Day 1 ✅
