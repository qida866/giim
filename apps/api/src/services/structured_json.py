"""仅剥离完整单层 JSON 围栏；不修复字段或搜索混杂文本中的对象。"""


def json_payload(raw: str) -> str:
    text = raw.strip()
    lines = text.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```json", "```"}
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1])
    return text
