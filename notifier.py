# notifier.py - Discord Webhook 通知

from __future__ import annotations
import os
import requests
from dotenv import load_dotenv
from dataclasses import dataclass
from typing import Optional

from technical_analyzer import TechnicalResult, SIGNAL_JP, signal_label
from news_monitor import SentimentResult

# .env 読み込み（investment_tool/.env を優先）
_env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_env_path)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")


@dataclass
class AlertItem:
    ticker:          str
    name:            str
    fundamental_score: int
    technical:       TechnicalResult
    combined_score:  int
    verdict:         str


def send_alerts(
    alerts: list[AlertItem],
    sentiment: Optional[SentimentResult] = None,
) -> bool:
    """
    買いシグナル銘柄リストを Discord に送信する。
    送信成功なら True、スキップ/失敗なら False を返す。
    """
    if not DISCORD_WEBHOOK_URL:
        print("  [DISCORD] DISCORD_WEBHOOK_URL 未設定 → 通知スキップ")
        return False

    if not alerts:
        print("  [DISCORD] 通知対象銘柄なし → スキップ")
        return False

    message = _build_message(alerts, sentiment)
    return _post(message)


def _build_message(
    alerts: list[AlertItem],
    sentiment: Optional[SentimentResult],
) -> str:
    lines = ["🚨 **投資シグナル alert**"]

    for item in alerts:
        tech = item.technical
        lines.append("─────────────────")
        lines.append(f"【買いシグナル】**{item.ticker}**  {item.name}")
        lines.append(f"ファンダメンタル: {item.fundamental_score}点")
        lines.append(f"テクニカル: {signal_label(tech)}  (スコア {tech.score})")
        lines.append(f"総合判定: {item.verdict}  ({item.combined_score}点)")

    lines.append("─────────────────")

    if sentiment is not None:
        tone_jp = {"hawkish": "タカ派", "dovish": "ハト派", "neutral": "中立"}[sentiment.tone]
        adj = sentiment.adjustment
        adj_str = f"+{adj}" if adj > 0 else str(adj)
        lines.append(f"相場トーン: {tone_jp}（{adj_str}補正中）")
    else:
        lines.append("相場トーン: 取得不可")

    return "\n".join(lines)


def _post(message: str) -> bool:
    """Discord Webhook に POST 送信。"""
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=10,
        )
        if resp.status_code in (200, 204):
            print(f"  [DISCORD] 送信成功 (status={resp.status_code})")
            return True
        else:
            print(f"  [DISCORD] 送信失敗: HTTP {resp.status_code} {resp.text[:100]}")
            return False
    except requests.RequestException as e:
        print(f"  [DISCORD] 送信エラー: {e}")
        return False


def preview(alerts: list[AlertItem], sentiment: Optional[SentimentResult] = None) -> None:
    """送信せずにメッセージ内容をターミナルに表示（デバッグ用）。"""
    print("\n" + "=" * 50)
    print("  [Discord プレビュー]")
    print("=" * 50)
    print(_build_message(alerts, sentiment))
    print("=" * 50)
