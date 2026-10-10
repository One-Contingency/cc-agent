# 第 11 阶段。公司概览不调用模型。财报用 SSE：进度、元数据、章节、完成、错误。
# 同一份申报的同一种分析会写入数据库，下次直接读。

# 并行和线程。
import asyncio
# SSE 正文。
import json
# 日志。
import logging
# 只允许 http 链接。
from urllib.parse import urlparse
# 概览缓存。
from cachetools import TTLCache
# 路由。
from fastapi import APIRouter, Depends, HTTPException, Request
# SSE。
from fastapi.responses import JSONResponse, StreamingResponse

# 公司行。
from api.db import ensure_company, get_filing_analysis, save_filing_analysis, track_company_view
# 密钥。
from api.dependencies import ApiKeys, get_api_keys
# 补名称。
from api.enrichment import enrich_company
# 财报分析占一个模型名额。聊天整段不占。
from api.llm_concurrency import LLMBudgetExceeded, LLMConcurrencyExceeded, check_and_charge_budget, llm_slot
# 频率。
from api.rate_limit import check_rest_rate_limit, client_ip, rate_limit_key
# 股票代码。
from api.validators import TICKER_RE
# 模型。
from agents.llm_factory import create_llm
# 清单。
from agents.model_registry import get_default_model, get_model
# 大盘。第 12 阶段的检测器。
from agents.market_analysis.regime_detector import MarketRegimeDetector
# 下载。
from agents.sec_workflow.get_SEC_data import SECDataRetrieval
# 摘要。
from agents.sec_workflow.sec_llm_models import summarize_risks
# 指标。
from agents.technical_workflow.process_technical_indicators import TechnicalIndicators
# 形态。
from agents.technical_workflow.pattern_recognition import PatternRecognitionEngine
# 行情。
from agents.technical_workflow.get_stock_data import YahooFinanceDataRetrieval

# 日志。
logger = logging.getLogger(__name__)
# 前缀是 /api/company，不是 /company。
router = APIRouter(prefix="/api/company", tags=["company"])
# 概览缓存 5 分钟。
_PROFILE_TTL = 300
# 按股票缓存。
_profile_cache: TTLCache = TTLCache(maxsize=256, ttl=_PROFILE_TTL)
# 同一只股票同时只建一次概览。
_profile_locks: dict[str, asyncio.Lock] = {}


# 取出这只股票的锁。
def _lock(ticker: str) -> asyncio.Lock:
    # 没有就建。
    if ticker not in _profile_locks:
        # 新建。
        _profile_locks[ticker] = asyncio.Lock()
    # 返回。
    return _profile_locks[ticker]


# 调用失败时用默认值，不让整份概览失败。
def _safe(fn, default):
    # 执行。
    try:
        # 结果。
        return fn()
    # 失败。
    except Exception:
        # 默认。
        return default


# 一条 SSE。
def _sse(data: dict) -> str:
    # data 行加空行。
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# 组装概览。不调用模型。
async def _build_profile(ticker: str) -> dict:
    # 下载器。
    source = YahooFinanceDataRetrieval(ticker)

    # 五个独立任务。
    def company():
        # 资料。
        return _safe(source.get_company_profile, {})

    # 现价。
    def quote():
        # 两个价格。
        return _safe(source.get_live_price, {})

    # 一年日线。
    def frame():
        # K 线。
        return _safe(lambda: source.get_historical_prices(period="1y", interval="1d"), None)

    # 大盘。
    def regime():
        # 检测。
        return _safe(lambda: MarketRegimeDetector().detect_regime(), {})

    # 并行。
    info, price, history, market = await asyncio.gather(
        # 资料。
        asyncio.to_thread(company),
        # 现价。
        asyncio.to_thread(quote),
        # K 线。
        asyncio.to_thread(frame),
        # 大盘。
        asyncio.to_thread(regime),
    )
    # 指标和形态。
    technicals: dict = {}
    # 形态列表。
    patterns: list = []
    # 有 K 线才算。
    if history is not None and not getattr(history, "empty", True):
        # 指标。
        technicals = TechnicalIndicators(ticker).calculate_all_indicators(history)
        # 形态。
        patterns = PatternRecognitionEngine().detect_all_patterns(history)
    # 网站只留 http。
    website = info.get("website") or ""
    # 判断协议。
    safe_site = website if urlparse(website).scheme in ("http", "https") else None
    # 整份。
    raw = {
        # 代码。
        "ticker": ticker,
        # 介绍。
        "company": {
            # 名称。
            "name": info.get("shortName"),
            # 行业。
            "sector": info.get("sector"),
            # 细分。
            "industry": info.get("industry"),
            # 简介。
            "summary": info.get("longBusinessSummary"),
            # 网站。
            "website": safe_site,
        },
        # 估值。
        "metrics": {
            # 市值。
            "market_cap": info.get("marketCap"),
            # 市盈率。
            "pe_ratio": info.get("trailingPE"),
            # 52 周高。
            "high_52w": info.get("fiftyTwoWeekHigh"),
            # 52 周低。
            "low_52w": info.get("fiftyTwoWeekLow"),
        },
        # 现价。
        "quote": price,
        # 指标。
        "technicals": technicals,
        # 形态。
        "patterns": patterns,
        # 大盘。
        "regime": market,
    }
    # 转成可 JSON 的普通类型。numpy 数字会在这里变成字符串或数字。
    return json.loads(json.dumps(raw, default=str))


