# 第 3 阶段 · 顺序 1
# 本阶段新建的唯一 Python 文件。写在 .env.example 定下 DB_PATH 之后。
# 写完后还要改两处旧文件：pyproject.toml 加上 aiosqlite，main.py 启动时调用 init_db()。

# 读取环境变量 DB_PATH。没配置时后面会使用默认路径。
import os
# 第 9 阶段。生成会话和消息编号。
import uuid
# 第 11 阶段。把财报分析存成 JSON 字符串。
import json
# 第 13 阶段。额度按 UTC 日期分天。
from datetime import datetime, timezone
# 用 Path 拼接路径，避免手写斜杠。
from pathlib import Path

# 异步 SQLite 驱动。建表和以后的查询都通过它。
import aiosqlite

# 数据库文件位置。
# 环境变量 DB_PATH 优先；没填时用「项目根/data/chats.db」。
# 本文件在 api/db.py：parent 是 api 目录，parent.parent 才是项目根。
DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent.parent / "data" / "chats.db"))

# 进程里只保留一条连接。还没连接过时是 None。
_db: aiosqlite.Connection | None = None


# 取出那条共用连接。第一次调用时才真正创建 chats.db。
async def get_db() -> aiosqlite.Connection:
    # 声明要修改的是文件顶部那个 _db，不是函数内部的新变量。
    global _db
    # 已经连接过就跳过下面的创建过程。
    if _db is None:
        # data 目录不存在就创建。parents=True 连父目录一起建，exist_ok 表示已存在不算错。
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        # 打开数据库文件。文件不存在时，这一行会创建 data/chats.db。
        _db = await aiosqlite.connect(DB_PATH)
        # 查询结果可以用列名取值，例如 row["ticker"]，不用记第几列。
        _db.row_factory = aiosqlite.Row
        # WAL 让读取和写入可以同时进行，避免一个人写的时候其他人全部卡住。
        await _db.execute("PRAGMA journal_mode=WAL")
        # 写锁被占用时，最多再等 5000 毫秒，而不是立刻报错。
        await _db.execute("PRAGMA busy_timeout=5000")
    # 把连接交给调用方。init_db 和以后的查询函数都从这里拿。
    return _db


