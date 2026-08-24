import time
from json import JSONDecodeError, dumps, loads
from urllib.error import URLError
from urllib.request import Request, urlopen

from langchain_core.tools import tool

KLINE_URL = (
    "https://indexapi.wind.com.cn/indicesWebsite/api/Kline"
    "?indexId=3fc4e92bdb75d65db3c7a7d55803bc9e&period=1Y&lan=cn"
)
TOOL_MIN_INTERVAL_SECONDS = 10.0
_LAST_TOOL_CALL_TS = 0.0


@tool
def get_wind_kline_1y() -> str:
    """获取万得全A指数近1年K线（GET接口）。内置限流，避免过于频繁请求。"""
    global _LAST_TOOL_CALL_TS

    now = time.monotonic()
    wait_seconds = TOOL_MIN_INTERVAL_SECONDS - (now - _LAST_TOOL_CALL_TS)
    if wait_seconds > 0:
        time.sleep(wait_seconds)

    req = Request(
        KLINE_URL,
        method="GET",
        headers={"User-Agent": "langgraph-demo-agent/1.0", "Accept": "application/json"},
    )
    _LAST_TOOL_CALL_TS = time.monotonic()

    try:
        with urlopen(req, timeout=10) as resp:
            payload = resp.read().decode("utf-8")
    except URLError as exc:
        return f"调用接口失败：{exc}"

    try:
        data = loads(payload)
    except JSONDecodeError:
        return f"接口返回非JSON，原始内容片段：{payload[:300]}"

    if not data.get("Success"):
        return f"接口返回失败：{dumps(data, ensure_ascii=False)[:500]}"

    rows = (data.get("Result") or {}).get("data") or []
    if not rows:
        return "接口成功但没有K线数据。"

    latest = rows[-1]
    first = rows[0]
    first_close = first.get("close")
    latest_close = latest.get("close")
    total_change = ((latest_close - first_close) / first_close) * 100 if first_close else 0.0
    chart_points = [{"date": r.get("tradeDate"), "close": r.get("close")} for r in rows if r.get("tradeDate")]
    result = {
        "index_name": latest.get("shortName", ""),
        "wind_code": latest.get("windCode", ""),
        "period": {"start": first.get("tradeDate"), "end": latest.get("tradeDate"), "count": len(rows)},
        "latest": {
            "open": latest.get("open"),
            "high": latest.get("hight"),
            "low": latest.get("low"),
            "close": latest_close,
            "pct_change": latest.get("pctChange"),
        },
        "total_change_pct": round(total_change, 4),
        "series": chart_points,
    }
    return dumps(result, ensure_ascii=False)