# 概览。
@router.get("/{ticker}/profile")
async def get_company_profile(ticker: str, keys: ApiKeys = Depends(get_api_keys)):
    # 代码。
    if not TICKER_RE.match(ticker.upper()):
        # 422。
        raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    # 大写。
    ticker = ticker.upper()
    # 同一只股票加锁。
    async with _lock(ticker):
        # 缓存。
        cached = _profile_cache.get(ticker)
        # 命中。
        if cached is not None:
            # 返回缓存。
            return JSONResponse(content=cached)
        # 现算。
        payload = await _build_profile(ticker)
        # 放进缓存。
        _profile_cache[ticker] = payload
        # 有用户就记一次浏览，没有就只保证公司行存在。
        if keys.user_id:
            # 浏览。
            await track_company_view(ticker, keys.user_id)
        # 匿名。
        else:
            # 公司行。
            await ensure_company(ticker)
        # 顺手补名称。失败不管。
        try:
            # 补。
            await enrich_company(ticker)
        # 失败。
        except Exception:
            # 忽略。
            pass
    # 返回。
    return JSONResponse(content=payload)


# 财报流。
@router.get("/{ticker}/filings/stream")
async def stream_company_filings(ticker: str, request: Request, keys: ApiKeys = Depends(get_api_keys)):
    # 代码。
    if not TICKER_RE.match(ticker.upper()):
        # 422。
        raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    # 大写。
    ticker = ticker.upper()
    # 每分钟 10 次。
    if not check_rest_rate_limit(rate_limit_key(keys.user_id, client_ip(request)), "filings", 10, 60):
        # 429。
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    # 模型。
    model = get_model(keys.model_id or "") or get_default_model()
    # 没有密钥就 422。
    api_key = keys.require_provider_key(model.provider)

    # 生成器。
    async def events():
        # 开始。
        yield _sse({"type": "progress", "message": "正在下载最新 10-K"})
        # 下载放线程里。
        filing = await asyncio.to_thread(SECDataRetrieval(ticker).latest_risk_text)
        # 没原文。
        if not filing.get("text"):
            # 错误事件。
            yield _sse({"type": "error", "message": filing.get("error") or "没有财报。"})
            # 结束。
            return
        # 元数据。
        yield _sse({
            # 类型。
            "type": "metadata",
            # 表格。
            "form": filing.get("form") or "10-K",
            # 申报编号。
            "accession": filing.get("accession") or "",
            # 股票。
            "ticker": ticker,
        })
        # 缓存键的四段。
        form_type = filing.get("form") or "10-K"
        # 编号。没有编号时用 ticker，避免空字符串把不同公司写到一起。
        accession = filing.get("accession") or ticker
        # 分析种类。
        analysis_type = "risk_summary"
        # 先读缓存。
        cached = await get_filing_analysis(ticker, form_type, accession, analysis_type)
        # 命中。
        if cached and cached.get("analysis_json"):
            # 章节直接来自数据库。
            yield _sse({"type": "section", "section": analysis_type, "content": cached["analysis_json"], "cached": True})
            # 完成。
            yield _sse({"type": "complete"})
            # 结束。
            return
        # 进度。
        yield _sse({"type": "progress", "message": "正在概括风险因素"})
        # 占一个模型名额。额度用完或排队太久都变成错误事件。
        try:
            # 操作员密钥才扣额度。
            if keys.is_operator_paid(model.provider):
                # 加一。
                await check_and_charge_budget(keys.user_id)
            # 名额。
            async with llm_slot():
                # 工具模型，思考关闭。
                llm = create_llm(model.id, api_key)
                # 摘要。
                text = await summarize_risks(llm, ticker, filing["text"])
        # 排队太久。
        except LLMBudgetExceeded:
            # 额度用完。
            yield _sse({"type": "error", "message": "今天的模型次数已经用完。"})
            # 结束。
            return
        except LLMConcurrencyExceeded:
            # 错误。
            yield _sse({"type": "error", "message": "服务器正忙，请稍后再试。"})
            # 结束。
            return
        # 写入缓存。
        await save_filing_analysis(ticker, form_type, accession, analysis_type, text)
        # 章节。
        yield _sse({"type": "section", "section": analysis_type, "content": text, "cached": False})
        # 完成。
        yield _sse({"type": "complete"})

    # 不缓冲，方便页面逐条看到。
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