# 启动时建表。表已经存在就什么都不改，所以可以每次启动都调用。
async def init_db() -> None:
    # 先拿到连接。这里会顺便把 chats.db 创建出来。
    db = await get_db()

    # 公司表。ticker 是中心，后面多张表都引用它，所以第一张建。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            ticker TEXT PRIMARY KEY,              -- 股票代码，主键
            name TEXT,                            -- 公司名称，可以后补
            sector TEXT,                          -- 所属行业，可以后补
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 第一次写入的时间，数据库自动填
        )
    """)

    # 某个用户打开过哪些公司。同一用户对同一只股票只保留一行。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_companies (
            user_id TEXT NOT NULL,                -- 用户编号
            ticker TEXT NOT NULL,                 -- 股票代码
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 最近一次查看时间
            PRIMARY KEY (user_id, ticker),        -- 两个字段合在一起才是主键
            FOREIGN KEY (ticker) REFERENCES companies(ticker)  -- ticker 必须来自公司表
        )
    """)

    # 一次聊天会话。model 表示这次会话用的模型。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,                  -- 会话编号
            ticker TEXT NOT NULL,                 -- 这次聊天讨论的股票
            summary TEXT,                        -- 对话太长时压缩出来的摘要，一开始为空
            user_id TEXT,                        -- 会话属于哪个用户
            model TEXT,                          -- 使用的模型编号
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 会话创建时间
        )
    """)

    # 会话里的每一条消息。session_id 指向 sessions.id。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,                  -- 消息编号
            session_id TEXT NOT NULL,             -- 属于哪一次会话
            role TEXT NOT NULL,                   -- user 或 assistant
            content TEXT NOT NULL,                -- 消息正文
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 写入时间
            FOREIGN KEY (session_id) REFERENCES sessions(id)  -- 必须对应一条已有会话
        )
    """)

    # 自选股。同一个用户不能把同一只股票加两次。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            user_id TEXT NOT NULL,                -- 用户编号
            ticker TEXT NOT NULL,                 -- 股票代码
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 加入自选的时间
            PRIMARY KEY (user_id, ticker)         -- 用户加股票，合起来唯一
        )
    """)

    # 一份早报的总览：市场状态、仓位建议、警报原文。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS briefings (
            id TEXT PRIMARY KEY,                  -- 早报编号
            market_regime TEXT NOT NULL,          -- 市场状态
            market_positioning TEXT NOT NULL,     -- 仓位建议
            alerts TEXT NOT NULL,                 -- 警报内容
            thinking TEXT,                        -- 模型的思考过程，可以为空
            raw_json TEXT NOT NULL,               -- 模型输出的完整 JSON
            user_id TEXT,                         -- 这份早报属于哪个用户
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP  -- 生成时间
        )
    """)

    # 一份早报里每一只股票的具体判断。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS briefing_tickers (
            id TEXT PRIMARY KEY,                  -- 这一行的编号
            briefing_id TEXT NOT NULL,            -- 属于哪一份早报
            ticker TEXT NOT NULL,                 -- 股票代码
            price REAL NOT NULL,                  -- 生成早报时的价格
            change_pct REAL NOT NULL,             -- 当时的涨跌幅
            technical_signal TEXT NOT NULL,       -- 技术面信号的一句话
            news_summary TEXT NOT NULL,           -- 新闻摘要
            news_url TEXT,                        -- 新闻链接，可以没有
            news_items_json TEXT,                 -- 多条新闻的 JSON，可以没有
            outlook TEXT NOT NULL,                -- bullish、bearish、neutral 或 mixed
            FOREIGN KEY (briefing_id) REFERENCES briefings(id),  -- 必须对应一份早报
            FOREIGN KEY (ticker) REFERENCES companies(ticker)    -- 必须对应一家公司
        )
    """)

    # 财报文件本身的信息：哪一天交的、编号是什么。分析正文不放这里。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS filings_cache (
            id TEXT PRIMARY KEY,                  -- 这条缓存的编号
            ticker TEXT NOT NULL,                 -- 股票代码
            form_type TEXT NOT NULL,              -- 10-K、10-Q 或 8-K
            filing_date TEXT NOT NULL,            -- 提交日期
            period_of_report TEXT,                -- 报告覆盖的会计期间
            accession_number TEXT,                -- SEC 给这份文件的唯一编号
            filing_url TEXT,                      -- 原文链接
            downloaded_at TIMESTAMP,              -- 下载完成的时间，还没下载就是空
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 这条记录写入的时间
            FOREIGN KEY (ticker) REFERENCES companies(ticker)
        )
    """)

    # 模型对某一份财报、某一种章节的分析。同一份文件的同一种分析只留一行。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS filing_analyses (
            id TEXT PRIMARY KEY,                  -- 分析结果编号
            ticker TEXT NOT NULL,                 -- 股票代码
            form_type TEXT NOT NULL,              -- 表格类型
            accession_number TEXT NOT NULL,       -- 对应哪一份 SEC 文件
            analysis_type TEXT NOT NULL,          -- 风险因素、MD&A、资产负债表等
            analysis_json TEXT NOT NULL,          -- 模型生成的分析 JSON
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (ticker) REFERENCES companies(ticker),
            UNIQUE (ticker, form_type, accession_number, analysis_type)  -- 这四列合起来不能重复
        )
    """)

    # 每个用户每天调用了多少次模型。第 13 步的额度检查才用它，表现在建好。
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_llm_usage (
            user_id TEXT NOT NULL,                -- 用户编号
            date TEXT NOT NULL,                   -- 日期，格式按写入时的约定
            count INTEGER NOT NULL DEFAULT 0,     -- 当天已用次数，新建时是 0
            PRIMARY KEY (user_id, date)           -- 一个用户一天只有一行
        )
    """)

    # 一次执行多条建索引语句。索引用来加快后面按用户、股票、会话查询的速度。
    await db.executescript("""
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_companies_user ON user_companies(user_id);
        CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
        CREATE INDEX IF NOT EXISTS idx_briefings_created ON briefings(created_at);
        CREATE INDEX IF NOT EXISTS idx_briefings_user ON briefings(user_id);
        CREATE INDEX IF NOT EXISTS idx_briefing_tickers_ticker ON briefing_tickers(ticker);
        CREATE INDEX IF NOT EXISTS idx_briefing_tickers_briefing ON briefing_tickers(briefing_id);
        CREATE INDEX IF NOT EXISTS idx_filings_cache_ticker ON filings_cache(ticker);
        CREATE INDEX IF NOT EXISTS idx_filings_cache_form ON filings_cache(ticker, form_type);
        CREATE INDEX IF NOT EXISTS idx_filing_analyses_lookup
            ON filing_analyses(ticker, form_type, accession_number);
    """)

    # 把上面所有建表、建索引真正写进 chats.db。不 commit，重启后这些表可能不在。
    await db.commit()


