# technical_analyzer.py - テクニカル分析（MA/RSI/MACD）
# pandas-ta の代わりに pandas で直接実装（互換性確保）

from __future__ import annotations
import yfinance as yf
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class TechnicalResult:
    ticker:  str
    signal:  str               # "buy" / "sell" / "neutral"
    rsi:     Optional[float]
    ma20:    Optional[float]
    ma50:    Optional[float]
    macd:    Optional[float]   # MACD線
    macd_signal: Optional[float]  # シグナル線
    score:   int = 50          # 0〜100 テクニカルスコア
    reason:  str = ""          # シグナル理由テキスト


# ─── メイン取得関数 ─────────────────────────────────────────────────────────

def analyze(ticker: str) -> TechnicalResult:
    """
    過去6ヶ月の日次データを取得してテクニカル指標を計算し TechnicalResult を返す。
    """
    t = yf.Ticker(ticker)
    df = t.history(period="6mo")

    if df is None or len(df) < 55:
        # データ不足（ETFや上場間もない銘柄）
        return TechnicalResult(
            ticker=ticker.upper(),
            signal="neutral",
            rsi=None, ma20=None, ma50=None,
            macd=None, macd_signal=None,
            score=50, reason="データ不足"
        )

    close = df["Close"]

    ma20 = _ma(close, 20)
    ma50 = _ma(close, 50)
    rsi  = _rsi(close, 14)
    macd_line, signal_line = _macd(close)

    result = TechnicalResult(
        ticker=ticker.upper(),
        signal="neutral",
        rsi=_last(rsi),
        ma20=_last(ma20),
        ma50=_last(ma50),
        macd=_last(macd_line),
        macd_signal=_last(signal_line),
    )

    result.signal, result.reason = _detect_signal(result, ma20, ma50)
    result.score  = _calc_score(result)
    return result


# ─── シグナル判定 ─────────────────────────────────────────────────────────

def _detect_signal(
    r: TechnicalResult,
    ma20: pd.Series,
    ma50: pd.Series,
) -> tuple[str, str]:
    """買い/売り/中立シグナルと理由テキストを返す。"""
    reasons = []
    buy_flags  = 0
    sell_flags = 0

    # MA クロス判定（直近2日で上抜け/下抜けを判定）
    ma_cross = _ma_cross(ma20, ma50)  # +1=ゴールデン, -1=デッド, 0=変化なし
    ma_above = (r.ma20 is not None and r.ma50 is not None and r.ma20 > r.ma50)

    if ma_cross == 1:
        reasons.append("ゴールデンクロス")
        buy_flags += 2
    elif ma_above:
        reasons.append("MA20>MA50")
        buy_flags += 1
    elif ma_cross == -1:
        reasons.append("デッドクロス")
        sell_flags += 2
    else:
        reasons.append("MA20<MA50")
        sell_flags += 1

    # RSI 判定
    if r.rsi is not None:
        if 30 <= r.rsi <= 55:
            reasons.append(f"RSI {r.rsi:.0f}(理想圏)")
            buy_flags += 1
        elif r.rsi > 70:
            reasons.append(f"RSI {r.rsi:.0f}(過熱)")
            sell_flags += 2
        elif r.rsi < 30:
            reasons.append(f"RSI {r.rsi:.0f}(売られ過ぎ)")
            buy_flags += 1  # 反発期待
        else:
            reasons.append(f"RSI {r.rsi:.0f}")

    # MACD 判定（補助）
    if r.macd is not None and r.macd_signal is not None:
        if r.macd > r.macd_signal:
            reasons.append("MACD↑")
            buy_flags += 1
        else:
            reasons.append("MACD↓")
            sell_flags += 1

    reason_str = " / ".join(reasons)

    # 買いシグナル: MA20がMA50を上抜け かつ RSI 30〜55
    if ma_above and r.rsi is not None and 30 <= r.rsi <= 55:
        return "buy", reason_str
    # 売りシグナル: MA20がMA50を下抜け または RSI 70超
    if (not ma_above) or (r.rsi is not None and r.rsi > 70):
        return "sell", reason_str

    return "neutral", reason_str


# ─── テクニカルスコア計算（0〜100） ──────────────────────────────────────

def _calc_score(r: TechnicalResult) -> int:
    """
    MA(40点) + RSI(40点) + MACD(20点) の合計。
    """
    score = 0

    # MA スコア
    if r.ma20 is not None and r.ma50 is not None:
        ratio = r.ma20 / r.ma50
        if   ratio >= 1.05: score += 40
        elif ratio >= 1.01: score += 30
        elif ratio >= 0.99: score += 20
        else:               score += 0

    # RSI スコア
    if r.rsi is not None:
        if   30 <= r.rsi <= 55: score += 40   # 理想圏
        elif 55 <  r.rsi <= 65: score += 25   # やや過熱
        elif 20 <= r.rsi <  30: score += 25   # 売られ過ぎ（反発期待）
        elif 65 <  r.rsi <= 70: score += 10
        else:                   score += 0    # <20 or >70

    # MACD スコア
    if r.macd is not None and r.macd_signal is not None:
        if r.macd > r.macd_signal and r.macd > 0:
            score += 20
        elif r.macd > r.macd_signal:
            score += 10
        else:
            score += 0

    return min(100, max(0, score))


# ─── 指標計算ヘルパー ─────────────────────────────────────────────────────

def _ma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(window=period).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _macd(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    ema12  = series.ewm(span=12, adjust=False).mean()
    ema26  = series.ewm(span=26, adjust=False).mean()
    macd   = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def _ma_cross(ma_fast: pd.Series, ma_slow: pd.Series) -> int:
    """
    直近2日で ma_fast が ma_slow を上抜けたら +1、下抜けたら -1、変化なし 0。
    """
    f = ma_fast.dropna()
    s = ma_slow.dropna()
    common = f.index.intersection(s.index)
    if len(common) < 2:
        return 0
    prev_above = f[common[-2]] > s[common[-2]]
    curr_above = f[common[-1]] > s[common[-1]]
    if not prev_above and curr_above:
        return 1   # ゴールデンクロス
    if prev_above and not curr_above:
        return -1  # デッドクロス
    return 0


def _last(series: Optional[pd.Series]) -> Optional[float]:
    if series is None:
        return None
    val = series.dropna()
    return float(val.iloc[-1]) if len(val) > 0 else None


# ─── 表示ヘルパー ─────────────────────────────────────────────────────────

SIGNAL_JP = {"buy": "買い", "sell": "売り", "neutral": "中立"}

def signal_label(r: TechnicalResult) -> str:
    return f"{SIGNAL_JP[r.signal]}（RSI {r.rsi:.0f} / {r.reason}）" if r.rsi else r.signal


# ─── 単体テスト ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["AAPL", "NVDA", "VTI"]
    for t in tickers:
        r = analyze(t)
        print(f"\n{r.ticker}")
        print(f"  シグナル : {SIGNAL_JP[r.signal]}  スコア: {r.score}")
        print(f"  MA20={r.ma20:.2f}  MA50={r.ma50:.2f}" if r.ma20 else "  MA: N/A")
        print(f"  RSI={r.rsi:.1f}" if r.rsi else "  RSI: N/A")
        print(f"  MACD={r.macd:.3f}  Signal={r.macd_signal:.3f}" if r.macd else "  MACD: N/A")
        print(f"  理由: {r.reason}")
