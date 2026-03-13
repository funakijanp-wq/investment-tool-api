#!/usr/bin/env python3
# scheduler.py - Phase1+2 統合スキャナー
# python3 scheduler.py で即時実行

from __future__ import annotations
import sys

import config as cfg
from data_fetcher import fetch
from scorer import score as fundamental_score, verdict
from technical_analyzer import analyze, TechnicalResult, SIGNAL_JP, signal_label
from news_monitor import fetch_sentiment, print_sentiment
from notifier import AlertItem, send_alerts, preview

# ─── 統合スコア設定 ────────────────────────────────────────────────────────
FUNDAMENTAL_WEIGHT = 0.6
TECHNICAL_WEIGHT   = 0.4
ALERT_THRESHOLD    = 65   # 総合スコアがこの点以上かつ買いシグナルで通知


def run_scan(tickers: list[str], dry_run: bool = False) -> None:
    """
    全銘柄をスキャンし、条件を満たした銘柄を Discord に通知する。

    Args:
        tickers: スキャン対象ティッカーリスト
        dry_run: True の場合 Discord 送信せずにプレビューのみ
    """
    width = 55
    print("\n" + "=" * width)
    print("  Phase2 統合スキャナー 起動")
    print("=" * width)

    # ─── Step1: ニュースセンチメント ─────────────────────────────────────
    print("\n[Step1] ニュースセンチメント取得中...")
    try:
        sentiment = fetch_sentiment()
        print_sentiment(sentiment)
        news_adj = sentiment.adjustment
    except Exception as e:
        print(f"  取得失敗（補正なし）: {e}")
        sentiment = None
        news_adj = 0

    # ─── Step2: 銘柄スキャン ──────────────────────────────────────────────
    print(f"\n[Step2] {len(tickers)}銘柄スキャン中...")
    print(f"  {'Ticker':<8} {'ファンダ':>6}  {'テクニカル':>10}  {'統合':>6}  シグナル  判定")
    print(f"  {'─' * 60}")

    alerts: list[AlertItem] = []

    for ticker in tickers:
        try:
            # ファンダメンタル
            print(f"  [{ticker}] 取得中...", end="\r")
            stock_data = fetch(ticker)
            fund_detail = fundamental_score(stock_data)
            fund_score  = fund_detail.total + news_adj

            # テクニカル
            tech = analyze(ticker)

            # 統合スコア計算
            combined = round(fund_score * FUNDAMENTAL_WEIGHT + tech.score * TECHNICAL_WEIGHT)
            vd = verdict(combined)
            sig_jp = SIGNAL_JP[tech.signal]

            print(f"  {ticker:<8} {fund_score:>5}点  {tech.score:>9}点  {combined:>5}点  {sig_jp:<4}  {vd}")

            # 通知条件: 買いシグナル かつ 総合スコア >= 閾値
            if tech.signal == "buy" and combined >= ALERT_THRESHOLD:
                alerts.append(AlertItem(
                    ticker=ticker,
                    name=stock_data.name,
                    fundamental_score=fund_score,
                    technical=tech,
                    combined_score=combined,
                    verdict=vd,
                ))

        except Exception as e:
            print(f"  {ticker:<8} エラー: {e}")
            continue

    print(f"  {'─' * 60}")

    # ─── Step3: 通知 ─────────────────────────────────────────────────────
    print(f"\n[Step3] Discord 通知")
    print(f"  買いシグナル + {ALERT_THRESHOLD}点以上: {len(alerts)}銘柄")

    if alerts:
        print("  通知対象:", ", ".join(a.ticker for a in alerts))
        if dry_run:
            preview(alerts, sentiment)
        else:
            send_alerts(alerts, sentiment)
    else:
        print("  通知対象なし（条件を満たす銘柄がありません）")

    # ─── Step4: cron 案内 ────────────────────────────────────────────────
    _print_cron_guide()


def _print_cron_guide() -> None:
    script_path = __file__
    python_path = sys.executable

    print("\n" + "─" * 55)
    print("  次回自動実行：毎朝 8:00（cron 設定方法）")
    print("─" * 55)
    print("  ターミナルで以下を実行:")
    print("    crontab -e")
    print()
    print("  以下の1行を追加して保存（:wq）:")
    print(f"    0 8 * * 1-5 {python_path} {script_path}")
    print()
    print("  設定確認:")
    print("    crontab -l")
    print("─" * 55)


# ─── エントリポイント ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase2 統合スキャナー")
    parser.add_argument(
        "tickers", nargs="*",
        help="ティッカー（省略時は config.DEFAULT_TICKERS）"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Discord 送信せずにプレビューのみ表示"
    )
    args = parser.parse_args()

    tickers = [t.upper() for t in args.tickers] if args.tickers else cfg.DEFAULT_TICKERS
    run_scan(tickers, dry_run=args.dry_run)