# 进程退出时关闭连接，避免文件一直被占用。
async def close_db() -> None:
    # 同样修改文件顶部的 _db。
    global _db
    # 只有曾经连接过才需要关闭。
    if _db is not None:
        # 断开 SQLite。
        await _db.close()
        # 设回空，下次 get_db 会重新连接。
        _db = None


# 第 9 阶段。同一用户、同一只股票已有会话就返回它，否则新建。
async def get_or_create_session(ticker: str, user_id: str, model: str | None = None) -> str:
    # 拿到共用连接。
    db = await get_db()
    # 代码统一大写。
    ticker = ticker.upper()
    # 查现有会话。
    async with db.execute(
        # 只取编号。
        "SELECT id FROM sessions WHERE ticker = ? AND user_id = ?",
        # 股票和用户。
        (ticker, user_id),
    ) as cursor:
        # 一行或没有。
        row = await cursor.fetchone()
        # 已经聊过就继续用原来的会话。
        if row:
            # 返回已有编号。
            return row["id"]
    # 新会话编号。
    session_id = str(uuid.uuid4())
    # 公司表里先有这只股票。
    await db.execute("INSERT OR IGNORE INTO companies (ticker) VALUES (?)", (ticker,))
    # 记下这个用户看过它。
    await db.execute(
        # 重复插入会被忽略。
        "INSERT OR IGNORE INTO user_companies (user_id, ticker) VALUES (?, ?)",
        # 用户和股票。
        (user_id, ticker),
    )
    # 写入会话。
    await db.execute(
        # 编号、股票、用户、模型。
        "INSERT INTO sessions (id, ticker, user_id, model) VALUES (?, ?, ?, ?)",
        # 这一行的值。
        (session_id, ticker, user_id, model),
    )
    # 落盘。
    await db.commit()
    # 交给聊天接口。
    return session_id


# 第 9 阶段。按编号取会话，用来核对是不是这个用户的。
async def get_session(session_id: str) -> dict | None:
    # 打开连接。
    db = await get_db()
    # 按主键查。
    async with db.execute(
        # 归属核对要用 ticker 和 user_id。
        "SELECT id, ticker, summary, user_id, model, created_at FROM sessions WHERE id = ?",
        # 会话编号。
        (session_id,),
    ) as cursor:
        # 取出一行。
        row = await cursor.fetchone()
        # 没有这条会话。
        if row is None:
            # 调用方当成找不到。
            return None
        # 转成字典。
        return {
            # 编号。
            "id": row["id"],
            # 股票。
            "ticker": row["ticker"],
            # 压缩摘要，一开始是空的。
            "summary": row["summary"],
            # 主人。
            "user_id": row["user_id"],
            # 模型。
            "model": row["model"],
            # 创建时间。
            "created_at": row["created_at"],
        }


