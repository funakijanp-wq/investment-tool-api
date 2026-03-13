#!/usr/bin/env python3
# main.py - 株式スクリーニングツール Phase1 エントリポイント

import sys
import argparse
from data_fetcher import fetch, StockData, _fmt
from scorer import score, ScoreDetail, verdict
from news_monitor import fetch_sentiment, print_sentiment, SentimentResult
import config as cfg


def _bar(score: int, max_score: int, width: int = 10) -> str:
    """テキストプログレスバー生成。"""
    filled = round(score / max_score * width)
    return "█" * filled + "░" * (width - filled)


def _fmt_pct(val, suffix="%") -> str:
    return f"{val:+.1f}{suffix}" if val is not None else "N/A"


def display(data: StockData, detail: ScoreDetail, adjustment: int = 0) -> None:
    base  = detail.total
    total = base + adjustment
    vd = verdict(total)
    width = 47

    print("─" * width)
    print(f"  {data.ticker}  {data.name}")
    if adjustment != 0:
        sign = f"+{adjustment}" if adjustment > 0 else str(adjustment)
        print(f"  総合スコア: {total}点 ({sign}補正込み)  {vd}")
    else:
        print(f"  総合スコア: {total}点  {vd}")
    print(f"  {'─' * (width - 4)}")

    # Layer1
    g = detail.geopolitical
    print(f"  地政学  : {g:2d}/20  {_bar(g, 20)}")

    # Layer2
    m = detail.macro
    print(f"  マクロ  : {m:2d}/25  {_bar(m, 25)}")

    # Layer3
    f = detail.fundamental
    if data.is_etf:
        er_str  = f"{data.expense_ratio:.2f}%" if data.expense_ratio is not None else "N/A"
        div_str = _fmt(data.dividend_yield) + "%" if data.dividend_yield is not None else "N/A"
        cat_str = data.etf_category or "不明"
        print(f"  コスト  : {f:2d}/30  {_bar(f, 30)}")
        print(f"            経費率 {er_str} / 配当 {div_str} / カテゴリ: {cat_str}")
    else:
        eps_str = _fmt_pct(data.eps_growth)
        rev_str = _fmt_pct(data.revenue_growth)
        eq_str  = _fmt(data.equity_ratio) + "%" if data.equity_ratio is not None else "N/A"
        div_str = _fmt(data.dividend_yield) + "%" if data.dividend_yield is not None else "N/A"
        print(f"  業績    : {f:2d}/30  {_bar(f, 30)}")
        print(f"            EPS {eps_str} / 売上 {rev_str} / 自己資本 {eq_str} / 配当 {div_str}")
        print(f"            ({detail.eps_growth_score}+{detail.revenue_growth_score}"
              f"+{detail.equity_ratio_score}+{detail.dividend_score}点)")

    # Layer4
    s = detail.sector
    sector_label = data.sector or "不明"
    print(f"  セクター: {s:2d}/25  {_bar(s, 25)}  [{sector_label}]")

    print(f"  {'─' * (width - 4)}")
    print(f"  PER: {_fmt(data.per)}  PBR: {_fmt(data.pbr)}"
          f"  国: {data.country or '不明'}")
    print("─" * width)


def _print_sentiment_banner(sentiment: SentimentResult) -> None:
    """要人発言トーンのバナーを表示。"""
    width = 47
    tone_jp = {"hawkish": "タカ派", "dovish": "ハト派", "neutral": "中立"}[sentiment.tone]
    adj = sentiment.adjustment
    adj_str = f"+{adj}" if adj > 0 else str(adj)
    score_str = f"全銘柄{adj_str}点補正" if adj != 0 else "補正なし"

    print("─" * width)
    print(f"  要人発言トーン: {tone_jp}({sentiment.score:+d}) → {score_str}")
    print("─" * width)


def run(tickers: list[str], verbose: bool = False) -> None:
    print()

    # ─── ニュースセンチメント取得 ──────────────────────────────────────────
    print("  [NEWS] RSSフィード取得中...", end="\r")
    try:
        sentiment = fetch_sentiment(verbose=verbose)
        adjustment = sentiment.adjustment
    except Exception as e:
        print(f"  [NEWS] 取得失敗（補正なし）: {e}")
        sentiment = None
        adjustment = 0
    print(" " * 40, end="\r")

    # ─── 株式データ取得・採点 ──────────────────────────────────────────────
    results = []
    for ticker in tickers:
        try:
            print(f"  [{ticker}] データ取得中...", end="\r")
            data = fetch(ticker)
            detail = score(data)
            results.append((data, detail))

            if verbose:
                print(f"\n[DEBUG] {ticker} メモ:")
                for note in detail.notes:
                    print(f"    {note}")

        except Exception as e:
            print(f"  [{ticker}] エラー: {e}")
            continue

    print(" " * 40, end="\r")

    # ─── 要人発言バナー ────────────────────────────────────────────────────
    if sentiment is not None:
        _print_sentiment_banner(sentiment)
        print()

    # ─── 銘柄表示（補正込みスコア降順） ────────────────────────────────────
    results.sort(key=lambda x: x[1].total + adjustment, reverse=True)
    for data, detail in results:
        display(data, detail, adjustment)
        print()

    # ─── サマリーテーブル ──────────────────────────────────────────────────
    if len(results) > 1:
        adj_label = f"（{adjustment:+d}補正込み）" if adjustment != 0 else ""
        print(f"  ランキング{adj_label}")
        print(f"  {'Ticker':<8} {'総合':>4}  {'地政':>4}  {'マクロ':>6}  {'業績':>4}  {'セクター':>8}  判定")
        print(f"  {'─'*65}")
        for data, detail in results:
            total = detail.total + adjustment
            print(f"  {data.ticker:<8} {total:>4}点  "
                  f"{detail.geopolitical:>2}/20  "
                  f"{detail.macro:>2}/25  "
                  f"{detail.fundamental:>2}/30  "
                  f"{detail.sector:>2}/25  "
                  f"  {verdict(total)}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="株式スクリーニングツール Phase1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="例: python main.py AAPL NVDA VTI LMT XOM"
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="ティッカーシンボル（スペース区切りで複数指定可）"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="採点の詳細メモを表示"
    )
    parser.add_argument(
        "--defaults",
        action="store_true",
        help=f"デフォルト銘柄リストを使用: {cfg.DEFAULT_TICKERS}"
    )

    args = parser.parse_args()

    tickers = args.tickers
    if args.defaults or not tickers:
        tickers = cfg.DEFAULT_TICKERS
        if not args.tickers:
            print(f"ティッカー未指定のためデフォルトを使用: {tickers}")

    run([t.upper() for t in tickers], verbose=args.verbose)


if __name__ == "__main__":
    main()
