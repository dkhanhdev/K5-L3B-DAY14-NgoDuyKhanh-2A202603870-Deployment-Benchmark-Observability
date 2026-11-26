"""
Rate limiting (tiêu chí 7) — Sliding window 60s lưu trong Redis.
"""
import time
import uuid
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r


def check_rate_limit(key: str) -> None:
    """Giới hạn RATE_LIMIT_PER_MINUTE request / 60s cho mỗi API key."""
    if r is None:
        return

    now = time.time()
    window_start = now - 60.0
    redis_key = f"rate_limit:{key}"

    try:
        pipe = r.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zcard(redis_key)
        _, current_count = pipe.execute()

        if current_count >= settings.rate_limit_per_minute:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

        member = f"{now}:{uuid.uuid4().hex}"
        pipe_add = r.pipeline()
        pipe_add.zadd(redis_key, {member: now})
        pipe_add.expire(redis_key, 65)
        pipe_add.execute()
    except HTTPException:
        raise
    except Exception:
        # Không làm sập endpoint nếu Redis tạm thời gián đoạn
        return