# 第 9 阶段。按股票和用户找现有会话。
async def get_session_by_ticker(ticker: str, user_id: str) -> dict | None:
    # 打开连接。
    db = await get_db()
    # 查这一对。
    async with db.execute(
        # 历史页用来判断要不要续上旧对话。
        "SELECT id, ticker, user_id, model, created_at FROM sessions WHERE ticker = ? AND user_id = ?",
        # 代码转大写。
        (ticker.upper(), user_id),
    ) as cursor:
        # 一行或没有。
        row = await cursor.fetchone()
        # 没有会话。
        if row is None:
            # 接口会返回 null。
            return None
        # 转成字典。
        return {
            # 编号。
            "id": row["id"],
            # 股票。
            "ticker": row["ticker"],
            # 用户。
            "user_id": row["user_id"],
            # 模型。
            "model": row["model"],
            # 创建时间。
            "created_at": row["created_at"],
        }


# 第 9 阶段。存一条用户或助手的话。
async def save_message(session_id: str, role: str, content: str) -> str:
    # 消息编号。
    message_id = str(uuid.uuid4())
    # 打开连接。
    db = await get_db()
    # 插入。
    await db.execute(
        # role 是 user 或 assistant。
        "INSERT INTO messages (id, session_id, role, content) VALUES (?, ?, ?, ?)",
        # 四个值。
        (message_id, session_id, role, content),
    )
    # 落盘。
    await db.commit()
    # 返回编号。
    return message_id


# 第 9 阶段。按时间取出一条会话的全部消息。
async def get_session_messages(session_id: str) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 从早到晚。
    async with db.execute(
        # 续聊按这个顺序重放。
        "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at",
        # 会话编号。
        (session_id,),
    ) as cursor:
        # 全部行。
        rows = await cursor.fetchall()
        # 转成字典列表。
        return [
            # 角色、正文、时间。
            {"role": row["role"], "content": row["content"], "created_at": row["created_at"]}
            # 逐行。
            for row in rows
        ]


# 第 9 阶段。历史页：这个用户接触过的股票。
async def get_tickers(user_id: str, limit: int = 50) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 从看过的公司出发，左连接会话。
    async with db.execute(
        # 会话条数和最近活动时间。
        """
        SELECT c.ticker,
               COUNT(s.id) AS session_count,
               COALESCE(MAX(s.created_at), uc.viewed_at, c.added_at) AS last_active
        FROM user_companies uc
        JOIN companies c ON c.ticker = uc.ticker
        LEFT JOIN sessions s ON s.ticker = c.ticker AND s.user_id = ?
        WHERE uc.user_id = ?
        GROUP BY c.ticker
        ORDER BY last_active DESC
        LIMIT ?
        """,
        # 两次用户编号，再加条数上限。
        (user_id, user_id, limit),
    ) as cursor:
        # 全部股票。
        rows = await cursor.fetchall()
        # 三个字段。
        return [
            # 代码、会话数、最近时间。
            {"ticker": row["ticker"], "session_count": row["session_count"], "last_active": row["last_active"]}
            # 逐行。
            for row in rows
        ]


# 第 9 阶段。某只股票下的会话。
async def get_sessions_for_ticker(ticker: str, user_id: str, limit: int = 50) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 只查这个用户。
    async with db.execute(
        # 新的在前。
        "SELECT id, ticker, model, created_at FROM sessions WHERE ticker = ? AND user_id = ? ORDER BY created_at DESC LIMIT ?",
        # 代码、用户、上限。
        (ticker.upper(), user_id, limit),
    ) as cursor:
        # 全部会话。
        rows = await cursor.fetchall()
        # 转成字典。
        return [
            # 编号、股票、模型、时间。
            {"id": row["id"], "ticker": row["ticker"], "model": row["model"], "created_at": row["created_at"]}
            # 逐行。
            for row in rows
        ]


# 第 9 阶段。先删消息，再删会话。
async def delete_session(session_id: str) -> bool:
    # 打开连接。
    db = await get_db()
    # 消息引用会话，所以先删消息。
    await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    # 再删会话。
    cursor = await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    # 落盘。
    await db.commit()
    # 删到一行才算成功。
    return cursor.rowcount > 0


