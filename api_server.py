#!/usr/bin/env python3
# api_server.py - Flask API サーバー（Next.js ダッシュボード向け）
# python3 api_server.py で起動、デフォルトポート 5001

from __future__ import annotations
import sys
import os
import time
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, Response
from flask_cors import CORS

# investment_tool ディレクトリ自身を sys.path に追加
sys.path.insert(0, os.path.dirname(__file__))

import config as cfg
from data_fetcher import fetch
from scorer import score as calc_fundamental, verdict
from technical_analyzer import analyze, SIGNAL_JP
from news_monitor import fetch_sentiment

# ─── Flask 初期化 ──────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # Next.js からのクロスオリジンリクエストを許可

# ─── インメモリキャッシュ（yfinance の過剰アクセスを防ぐ） ─────────────────
CACHE_TTL_SECONDS = 3600  # 1時間

_cache: dict = {
    "scores":    {"data": None, "expires_at": 0},
    "sentiment": {"data": None, "expires_at": 0},
}
_cache_lock = threading.Lock()


def _is_fresh(key: str) -> bool:
    return _cache[key]["data"] is not None and time.time() < _cache[key]["expires_at"]


def _set_cache(key: str, data: dict) -> None:
    with _cache_lock:
        _cache[key]["data"] = data
        _cache[key]["expires_at"] = time.time() + CACHE_TTL_SECONDS


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ─── データ取得ロジック ────────────────────────────────────────────────────

def _fetch_sentiment_data() -> dict:
    """ニュースセンチメントを取得してdict形式で返す。"""
    if _is_fresh("sentiment"):
        return _cache["sentiment"]["data"]

    try:
        result = fetch_sentiment()
        tone_jp = {"hawkish": "タカ派", "dovish": "ハト派", "neutral": "中立"}[result.tone]
        data = {
            "tone":       result.tone,
            "tone_jp":    tone_jp,
            "score":      result.score,
            "adjustment": result.adjustment,
            "hawkish_total": result.hawkish_total,
            "dovish_total":  result.dovish_total,
            "updated_at": _now_iso(),
            "error": None,
        }
    except Exception as e:
        data = {
            "tone": "neutral", "tone_jp": "中立",
            "score": 0, "adjustment": 0,
            "hawkish_total": 0, "dovish_total": 0,
            "updated_at": _now_iso(),
            "error": str(e),
        }

    _set_cache("sentiment", data)
    return data


def _fetch_scores_data(tickers: list[str], news_adj: int) -> dict:
    """全銘柄のスコアを取得してdict形式で返す。"""
    if _is_fresh("scores"):
        return _cache["scores"]["data"]

    items = []
    for ticker in tickers:
        try:
            stock   = fetch(ticker)
            f_detail = calc_fundamental(stock)
            tech    = analyze(ticker)

            f_score  = f_detail.total + news_adj
            combined = round(f_score * 0.6 + tech.score * 0.4)
            vd       = verdict(combined)

            items.append({
                "ticker":   ticker,
                "name":     stock.name,
                "signal":   tech.signal,
                "signal_jp": SIGNAL_JP[tech.signal],
                "verdict":  vd,
                "scores": {
                    "fundamental": f_score,
                    "technical":   tech.score,
                    "combined":    combined,
                    "geopolitical": f_detail.geopolitical,
                    "macro":        f_detail.macro,
                    "business":     f_detail.fundamental,
                    "sector":       f_detail.sector,
                },
                "indicators": {
                    "rsi":    round(tech.rsi, 1) if tech.rsi is not None else None,
                    "ma20":   round(tech.ma20, 2) if tech.ma20 is not None else None,
                    "ma50":   round(tech.ma50, 2) if tech.ma50 is not None else None,
                    "macd":   round(tech.macd, 3) if tech.macd is not None else None,
                    "signal_line": round(tech.macd_signal, 3) if tech.macd_signal is not None else None,
                },
                "fundamentals": {
                    "per":            round(stock.per, 1) if stock.per is not None else None,
                    "pbr":            round(stock.pbr, 2) if stock.pbr is not None else None,
                    "eps_growth":     round(stock.eps_growth, 1) if stock.eps_growth is not None else None,
                    "revenue_growth": round(stock.revenue_growth, 1) if stock.revenue_growth is not None else None,
                    "equity_ratio":   round(stock.equity_ratio, 1) if stock.equity_ratio is not None else None,
                    "dividend_yield": round(stock.dividend_yield, 2) if stock.dividend_yield is not None else None,
                    "is_etf":         stock.is_etf,
                    "expense_ratio":  stock.expense_ratio,
                },
                "meta": {
                    "country": stock.country,
                    "sector":  stock.sector,
                    "tech_reason": tech.reason,
                },
            })
        except Exception as e:
            items.append({
                "ticker": ticker, "name": ticker,
                "signal": "neutral", "signal_jp": "中立",
                "verdict": "❌ エラー",
                "scores": {"fundamental": 0, "technical": 0, "combined": 0,
                           "geopolitical": 0, "macro": 0, "business": 0, "sector": 0},
                "indicators": {},
                "fundamentals": {"is_etf": False},
                "meta": {"country": "", "sector": "", "tech_reason": str(e)},
            })
        finally:
            time.sleep(2)  # レートリミット対策

    # 総合スコア降順ソート
    items.sort(key=lambda x: x["scores"]["combined"], reverse=True)

    data = {
        "tickers":       items,
        "news_adjustment": news_adj,
        "updated_at":    _now_iso(),
        "cache_ttl":     CACHE_TTL_SECONDS,
    }
    _set_cache("scores", data)
    return data


