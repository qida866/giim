"""新闻响应模型，定义新闻列表接口的输出结构。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class NewsResponse(BaseModel):
    """新闻响应项模型。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    source_url: str
    title: str
    content: str
    language: str
    published_at: datetime

    @field_validator("content", mode="before")
    @classmethod
    def truncate_content(cls, value: object) -> str:
        """将正文截断至 200 字以内，避免列表响应过大。"""
        if not isinstance(value, str):
            return ""
        return value[:200]


class NewsListResponse(BaseModel):
    """新闻列表响应模型。"""

    items: list[NewsResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
