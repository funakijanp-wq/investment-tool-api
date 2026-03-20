# config.py - スクリーニングツール設定管理

# ─── レイヤーウェイト（合計100） ───────────────────────────────────────────
LAYER_WEIGHTS = {
    "geopolitical": 20,   # Layer1: 地政学リスク
    "macro":        25,   # Layer2: マクロ経済
    "fundamental":  30,   # Layer3: 企業業績
    "sector":       25,   # Layer4: セクターリスク
}

# ─── Layer1: 地政学リスク ──────────────────────────────────────────────────
# 国別リスクスコア (0=高リスク, 1.0=低リスク)
COUNTRY_RISK = {
    "United States": 1.0,
    "Japan":         0.9,
    "Germany":       0.85,
    "United Kingdom":0.85,
    "Canada":        0.9,
    "Australia":     0.85,
    "South Korea":   0.75,
    "Taiwan":        0.65,
    "India":         0.70,
    "Brazil":        0.60,
    "China":         0.30,
    "Russia":        0.10,
}
COUNTRY_RISK_DEFAULT = 0.55  # 不明な国のデフォルト

# 中国・ロシア依存企業のペナルティ (0〜1、大きいほど減点大)
CHINA_RUSSIA_PENALTY = 0.4

# ─── Layer2: マクロ経済 ────────────────────────────────────────────────────
# 現在の想定政策金利（米国10年債利回りの目安）
CURRENT_INTEREST_RATE = 4.5  # %

# PER妥当性の判定基準（金利との関係）
# 益回り（1/PER）が金利を上回っていれば割安
PER_FAIR_VALUE_MULTIPLIER = 1.0   # 益回り >= 金利×この倍率 → 満点
PER_CHEAP_THRESHOLD       = 1.2   # 益回り >= 金利×1.2 → ボーナス
PER_EXPENSIVE_THRESHOLD   = 0.6   # 益回り <= 金利×0.6 → 大幅減点

# ─── Layer3: 企業業績 ──────────────────────────────────────────────────────
FUNDAMENTAL_CRITERIA = {
    # EPS成長率 (%)
    "eps_growth": {
        "excellent": 20,   # >= 20% → 満点
        "good":      10,   # >= 10% → 高得点
        "neutral":    0,   # >= 0%  → 中程度
        "bad":       -10,  # < -10% → 減点
    },
    # 売上成長率 (%)
    "revenue_growth": {
        "excellent": 15,
        "good":       8,
        "neutral":    0,
        "bad":       -5,
    },
    # 自己資本比率 (%)
    "equity_ratio": {
        "excellent": 60,   # >= 60% → 堅固
        "good":      40,
        "neutral":   20,
        "bad":       10,   # < 10% → 危険
    },
    # PER上限（業績評価上のペナルティ閾値）
    "per_penalty_threshold": 50,  # PER > 50 → 業績スコア減点
}

# 業績サブスコアのウェイト配分（合計100）
FUNDAMENTAL_SUB_WEIGHTS = {
    "per":            30,
    "eps_growth":     30,
    "revenue_growth": 25,
    "equity_ratio":   15,
}

# ─── Layer4: セクターリスク ────────────────────────────────────────────────
# セクターごとの加点・減点スコア（0〜25スケール内の相対値）
SECTOR_SCORES = {
    # ボーナスセクター
    "Industrials":          20,   # 防衛・航空含む
    "Energy":               19,
    "Information Technology": 18,
    "Health Care":          17,
    "Utilities":            15,
    "Financials":           14,
    # 中立
    "Consumer Discretionary": 13,
    "Consumer Staples":     13,
    "Materials":            12,
    # リスクセクター
    "Real Estate":          10,
    "Communication Services": 11,
}
SECTOR_SCORE_DEFAULT = 12  # 不明セクターのデフォルト

# 防衛・エネルギーの特定キーワードボーナス（summaryに含まれる場合）
DEFENSE_BONUS_KEYWORDS = ["defense", "defence", "aerospace", "military", "weapon"]
DEFENSE_BONUS = 3  # 最大加算点

# ─── ETF専用設定 ──────────────────────────────────────────────────────────

# categoryキーワード → 投資地域タグ
# （yfinanceの category フィールドで判定）
ETF_CATEGORY_REGION = {
    "emerging": "Emerging",      # Diversified Emerging Mkts など
    "foreign":  "Global",        # Foreign Large Blend など
    "global":   "Global",
    "world":    "Global",
    "international": "Global",
}
# 上記に該当しない場合は "US" 扱い

# 投資地域 → 地政学スコア（20点満点）
ETF_REGION_GEO_SCORE = {
    "US":       18,
    "Global":   15,
    "Emerging": 10,
}

# 経費率閾値 → コストスコア（最大28点）
# netExpenseRatio は % 表記で格納（0.03 = 0.03%）
ETF_EXPENSE_RATIO_SCORES = [
    (0.10,  28),   # 0.10%以下 → 28点
    (0.30,  20),   # 0.30%以下 → 20点
    (0.50,  12),   # 0.50%以下 → 12点
    (float("inf"), 6),  # それ以上 → 6点
]

# ─── デフォルト銘柄リスト ─────────────────────────────────────────────────
DEFAULT_TICKERS = ["AAPL", "NVDA", "VTI", "LMT", "XOM", "QQQ", "JNJ", "KO", "PG", "VZ"]
