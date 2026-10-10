# 第 13 阶段。聊天按 IP 每分钟 10 条；其余接口按桶限制。

# 解析 IP，并把 IPv6 收到 /64。
import ipaddress
# 代理层数可以配置。
import os
# 滑动窗口用当前时间。
import time

# 过期后自动丢掉旧记录，避免内存一直涨。
from cachetools import TTLCache

# 聊天窗口长度。
WINDOW_SECONDS = 60
# 窗口内最多几条。
MAX_MESSAGES = 10
# 每个 IP 的时间戳。条目本身 60 秒后过期。
_timestamps: TTLCache = TTLCache(maxsize=10_000, ttl=WINDOW_SECONDS)
# 不同窗口长度各用一个缓存，避免短窗口把长窗口挤掉。
_rest_stores: dict[int, TTLCache] = {}
# 前面有几层可信代理。默认 1，取 X-Forwarded-For 右侧。
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))


# 允许再发一条聊天时返回 True。
def check_rate_limit(ip: str) -> bool:
    # 现在。
    now = time.time()
    # 窗口起点。
    cutoff = now - WINDOW_SECONDS
    # 丢掉窗口外的时间戳。
    recent = [stamp for stamp in _timestamps.get(ip, []) if stamp > cutoff]
    # 已经到上限。
    if len(recent) >= MAX_MESSAGES:
        # 写回裁剪后的列表，不追加。
        _timestamps[ip] = recent
        # 拒绝。
        return False
    # 记上这一次。
    recent.append(now)
    # 写回。
    _timestamps[ip] = recent
    # 允许。
    return True


# 按窗口长度取出对应缓存。
def _rest_store(window_seconds: int) -> TTLCache:
    # 已经建过。
    store = _rest_stores.get(window_seconds)
    # 没有就新建。
    if store is None:
        # 生存时间和窗口一样长。
        store = TTLCache(maxsize=10_000, ttl=window_seconds)
        # 记下来。
        _rest_stores[window_seconds] = store
    # 交给检查函数。
    return store


# 有用户编号就按人，否则按 IP。
def rate_limit_key(user_id: str | None, ip: str) -> str:
    # 登录用户。
    if user_id:
        # 前缀避免和 IP 撞键。
        return f"u:{user_id}"
    # 匿名。
    return f"ip:{ip}"


# 从请求或 WebSocket 上取出客户端 IP。
def client_ip(conn) -> str:
    # 没有可信代理时忽略转发头，防止来人自己伪造。
    forwarded = conn.headers.get("x-forwarded-for") if TRUSTED_PROXY_HOPS > 0 else None
    # 按逗号拆开，去掉空白。
    hops = [part.strip() for part in forwarded.split(",") if part.strip()] if forwarded else []
    # 有转发链时，从右边数可信代理那一跳。
    if hops:
        # 右边是代理加上的，左边是客户端可以伪造的。
        raw = hops[-min(TRUSTED_PROXY_HOPS, len(hops))]
    # 没有转发头，用连接上的地址。
    elif conn.client:
        # 直连地址。
        raw = conn.client.host
    # 两边都没有。
    else:
        # 共用一个桶。
        return "unknown"
    # 解析。
    try:
        # 标准库认 IPv4 和 IPv6。
        addr = ipaddress.ip_address(raw)
    # 垃圾字符串。
    except ValueError:
        # 不给每个垃圾值单独配额。
        return "unknown"
    # IPv4 映射在 IPv6 里时还原成 IPv4。
    if addr.version == 6 and addr.ipv4_mapped:
        # 用映射出来的地址。
        return str(addr.ipv4_mapped)
    # 纯 IPv6 收到所在的 /64，避免同一台机器换后缀刷配额。
    if addr.version == 6:
        # 网络地址。
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address)
    # IPv4 原样返回。
    return str(addr)


# 某个接口自己的配额。允许返回 True。
def check_rest_rate_limit(key: str, bucket: str, max_calls: int, window_seconds: int) -> bool:
    # 现在。
    now = time.time()
    # 这个窗口的缓存。
    store = _rest_store(window_seconds)
    # 接口名和调用者拼在一起。
    cache_key = f"{bucket}:{key}"
    # 窗口内的时间戳。
    recent = [stamp for stamp in store.get(cache_key, []) if now - stamp < window_seconds]
    # 到上限。
    if len(recent) >= max_calls:
        # 写回，不追加。
        store[cache_key] = recent
        # 拒绝。
        return False
    # 记这一次。
    recent.append(now)
    # 写回。
    store[cache_key] = recent
    # 允许。
    return True