# ─── エンドポイント ────────────────────────────────────────────────────────

@app.route("/api/sentiment")
def api_sentiment() -> Response:
    """
    GET /api/sentiment
    相場トーン（ハト派/タカ派/中立）とスコア補正値を返す。
    """
    data = _fetch_sentiment_data()
    return jsonify(data)


@app.route("/api/scores")
def api_scores() -> Response:
    """
    GET /api/scores
    全銘柄のファンダメンタル・テクニカル・統合スコアを返す。
    ニュース補正はキャッシュ済みのセンチメントを優先使用。
    """
    sent = _fetch_sentiment_data()
    news_adj = sent.get("adjustment", 0)
    data = _fetch_scores_data(cfg.DEFAULT_TICKERS, news_adj)
    return jsonify(data)


@app.route("/api/scores/refresh")
def api_scores_refresh() -> Response:
    """
    GET /api/scores/refresh
    キャッシュを強制クリアして再取得。
    """
    with _cache_lock:
        _cache["scores"]["expires_at"] = 0
        _cache["sentiment"]["expires_at"] = 0
    return jsonify({"status": "cache cleared", "updated_at": _now_iso()})


@app.route("/api/health")
def api_health() -> Response:
    """GET /api/health  ヘルスチェック用。"""
    return jsonify({
        "status": "ok",
        "tickers": cfg.DEFAULT_TICKERS,
        "cache_ttl": CACHE_TTL_SECONDS,
        "scores_cached":    _is_fresh("scores"),
        "sentiment_cached": _is_fresh("sentiment"),
        "updated_at": _now_iso(),
    })


@app.route("/")
def index() -> Response:
    return jsonify({
        "name": "Investment Tool API",
        "version": "2.0",
        "endpoints": [
            "GET /api/health",
            "GET /api/sentiment",
            "GET /api/scores",
            "GET /api/scores/refresh",
        ],
    })


# ─── 起動 ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"\n  Investment Tool API サーバー起動")
    print(f"  http://localhost:{port}")
    print(f"  銘柄: {cfg.DEFAULT_TICKERS}")
    print(f"  キャッシュTTL: {CACHE_TTL_SECONDS}秒")
    print(f"\n  エンドポイント:")
    print(f"    GET /api/health")
    print(f"    GET /api/sentiment")
    print(f"    GET /api/scores")
    print(f"    GET /api/scores/refresh")
    print(f"\n  停止: Ctrl+C\n")
    app.run(host="0.0.0.0", port=port, debug=False)
