#!/usr/bin/env python3
"""生成调仓时间表（基于交易所交易日）.

规则：
1) 调仓生效日：2/5/8/11 月第二个星期五的下一个交易日
2) 初筛日：调仓生效日的上一个月的第一个交易日
3) 公告日：调仓生效日前 10 个交易日
4) 调仓计算日：调仓生效日前 1 个交易日
"""

from __future__ import annotations

import json
import ssl
import sys
import time
from datetime import date, datetime, timedelta
from urllib.error import URLError
from urllib.request import Request, urlopen

SSE_QUERY_URL = "https://query.sse.com.cn/commonSoaQuery.do"
SSE_REFERER = "https://www.sse.com.cn/disclosure/dealinstruc/calendar/"
REQUEST_INTERVAL_SECONDS = 0.2


def parse_args() -> tuple[str, str, str, str]:
    if len(sys.argv) != 5:
        raise SystemExit(
            "用法: python generate_rebalance_schedule.py <start_date> <end_date> <exchange> <output_json>\n"
            "示例: python generate_rebalance_schedule.py 2025-01-01 2025-12-31 sse rebalance_2025.json"
        )
    return sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]


def second_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    days_to_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_to_friday)
    return first_friday + timedelta(days=7)


def query_before_trade_day_for(biz_date: date, exchange: str) -> str:
    """查询某 bizDate 对应的 beforeTradeDay，返回 YYYYMMDD."""
    if exchange.lower() != "sse":
        raise ValueError(f"暂不支持交易所: {exchange}，当前仅支持 sse")

    query = f"{SSE_QUERY_URL}?sqlId=GW_PL_JYTS_TFPXX_TRADEDAY&bizDate={biz_date.strftime('%Y%m%d')}"
    req = Request(
        query,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": SSE_REFERER,
            "Accept": "application/json",
        },
    )
    try:
        try:
            with urlopen(req, timeout=10) as resp:
                payload = resp.read().decode("utf-8")
        except ssl.SSLCertVerificationError:
            with urlopen(req, timeout=10, context=ssl._create_unverified_context()) as resp:
                payload = resp.read().decode("utf-8")
        except URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                with urlopen(req, timeout=10, context=ssl._create_unverified_context()) as resp:
                    payload = resp.read().decode("utf-8")
            else:
                raise
    finally:
        time.sleep(REQUEST_INTERVAL_SECONDS)

    data = json.loads(payload)
    result = data.get("result") or []
    if not result or "beforeTradeDay" not in result[0]:
        raise RuntimeError(f"上交所接口返回异常: {payload[:300]}")
    return result[0]["beforeTradeDay"]


def is_trading_day(d: date, exchange: str) -> bool:
    """判定 d 是否交易日：若 d+1 的 beforeTradeDay == d 则 d 为交易日."""
    return query_before_trade_day_for(d + timedelta(days=1), exchange) == d.strftime("%Y%m%d")


def collect_trading_days(start: date, end: date, exchange: str) -> list[date]:
    days: list[date] = []
    cur = start
    while cur <= end:
        if is_trading_day(cur, exchange):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def next_trading_day(d: date, trading_set: set[date], end_guard: date) -> date:
    cur = d + timedelta(days=1)
    while cur <= end_guard:
        if cur in trading_set:
            return cur
        cur += timedelta(days=1)
    raise RuntimeError(f"未找到 {d} 之后的交易日")


def first_trading_day_of_month(year: int, month: int, trading_days: list[date]) -> date:
    for d in trading_days:
        if d.year == year and d.month == month:
            return d
    raise RuntimeError(f"未找到 {year}-{month:02d} 的首个交易日")


def nth_prev_trading_day(d: date, n: int, trading_days: list[date]) -> date:
    idx_map = {v: i for i, v in enumerate(trading_days)}
    if d not in idx_map:
        raise RuntimeError(f"{d} 不在交易日序列中")
    idx = idx_map[d] - n
    if idx < 0:
        raise RuntimeError(f"{d} 往前 {n} 个交易日超出数据范围")
    return trading_days[idx]


def main() -> None:
    start_date_str, end_date_str, exchange, output = parse_args()
    try:
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit("日期格式错误，请使用 YYYY-MM-DD")

    if start_date > end_date:
        raise SystemExit("开始日期不能晚于结束日期")

    rebalance_months = [2, 5, 8, 11]

    # 为“上个月首个交易日/前10交易日/下一个交易日”预留缓冲区
    fetch_start = (start_date.replace(day=1) - timedelta(days=45))
    fetch_end = end_date + timedelta(days=45)
    trading_days = collect_trading_days(fetch_start, fetch_end, exchange)
    trading_set = set(trading_days)
    year_range = range(start_date.year, end_date.year + 1)

    rows: list[dict[str, str]] = []
    for y in year_range:
        for m in rebalance_months:
            second_fri = second_friday(y, m)
            effective = next_trading_day(second_fri, trading_set, fetch_end)
            if not (start_date <= effective <= end_date):
                continue

            calc_day = nth_prev_trading_day(effective, 1, trading_days)
            announce_day = nth_prev_trading_day(effective, 10, trading_days)

            prev_month = m - 1
            prev_year = y
            if prev_month == 0:
                prev_month = 12
                prev_year = y - 1
            prescreen_day = first_trading_day_of_month(prev_year, prev_month, trading_days)

            rows.append(
                {
                    "exchange": exchange.lower(),
                    "调仓年份": str(y),
                    "调仓月份": f"{m:02d}",
                    "第二个星期五": second_fri.isoformat(),
                    "调仓生效日": effective.isoformat(),
                    "初筛日": prescreen_day.isoformat(),
                    "公告日(前10交易日)": announce_day.isoformat(),
                    "调仓计算日(前1交易日)": calc_day.isoformat(),
                }
            )

    output_payload = {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "exchange": exchange.lower(),
        "count": len(rows),
        "schedule": rows,
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(output_payload, f, ensure_ascii=False, indent=2)

    print(f"已生成: {output}，共 {len(rows)} 条调仓记录。")


if __name__ == "__main__":
    main()