# 第 11 阶段。读出名称和行业。
async def get_company(ticker: str) -> dict | None:
    # 打开连接。
    db = await get_db()
    # 按代码查。
    async with db.execute(
        # 补全名称时读这两列。
        "SELECT ticker, name, sector FROM companies WHERE ticker = ?",
        # 大写。
        (ticker.upper(),),
    ) as cursor:
        # 一行或没有。
        row = await cursor.fetchone()
        # 还没跟踪过。
        if row is None:
            # 跳过补全。
            return None
        # 转成字典。
        return {"ticker": row["ticker"], "name": row["name"], "sector": row["sector"]}


# 第 11 阶段。写回雅虎查到的名称和行业。
async def update_company(ticker: str, name: str | None, sector: str | None) -> None:
    # 打开连接。
    db = await get_db()
    # 只更新这两列。
    await db.execute(
        # 按代码定位。
        "UPDATE companies SET name = ?, sector = ? WHERE ticker = ?",
        # 新值和代码。
        (name, sector, ticker.upper()),
    )
    # 落盘。
    await db.commit()


# 第 11 阶段。保证公司表里有这只股票。
async def ensure_company(ticker: str) -> None:
    # 打开连接。
    db = await get_db()
    # 没有就插入，已有就忽略。
    await db.execute("INSERT OR IGNORE INTO companies (ticker) VALUES (?)", (ticker.upper(),))
    # 落盘。
    await db.commit()


# 第 11 阶段。记下这个用户看过这只股票。
async def track_company_view(ticker: str, user_id: str) -> None:
    # 先保证公司行存在。
    await ensure_company(ticker)
    # 打开连接。
    db = await get_db()
    # 插入或更新查看时间。
    await db.execute(
        # 冲突时刷新 viewed_at。
        "INSERT INTO user_companies (user_id, ticker, viewed_at) VALUES (?, ?, CURRENT_TIMESTAMP) ON CONFLICT(user_id, ticker) DO UPDATE SET viewed_at = CURRENT_TIMESTAMP",
        # 用户和股票。
        (user_id, ticker.upper()),
    )
    # 落盘。
    await db.commit()


# 第 11 阶段。按 accession 读取已经生成的分析。
async def get_filing_analysis(ticker: str, form_type: str, accession_number: str, analysis_type: str) -> dict | None:
    # 打开连接。
    db = await get_db()
    # 四列一起才是一份缓存。
    async with db.execute(
        # 取出当时存下的 JSON。
        "SELECT analysis_json FROM filing_analyses WHERE ticker = ? AND form_type = ? AND accession_number = ? AND analysis_type = ?",
        # 股票、表格、文件编号、分析类型。
        (ticker.upper(), form_type, accession_number, analysis_type),
    ) as cursor:
        # 一行或没有。
        row = await cursor.fetchone()
        # 未命中。
        if row is None:
            # 路由会去调用模型。
            return None
        # 库存的是字符串，转回字典。
        return json.loads(row["analysis_json"])


# 第 11 阶段。同一份文件再分析一次就覆盖旧结果。
async def save_filing_analysis(ticker: str, form_type: str, accession_number: str, analysis_type: str, analysis_json: str) -> None:
    # 打开连接。
    db = await get_db()
    # 公司表先有这只股票。
    await db.execute("INSERT OR IGNORE INTO companies (ticker) VALUES (?)", (ticker.upper(),))
    # 覆盖同一把缓存键。
    await db.execute(
        # 新编号加五列内容。
        "INSERT OR REPLACE INTO filing_analyses (id, ticker, form_type, accession_number, analysis_type, analysis_json) VALUES (?, ?, ?, ?, ?, ?)",
        # 编号用新的 UUID。
        (str(uuid.uuid4()), ticker.upper(), form_type, accession_number, analysis_type, analysis_json),
    )
    # 落盘。
    await db.commit()


