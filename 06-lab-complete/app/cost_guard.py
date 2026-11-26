"""
Cost guard (tiêu chí 8) — Theo dõi chi phí LLM trong Redis.
"""
import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _budget_key() -> str:
    return f"budget:{time.strftime('%Y-%m-%d')}"


def check_budget() -> None:
    """Kiểm tra tổng chi phí trong Redis; vượt DAILY_BUDGET_USD → HTTP 402."""
    if r is None:
        return
    try:
        spent = float(r.get(_budget_key()) or 0.0)
    except Exception:
        return

    if spent >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Cộng chi phí request vào Redis và trả về chi phí request (USD)."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is not None:
        try:
            key = _budget_key()
            r.incrbyfloat(key, cost)
            r.expire(key, 172800)
        except Exception:
            pass
    return cost
