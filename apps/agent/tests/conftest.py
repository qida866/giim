"""所有测试默认使用原创本地数据，不加载模型密钥。"""

import pytest
from giim_mcp.config import Settings
from giim_mcp.demo import demo_api


@pytest.fixture(scope="module")
def settings():
    with demo_api() as (url, caps):
        yield Settings(api_url=url, publisher_caps=caps)
