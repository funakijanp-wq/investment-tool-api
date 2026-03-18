# data_fetcher.py - yfinanceを使った株データ取得

from __future__ import annotations
import time
import yfinance as yf
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StockData:
    ticker: str
    name: str = ""
    country: str = ""
    sector: str = ""
    industry: str = ""
    summary: str = ""

    # バリュエーション
    per: Optional[float] = None          # PER (trailingPE)
    pbr: Optional[float] = None          # PBR (priceToBook)
    dividend_yield: Optional[float] = None  # 配当利回り (%)

    # 成長性
    eps_growth: Optional[float] = None      # EPS成長率 YoY (%)
    revenue_growth: Optional[float] = None  # 売上成長率 YoY (%)

    # 財務健全性
    equity_ratio: Optional[float] = None    # 自己資本比率 (%)

    # ETF専用フィールド
    is_etf: bool = False
    expense_ratio: Optional[float] = None   # 経費率 % (例: 0.03 = 0.03%)
    etf_category: str = ""                  # yfinanceの category フィールド

    # 生データ（デバッグ用）
    raw: dict = field(default_factory=dict)


def fetch(ticker: str) -> StockData:
    """
    ティッカーシンボルから StockData を取得して返す。
    失敗時は最大3回リトライし、それでも失敗した場合は yf.download() でフォールバック。
    """
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            return _fetch_once(ticker)
        except Exception as e:
            last_exc = e
            if attempt < 2:
                wait = 10 * (attempt + 1)
                print(f"[RETRY] {ticker}: attempt {attempt+1} failed ({e}), waiting {wait}s")
                time.sleep(wait)

    # yf.download() フォールバック（価格データのみ、ファンダメンタルズは None）
    print(f"[FALLBACK] {ticker}: switching to yf.download() after 3 failures")
    return _fetch_download_fallback(ticker)


def _fetch_once(ticker: str) -> StockData:
    """yf.Ticker().info を使った通常の取得。"""
    t = yf.Ticker(ticker)
    info = t.info or {}

    # info が空 or 無効なら例外にしてリトライを促す
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None and info.get("navPrice") is None:
        symbol_type = info.get("quoteType", "")
        # ETFはnavPriceがないこともある — longNameがあれば有効とみなす
        if not info.get("longName") and not info.get("shortName"):
            raise ValueError(f"Empty or invalid info for {ticker}")

    data = StockData(ticker=ticker.upper(), raw=info)

    # ─── 基本情報 ────────────────────────────────────────────────────────
    data.name    = info.get("longName") or info.get("shortName") or ticker
    data.country = info.get("country", "")
    data.sector  = info.get("sector", "")
    data.industry = info.get("industry", "")
    data.summary = (info.get("longBusinessSummary") or "").lower()

    # ─── ETF判定 ──────────────────────────────────────────────────────
    if info.get("quoteType") == "ETF":
        data.is_etf = True
        data.etf_category = info.get("category", "")
        data.expense_ratio = _to_float(info.get("netExpenseRatio"))
        data.per = _to_float(info.get("trailingPE"))
        data.dividend_yield = _normalize_dividend_yield(info.get("dividendYield"))
        return data

    # ─── バリュエーション ──────────────────────────────────────────────
    data.per = _to_float(info.get("trailingPE"))
    data.pbr = _to_float(info.get("priceToBook"))
    data.dividend_yield = _normalize_dividend_yield(info.get("dividendYield"))

    # ─── 成長性 ───────────────────────────────────────────────────────
    eps_qoq = _to_float(info.get("earningsQuarterlyGrowth"))
    if eps_qoq is not None:
        data.eps_growth = eps_qoq * 100
    else:
        data.eps_growth = _calc_eps_growth_from_financials(t)

    rev_growth = _to_float(info.get("revenueGrowth"))
    if rev_growth is not None:
        data.revenue_growth = rev_growth * 100
    else:
        data.revenue_growth = _calc_revenue_growth_from_financials(t)

    # ─── 財務健全性 ───────────────────────────────────────────────────
    data.equity_ratio = _calc_equity_ratio(t, info)

    return data


def _fetch_download_fallback(ticker: str) -> StockData:
    """
    yf.download() を使った最小限のフォールバック。
    ファンダメンタルズは取得できないが、銘柄が0点エラーになるのを防ぐ。
    """
    df = yf.download(ticker, period="5d", auto_adjust=True, progress=False)
    data = StockData(ticker=ticker.upper())
    data.name = ticker.upper()
    if df is not None and not df.empty:
        # 最新終値を raw に格納（スコアリングでは使わないがデバッグ用）
        data.raw = {"close": safe_float(df["Close"].iloc[-1])}
    return data


# ─── 内部ヘルパー ──────────────────────────────────────────────────────────