# 第 12 阶段。加入自选。已经在里面或已经有 10 只时返回 False。
async def add_to_watchlist(ticker: str, user_id: str) -> bool:
    # 打开连接。
    db = await get_db()
    # 统一大写。
    ticker = ticker.upper()
    # 先数这个人已经有几只。
    async with db.execute(
        # 只数行数。
        "SELECT COUNT(*) AS cnt FROM watchlist WHERE user_id = ?",
        # 当前用户。
        (user_id,),
    ) as cursor:
        # 取出计数。
        row = await cursor.fetchone()
        # 到了上限不再插入。
        if row["cnt"] >= 10:
            # 路由把它变成 409。
            return False
    # 重复的代码会被主键挡住。
    cursor = await db.execute(
        # 用户和股票一起做主键。
        "INSERT OR IGNORE INTO watchlist (user_id, ticker) VALUES (?, ?)",
        # 这一对。
        (user_id, ticker),
    )
    # 公司表补一行。
    await db.execute("INSERT OR IGNORE INTO companies (ticker) VALUES (?)", (ticker,))
    # 历史页也能看见这只股票。
    await db.execute(
        # 重复忽略。
        "INSERT OR IGNORE INTO user_companies (user_id, ticker) VALUES (?, ?)",
        # 用户和代码。
        (user_id, ticker),
    )
    # 落盘。
    await db.commit()
    # 真正插入了一行才算成功。
    return cursor.rowcount > 0


# 第 12 阶段。从自选里移除。
async def remove_from_watchlist(ticker: str, user_id: str) -> bool:
    # 打开连接。
    db = await get_db()
    # 按用户和代码删除。
    cursor = await db.execute(
        # 只删这一对。
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
        # 代码转大写。
        (user_id, ticker.upper()),
    )
    # 落盘。
    await db.commit()
    # 删到一行才算成功。
    return cursor.rowcount > 0


# 第 12 阶段。自选代码列表，早报用它，不带公司名。
async def get_watchlist(user_id: str) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 按加入时间排列。
    async with db.execute(
        # 只要代码。
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
        # 当前用户。
        (user_id,),
    ) as cursor:
        # 全部行。
        rows = await cursor.fetchall()
        # 转成字典。
        return [{"ticker": row["ticker"], "added_at": row["added_at"]} for row in rows]


# 第 12 阶段。带上公司名和行业的自选列表。
async def get_watchlist_enriched(user_id: str) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 左连接公司表，名称还没补上时是空的。
    async with db.execute(
        # 自选时间、名称、行业。
        """
        SELECT w.ticker, w.added_at, c.name, c.sector
        FROM watchlist w
        LEFT JOIN companies c ON c.ticker = w.ticker
        WHERE w.user_id = ?
        ORDER BY w.added_at
        """,
        # 当前用户。
        (user_id,),
    ) as cursor:
        # 全部行。
        rows = await cursor.fetchall()
        # 转成字典。
        return [
            # 四个字段。
            {"ticker": row["ticker"], "added_at": row["added_at"], "name": row["name"], "sector": row["sector"]}
            # 逐行。
            for row in rows
        ]


