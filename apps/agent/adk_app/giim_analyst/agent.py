"""只导出最终回答外壳，不暴露未验证草稿。"""

from giim_agent.adk_entry import root_agent

__all__ = ["root_agent"]
