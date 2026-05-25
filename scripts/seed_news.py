"""新闻种子数据脚本，用于本地开发时初始化测试新闻数据。"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from src.db.session import AsyncSessionLocal
from src.ingestion.deduplicator import compute_hashes
from src.ingestion.rss_fetcher import ParsedNewsItem
from src.models.news import News


def _build_seed_payload() -> list[News]:
    """构建 10 条仿真新闻数据。"""
    source_names = ["Reuters", "BBC", "新华社", "Bloomberg", "WSJ"]
    titles = [
        "AI chip startups accelerate global data center expansion plans",
        "欧盟就关键矿产供应链提出新一轮联合采购机制",
        "Federal Reserve signals caution as inflation cools unevenly",
        "亚太多国推进跨境数字支付试点，结算效率显著提升",
        "Major cloud vendors announce open model interoperability pact",
        "中东停火谈判出现进展，能源市场波动率短线回落",
        "Global banks test tokenized bond settlement on shared ledgers",
        "中国多地发布低空经济支持政策，产业链投资升温",
        "Cybersecurity firms warn of AI-assisted phishing surge in Q2",
        "全球航运指数反弹，制造业补库需求带动运价上行",
    ]
    contents = [
        "多家芯片初创公司近期宣布扩建算力中心，目标覆盖北美与欧洲市场。Analysts say demand from generative AI workloads remains strong, while capital expenditure discipline is still a key concern. 企业在采购 GPU 与网络设备时更重视交付周期和能耗表现，供应链协同成为竞争焦点。",
        "欧盟委员会提出关键矿产联合采购草案，旨在降低对单一来源的依赖。The proposal focuses on lithium, cobalt, and rare earth elements, and encourages long-term offtake contracts. 市场人士认为，该机制若落地将提升议价能力，但也可能推高短期库存成本。",
        "最新会议纪要显示，美联储官员对通胀回落节奏保持谨慎。Traders trimmed expectations for aggressive rate cuts after mixed labor data. 与此同时，企业融资环境边际改善，信贷利差仍处于历史中位区间，市场对下半年政策路径分歧加大。",
        "亚太地区数个经济体启动跨境数字支付互联试点，面向中小企业贸易结算。Pilot participants reported faster confirmation times and lower transaction fees. 监管机构强调将持续评估合规、反洗钱与数据跨境流动风险，逐步扩大应用场景。",
        "三家头部云厂商共同发布模型互操作协议草案，覆盖推理接口与安全审计。The group said open standards can reduce vendor lock-in for enterprise AI adoption. 开发者社区关注标准兼容性与迁移成本，预计相关工具链将在未来两个季度快速演进。",
        "中东地区停火谈判取得阶段性进展，原油与天然气期货盘中波动后回落。Energy desks noted lower geopolitical risk premium, though shipping insurance remains elevated. 多家研究机构提示，若谈判受阻，能源价格仍可能出现二次冲击。",
        "多家国际银行完成代币化债券结算沙盒测试，报告显示结算周期明显缩短。Banks highlighted programmability benefits for coupon distribution and collateral management. 监管方表示将继续观察系统韧性、隐私保护与跨机构互操作能力。",
        "中国多个城市出台低空经济扶持政策，涵盖无人机物流、巡检与应急应用。Local governments announced funding, airspace coordination pilots, and talent programs. 业内预计未来三年相关基础设施投资加速，但商业化回报路径仍需验证。",
        "网络安全机构发布季度报告，指出 AI 辅助钓鱼攻击在金融与零售行业上升明显。Attackers are using multilingual prompts to craft convincing social engineering messages. 企业正加快部署行为检测与员工培训，降低账号接管与数据泄露风险。",
        "全球航运指数连续反弹，制造业补库存带动部分航线运价上行。Freight brokers said container demand improved across electronics and auto components. 供应链企业仍关注港口拥堵与极端天气影响，计划通过多港分流与提前订舱来对冲不确定性。",
    ]

    now = datetime.now(UTC)
    articles: list[News] = []
    for i in range(10):
        source_name = source_names[i % len(source_names)]
        source_url = f"https://example.com/news/{i + 1}"
        title = titles[i]
        content = contents[i]
        language = "en" if i < 5 else "zh"
        published_at = now - timedelta(hours=i * 7)
        item = ParsedNewsItem(
            source_name=source_name,
            source_url=source_url,
            title=title,
            content=content,
            language=language,
            published_at=published_at,
        )
        url_hash, content_hash, title_fuzzy_hash = compute_hashes(item)
        articles.append(
            News(
                source_name=source_name,
                source_url=source_url,
                url_hash=url_hash,
                title=title,
                content=content,
                content_hash=content_hash,
                title_fuzzy_hash=title_fuzzy_hash,
                language=language,
                published_at=published_at,
                fetched_at=now,
                raw_metadata={"source": source_name, "category": "test"},
            )
        )
    return articles


async def main() -> None:
    """执行新闻种子数据写入。"""
    async with AsyncSessionLocal() as session:
        total_stmt = select(func.count()).select_from(News)
        existing_count = await session.scalar(total_stmt)
        count = int(existing_count or 0)
        if count > 0:
            print(f"已有 {count} 条数据,跳过 seeding")
            return

        session.add_all(_build_seed_payload())
        await session.commit()
        print("Seeded 10 news articles")


if __name__ == "__main__":
    asyncio.run(main())
