# 第 5 阶段 · 顺序 1
# 写在 pyproject.toml 加完依赖之后、chart.py 之前。chart.py 用这里的正则校验股票代码。

# 正则表达式模块。
import re

# 合法股票代码：1 到 10 位，只能是大写字母、数字、点、连字符。
# AAPL 是普通代码，BRK-B 带连字符，BF.B 带点。调用前要先转成大写。
TICKER_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")

# 第 7 阶段。合法用户编号：小写 UUID，或 Clerk 的 user_ 开头编号。
USER_ID_RE = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|user_[A-Za-z0-9]+)$"
)
