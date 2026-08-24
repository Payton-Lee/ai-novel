import ssl
import time
from datetime import datetime, timedelta
from json import dumps, loads
from urllib.error import URLError
from urllib.request import Request, urlopen

from langchain_core.tools import tool

SSE_QUERY_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_TOOL_MIN_INTERVAL_SECONDS = 0.2
SSE_OFFICIAL_CALENDAR_END_YEAR = 2025


@tool
def get_sse_trading_days(start_date: str, end_date: str, strict_official: bool = False) -> str:
    """查询上交所交易日历。输入 YYYY-MM-DD。strict_official=true 时仅允许官宣年份。"""
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return "日期格式错误，请使用 YYYY-MM-DD。"

    if start > end:
        return "开始日期不能晚于结束日期。"

    day_span = (end - start).days + 1
    if day_span > 370:
        return "区间过大，请将查询范围控制在370天以内。"

    if strict_official and (
        start.year > SSE_OFFICIAL_CALENDAR_END_YEAR or end.year > SSE_OFFICIAL_CALENDAR_END_YEAR
    ):
        return (
            f"strict_official=true 时仅支持到 {SSE_OFFICIAL_CALENDAR_END_YEAR} 年。"
            "请改查已官宣年份，或将 strict_official 设为 false。"
        )

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.sse.com.cn/disclosure/dealinstruc/calendar/",
        "Accept": "application/json",
    }

    trading_days: list[str] = []
    current = start
    while current <= end:
        next_day = current + timedelta(days=1)
        req_url = f"{SSE_QUERY_URL}?sqlId=GW_PL_JYTS_TFPXX_TRADEDAY&bizDate={next_day.strftime('%Y%m%d')}"
        req = Request(req_url, method="GET", headers=headers)
        try:
            try:
                with urlopen(req, timeout=10) as resp:
                    payload = resp.read().decode("utf-8")
            except ssl.SSLCertVerificationError:
                insecure_ctx = ssl._create_unverified_context()
                with urlopen(req, timeout=10, context=insecure_ctx) as resp:
                    payload = resp.read().decode("utf-8")
            except URLError as url_err:
                if isinstance(getattr(url_err, "reason", None), ssl.SSLCertVerificationError):
                    insecure_ctx = ssl._create_unverified_context()
                    with urlopen(req, timeout=10, context=insecure_ctx) as resp:
                        payload = resp.read().decode("utf-8")
                else:
                    raise
            data = loads(payload)
        except Exception as exc:
            return f"查询上交所接口失败：{exc}"

        result = data.get("result") or []
        before_trade_day = result[0].get("beforeTradeDay") if result else None
        if before_trade_day == current.strftime("%Y%m%d"):
            trading_days.append(current.strftime("%Y-%m-%d"))

        current += timedelta(days=1)
        time.sleep(SSE_TOOL_MIN_INTERVAL_SECONDS)

    return dumps(
        {
            "exchange": "SSE",
            "start_date": start_date,
            "end_date": end_date,
            "strict_official": strict_official,
            "count": len(trading_days),
            "trading_days": trading_days,
        },
        ensure_ascii=False,
    )
