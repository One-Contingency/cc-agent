# 第 13 阶段。同时进行的模型调用最多 8 个；操作员付费时每人每天最多 100 次。

# 信号量。
import asyncio
# 饱和时记一条日志。
import logging
# 两个上限都可以用环境变量改。
import os
# 把信号量包成 async with。
from contextlib import asynccontextmanager

# 次数写在 user_llm_usage.date 上。
from api.db import increment_llm_usage

# 本文件的日志。
logger = logging.getLogger(__name__)
# 同时最多几个。
LLM_DISPATCH_CONCURRENCY = int(os.getenv("LLM_DISPATCH_CONCURRENCY", "8"))
# 排不上队时最多等几秒。
LLM_DISPATCH_WAIT_SECONDS = float(os.getenv("LLM_DISPATCH_WAIT_SECONDS", "30"))
# 每人每天几次。只对操作员自己的密钥计数。
LLM_DAILY_BUDGET = int(os.getenv("LLM_DAILY_BUDGET", "100"))
# 进程级信号量。聊天整段流不要再套一层，否则和这里死锁。
_semaphore = asyncio.Semaphore(LLM_DISPATCH_CONCURRENCY)


# 等了 30 秒还没有空位。
class LLMConcurrencyExceeded(RuntimeError):
    # 路由把它变成 503 或一条错误事件。
    pass


# 当天次数用完。
class LLMBudgetExceeded(RuntimeError):
    # 记住上限，方便返回给页面。
    def __init__(self, limit: int) -> None:
        # 留给调用方。
        self.limit = limit
        # 异常文字。
        super().__init__(f"Daily LLM budget of {limit} exceeded")


# 占一个名额。财报和早报用它，聊天的整段 stream 不用。
@asynccontextmanager
async def llm_slot():
    # 排队。
    try:
        # 超时就失败，不无限等。
        await asyncio.wait_for(_semaphore.acquire(), timeout=LLM_DISPATCH_WAIT_SECONDS)
    # 等到超时。
    except asyncio.TimeoutError as exc:
        # 记下容量。
        logger.warning("LLM dispatch pool saturated cap=%s", LLM_DISPATCH_CONCURRENCY)
        # 换成业务异常。
        raise LLMConcurrencyExceeded("LLM dispatch pool saturated") from exc
    # 占到了。
    try:
        # 把控制权交给 with 里面的代码。
        yield
    # 无论成功失败都归还名额。
    finally:
        # 放回信号量。
        _semaphore.release()


# 匿名用户不计。调用方要先确认这次用的是操作员密钥。
async def check_and_charge_budget(user_id: str | None) -> None:
    # 没有用户编号。
    if user_id is None:
        # 不计。
        return
    # 先加再判断，避免两个人同时读到同一个旧数字。
    count = await increment_llm_usage(user_id)
    # 超过上限。越过线的这一次已经计入。
    if count > LLM_DAILY_BUDGET:
        # 拒绝后续，这一次的费用已经发生。
        raise LLMBudgetExceeded(LLM_DAILY_BUDGET)
