"""可审计的价格配置；默认不提供任何推测价格。"""

import json
import math
import os


def pricing() -> dict:
    data = json.loads(os.getenv("GIIM_MODEL_PRICES", "{}"))
    if not isinstance(data, dict) or len(data) > 20:
        raise ValueError("Pricing must be a mapping for at most 20 models")
    keys = {"input_per_million", "output_per_million"}
    for model, price in data.items():
        if not isinstance(model, str) or not isinstance(price, dict) or set(price) != keys:
            raise ValueError("Each model needs input_per_million and output_per_million prices")
        if any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for v in price.values()
        ):
            raise ValueError("Prices must be finite, non-negative USD values")
    return data