def safe_float(value) -> Optional[float]:
    """SeriesやDataFrameから安全にfloat値を取得"""
    if value is None:
        return None
    try:
        if isinstance(value, pd.Series):
            return float(value.iloc[0]) if len(value) > 0 else None
        if isinstance(value, pd.DataFrame):
            return float(value.iloc[0, 0]) if not value.empty else None
        return float(value)
    except (TypeError, ValueError, IndexError):
        return None


def _normalize_dividend_yield(raw) -> Optional[float]:
    """dividendYield を % 表記に統一（0.40→0.40%、0.004→0.4%）。"""
    div = safe_float(raw)
    if div is None:
        return None
    return div * 100 if div < 0.1 else div


def _to_float(val) -> Optional[float]:
    return safe_float(val)


def _calc_eps_growth_from_financials(t: yf.Ticker) -> Optional[float]:
    """年次EPSをfinancials(損益計算書)から2期分取って成長率を算出。"""
    try:
        fin = t.financials  # index=指標, columns=決算期(新→旧)
        if fin is None or fin.empty:
            return None

        row_keys = ["Net Income", "Net Income Common Stockholders"]
        ni_row = None
        for k in row_keys:
            if k in fin.index:
                ni_row = fin.loc[k]
                break
        if ni_row is None or len(ni_row) < 2:
            return None

        ni_new, ni_old = safe_float(ni_row.iloc[0]), safe_float(ni_row.iloc[1])
        if ni_new is None or ni_old is None or ni_old == 0:
            return None
        return (ni_new - ni_old) / abs(ni_old) * 100
    except Exception:
        return None


def _calc_revenue_growth_from_financials(t: yf.Ticker) -> Optional[float]:
    """年次売上をfinancials(損益計算書)から2期分取って成長率を算出。"""
    try:
        fin = t.financials
        if fin is None or fin.empty:
            return None

        row_keys = ["Total Revenue", "Revenue"]
        rev_row = None
        for k in row_keys:
            if k in fin.index:
                rev_row = fin.loc[k]
                break
        if rev_row is None or len(rev_row) < 2:
            return None

        r_new, r_old = safe_float(rev_row.iloc[0]), safe_float(rev_row.iloc[1])
        if r_new is None or r_old is None or r_old == 0:
            return None
        return (r_new - r_old) / abs(r_old) * 100
    except Exception:
        return None


def _calc_equity_ratio(t: yf.Ticker, info: dict) -> Optional[float]:
    """
    自己資本比率 = 純資産 / 総資産 × 100
    balance_sheet から取得する。
    """
    try:
        bs = t.balance_sheet
        if bs is None or bs.empty:
            return None

        equity_keys = [
            "Stockholders Equity",
            "Total Stockholders Equity",
            "Common Stock Equity",
        ]
        asset_keys = ["Total Assets"]

        equity_row, asset_row = None, None
        for k in equity_keys:
            if k in bs.index:
                equity_row = bs.loc[k]
                break
        for k in asset_keys:
            if k in bs.index:
                asset_row = bs.loc[k]
                break

        if equity_row is None or asset_row is None:
            return None

        equity = safe_float(equity_row.iloc[0])
        assets = safe_float(asset_row.iloc[0])
        if equity is None or assets is None or assets == 0:
            return None
        return equity / assets * 100
    except Exception:
        return None


def fetch_multiple(tickers: list[str]) -> dict[str, StockData]:
    """複数ティッカーをまとめて取得してdict形式で返す。"""
    results = {}
    for ticker in tickers:
        try:
            results[ticker.upper()] = fetch(ticker)
        except Exception as e:
            print(f"[WARNING] {ticker}: データ取得失敗 - {e}")
    return results


def print_summary(data: StockData) -> None:
    """取得データのサマリーをデバッグ表示。"""
    print(f"\n{'='*50}")
    print(f"  {data.ticker} ({data.name})")
    print(f"  国: {data.country}  セクター: {data.sector}")
    print(f"  PER: {_fmt(data.per)}  PBR: {_fmt(data.pbr)}")
    print(f"  配当利回り: {_fmt(data.dividend_yield)}%")
    print(f"  EPS成長率: {_fmt(data.eps_growth)}%")
    print(f"  売上成長率: {_fmt(data.revenue_growth)}%")
    print(f"  自己資本比率: {_fmt(data.equity_ratio)}%")
    print(f"{'='*50}")


def _fmt(val: Optional[float], decimals: int = 1) -> str:
    return f"{val:.{decimals}f}" if val is not None else "N/A"


# ─── 単体テスト用エントリポイント ─────────────────────────────────────────
if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "NVDA"]
    for ticker in tickers:
        d = fetch(ticker)
        print_summary(d)
