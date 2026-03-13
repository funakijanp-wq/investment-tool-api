# news_monitor.py - RSSフィードで要人発言モニタリング（Bパターン実装）

from __future__ import annotations
import feedparser
from dataclasses import dataclass, field
from typing import Optional

# ─── RSSフィード定義 ────────────────────────────────────────────────────────
RSS_FEEDS = {
    "FRB公式":        "https://www.federalreserve.gov/feeds/press_all.xml",
    "CNBC経済":       "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "MarketWatch":    "https://feeds.marketwatch.com/marketwatch/marketpulse/",
    "Investing.com":  "https://www.investing.com/rss/news_25.rss",
}

# ─── センチメントキーワード ─────────────────────────────────────────────────
HAWKISH_KEYWORDS = [
    "hawkish", "rate hike", "tighten", "inflation concern", "powell",
]
DOVISH_KEYWORDS = [
    "dovish", "rate cut", "pause", "easing", "soft landing",
]

# ─── スコア判定閾値 ─────────────────────────────────────────────────────────
HAWKISH_THRESHOLD =  2   # +2以上 → タカ派
DOVISH_THRESHOLD  = -2   # -2以下 → ハト派

# スコア補正値（株式スクリーニングへの加点/減点）
SENTIMENT_ADJUSTMENT = {
    "hawkish": -5,
    "dovish":  +5,
    "neutral":  0,
}


# ─── データクラス ───────────────────────────────────────────────────────────

@dataclass
class FeedResult:
    source: str
    total_entries: int = 0
    hawkish_hits: list[str] = field(default_factory=list)  # ヒットしたキーワード
    dovish_hits:  list[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class SentimentResult:
    tone: str                   # "hawkish" / "dovish" / "neutral"
    score: int                  # タカ派hits - ハト派hits
    adjustment: int             # スコア補正値
    feed_results: list[FeedResult] = field(default_factory=list)
    hawkish_total: int = 0
    dovish_total:  int = 0


# ─── メイン処理 ─────────────────────────────────────────────────────────────

def fetch_sentiment(
    feeds: dict[str, str] = RSS_FEEDS,
    max_entries: int = 20,
    verbose: bool = False,
) -> SentimentResult:
    """
    RSSフィードを取得し、要人発言のセンチメントスコアを返す。

    Args:
        feeds: {表示名: URL} の辞書
        max_entries: フィードごとに解析する最大エントリ数
        verbose: 詳細ログを標準出力に出力するか

    Returns:
        SentimentResult
    """
    feed_results = []
    hawkish_total = 0
    dovish_total  = 0

    for source, url in feeds.items():
        result = _parse_feed(source, url, max_entries, verbose)
        hawkish_total += len(result.hawkish_hits)
        dovish_total  += len(result.dovish_hits)
        feed_results.append(result)

    score = hawkish_total - dovish_total

    if   score >= HAWKISH_THRESHOLD: tone = "hawkish"
    elif score <= DOVISH_THRESHOLD:  tone = "dovish"
    else:                            tone = "neutral"

    adjustment = SENTIMENT_ADJUSTMENT[tone]

    return SentimentResult(
        tone=tone,
        score=score,
        adjustment=adjustment,
        feed_results=feed_results,
        hawkish_total=hawkish_total,
        dovish_total=dovish_total,
    )


def _parse_feed(
    source: str,
    url: str,
    max_entries: int,
    verbose: bool,
) -> FeedResult:
    """1つのRSSフィードを取得・解析してFeedResultを返す。"""
    result = FeedResult(source=source)

    try:
        feed = feedparser.parse(url)

        # feedparserはネットワーク障害でも例外を投げずにbozo=Trueにする
        if feed.bozo and not feed.entries:
            result.error = str(feed.bozo_exception)
            return result

        entries = feed.entries[:max_entries]
        result.total_entries = len(entries)

        for entry in entries:
            text = _entry_text(entry).lower()

            for kw in HAWKISH_KEYWORDS:
                if kw in text:
                    result.hawkish_hits.append(kw)
                    if verbose:
                        print(f"  [タカ派] '{kw}' in [{source}] {entry.get('title','')[:60]}")

            for kw in DOVISH_KEYWORDS:
                if kw in text:
                    result.dovish_hits.append(kw)
                    if verbose:
                        print(f"  [ハト派] '{kw}' in [{source}] {entry.get('title','')[:60]}")

    except Exception as e:
        result.error = str(e)

    return result


def _entry_text(entry) -> str:
    """エントリのタイトル・要約・本文を結合してテキストを返す。"""
    parts = [
        entry.get("title", ""),
        entry.get("summary", ""),
        entry.get("description", ""),
    ]
    # content フィールド（複数ある場合も考慮）
    for content in entry.get("content", []):
        parts.append(content.get("value", ""))
    return " ".join(parts)


# ─── 表示 ──────────────────────────────────────────────────────────────────

def print_sentiment(result: SentimentResult, verbose: bool = False) -> None:
    """センチメント結果を整形して表示。"""
    tone_jp = {"hawkish": "タカ派", "dovish": "ハト派", "neutral": "中立"}[result.tone]
    adj_str = f"+{result.adjustment}" if result.adjustment >= 0 else str(result.adjustment)

    print(f"\n現在の要人発言トーン: {tone_jp} ({result.score:+d}) → スコア{adj_str}点補正")

    if verbose:
        print(f"\n  タカ派ヒット合計: {result.hawkish_total}件")
        print(f"  ハト派ヒット合計: {result.dovish_total}件")
        print()
        for fr in result.feed_results:
            status = f"エラー: {fr.error}" if fr.error else f"{fr.total_entries}件取得"
            hawk_kws = ", ".join(fr.hawkish_hits) or "なし"
            dove_kws = ", ".join(fr.dovish_hits)  or "なし"
            print(f"  [{fr.source}] {status}")
            print(f"    タカ派: {hawk_kws}")
            print(f"    ハト派: {dove_kws}")


def get_score_adjustment(verbose: bool = False) -> int:
    """
    スクリーナー統合用のシンプルなAPI。
    補正値（-5 / 0 / +5）を返す。
    """
    result = fetch_sentiment(verbose=verbose)
    print_sentiment(result, verbose=verbose)
    return result.adjustment


# ─── 単体実行 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    print("RSSフィードを取得中...")
    result = fetch_sentiment(verbose=verbose)
    print_sentiment(result, verbose=True)