# 第 12 阶段。存一份早报和里面的每只股票。
async def save_briefing(raw_json: str, market_regime: str, market_positioning: str, alerts_json: str, thinking: str | None, tickers: list[dict], user_id: str) -> str:
    # 早报编号。
    briefing_id = str(uuid.uuid4())
    # 打开连接。
    db = await get_db()
    # 写入总览。
    await db.execute(
        # 八列。
        "INSERT INTO briefings (id, market_regime, market_positioning, alerts, thinking, raw_json, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        # 这一份的值。
        (briefing_id, market_regime, market_positioning, alerts_json, thinking, raw_json, user_id),
    )
    # 每只股票一行。
    for item in tickers:
        # 公司表先有这只股票，外键才不会失败。
        await db.execute("INSERT OR IGNORE INTO companies (ticker) VALUES (?)", (item["ticker"],))
        # 写入个股判断。
        await db.execute(
            # 价格、涨跌、信号、新闻和观点。
            """
            INSERT INTO briefing_tickers
                (id, briefing_id, ticker, price, change_pct, technical_signal, news_summary, news_url, outlook)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            # 这一行。
            (
                str(uuid.uuid4()),
                briefing_id,
                item["ticker"],
                item.get("price") or 0,
                item.get("change_pct") or 0,
                item.get("technical_signal") or "",
                item.get("news_summary") or "",
                item.get("news_url"),
                item.get("outlook") or "neutral",
            ),
        )
    # 落盘。
    await db.commit()
    # 返回早报编号。
    return briefing_id


# 第 12 阶段。这个用户最近的早报。
async def get_recent_briefings(user_id: str, limit: int = 20) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 新的在前。
    async with db.execute(
        # 列表页要的字段。
        "SELECT id, market_regime, market_positioning, alerts, raw_json, created_at FROM briefings WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        # 用户和条数。
        (user_id, limit),
    ) as cursor:
        # 全部行。
        rows = await cursor.fetchall()
        # 转成字典。
        return [
            # 六个字段。
            {
                "id": row["id"],
                "market_regime": row["market_regime"],
                "market_positioning": row["market_positioning"],
                "alerts": row["alerts"],
                "raw_json": row["raw_json"],
                "created_at": row["created_at"],
            }
            # 逐行。
            for row in rows
        ]


# 第 12 阶段。某只股票在早报里出现过的记录。
async def get_briefing_history(ticker: str, user_id: str, days: int = 30) -> list[dict]:
    # 打开连接。
    db = await get_db()
    # 只取这个用户、这只股票、最近 days 天。
    async with db.execute(
        # 用日期函数限制范围。
        """
        SELECT bt.ticker, bt.price, bt.change_pct, bt.technical_signal, bt.outlook, b.created_at
        FROM briefing_tickers bt
        JOIN briefings b ON b.id = bt.briefing_id
        WHERE bt.ticker = ? AND b.user_id = ? AND b.created_at >= datetime('now', ?)
        ORDER BY b.created_at DESC
        """,
        # 天数拼进 SQLite 的修饰符。
        (ticker.upper(), user_id, f"-{int(days)} days"),
    ) as cursor:
        # 全部行。
        rows = await cursor.fetchall()
        # 转成字典。
        return [dict(row) for row in rows]


# 第 13 阶段。把较旧对话的摘要写回会话。
async def update_session_summary(session_id: str, summary: str) -> None:
    # 打开连接。
    db = await get_db()
    # 只更新摘要列。
    await db.execute("UPDATE sessions SET summary = ? WHERE id = ?", (summary, session_id))
    # 落盘。
    await db.commit()


# 第 13 阶段。今天这个用户的模型调用加 1，返回加完后的次数。
async def increment_llm_usage(user_id: str) -> int:
    # 打开连接。
    db = await get_db()
    # 按 UTC 日期分桶。
    today = datetime.now(timezone.utc).date().isoformat()
    # 没有这一行就插入 1，已有就加 1。表的主键列名是 date。
    await db.execute(
        # 冲突时走更新。
        "INSERT INTO user_llm_usage (user_id, date, count) VALUES (?, ?, 1) ON CONFLICT(user_id, date) DO UPDATE SET count = count + 1",
        # 用户和今天。
        (user_id, today),
    )
    # 落盘。
    await db.commit()
    # 读出加完后的数字。
    async with db.execute(
        # 只取次数。
        "SELECT count FROM user_llm_usage WHERE user_id = ? AND date = ?",
        # 同一行。
        (user_id, today),
    ) as cursor:
        # 刚写入的那一行。
        row = await cursor.fetchone()
        # 交给额度检查。
        return int(row["count"])


# 第 13 阶段。读取今天已经用了多少次。
async def get_llm_usage(user_id: str) -> int:
    # 打开连接。
    db = await get_db()
    # 今天的 UTC 日期。
    today = datetime.now(timezone.utc).date().isoformat()
    # 查这一行。
    async with db.execute(
        # 只取次数。
        "SELECT count FROM user_llm_usage WHERE user_id = ? AND date = ?",
        # 用户和今天。
        (user_id, today),
    ) as cursor:
        # 可能还没有行。
        row = await cursor.fetchone()
        # 没有就算 0。
        return int(row["count"]) if row else 0
