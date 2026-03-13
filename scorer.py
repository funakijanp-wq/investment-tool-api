# scorer.py - 4レイヤー採点エンジン

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from data_fetcher import StockData
import config as cfg

# yfinanceが返すセクター名 → config.SECTOR_SCORESのキーへの正規化マップ
SECTOR_NORMALIZE = {
    "Technology":              "Information Technology",
    "Financial Services":      "Financials",
    "Consumer Cyclical":       "Consumer Discretionary",
    "Consumer Defensive":      "Consumer Staples",
    "Healthcare":              "Health Care",
    "Basic Materials":         "Materials",
    "Communication Services":  "Communication Services",
    "Industrials":             "Industrials",
    "Energy":                  "Energy",
    "Utilities":               "Utilities",
    "Real Estate":             "Real Estate",
}


@dataclass
class ScoreDetail:
    geopolitical: int = 0    # Layer1: 0〜20
    macro:        int = 0    # Layer2: 0〜25
    fundamental:  int = 0    # Layer3: 0〜30
    sector:       int = 0    # Layer4: 0〜25

    # 業績サブスコア（表示用）
    eps_growth_score:     int = 0
    revenue_growth_score: int = 0
    equity_ratio_score:   int = 0
    dividend_score:       int = 0

    # デバッグ情報
    notes: list[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []

    @property
    def total(self) -> int:
        return self.geopolitical + self.macro + self.fundamental + self.sector


def score(data: StockData) -> ScoreDetail:
    detail = ScoreDetail()
    if data.is_etf:
        detail.geopolitical = _etf_layer1_region(data, detail)
        detail.macro        = _layer2_macro(data, detail)        # 株式と同一ロジック
        detail.fundamental  = _etf_layer3_cost(data, detail)
        detail.sector       = _etf_layer4_sector(data, detail)
    else:
        detail.geopolitical = _layer1_geopolitical(data, detail)
        detail.macro        = _layer2_macro(data, detail)
        detail.fundamental  = _layer3_fundamental(data, detail)
        detail.sector       = _layer4_sector(data, detail)
    return detail


# ─── Layer1: 地政学リスク（20点満点） ──────────────────────────────────────

def _layer1_geopolitical(data: StockData, detail: ScoreDetail) -> int:
    country = data.country
    risk = cfg.COUNTRY_RISK.get(country, cfg.COUNTRY_RISK_DEFAULT)

    # risk × 20 を基本スコアとし、中国・ロシアは上限5点でキャップ
    raw = round(risk * 20)
    is_high_risk = country in ("China", "Russia")
    if is_high_risk:
        score = min(raw, 5)
        detail.notes.append(f"地政学: {country}（高リスク国）→ 上限5点")
    else:
        score = raw
        detail.notes.append(f"地政学: {country} リスク係数={risk:.2f} → {score}点")

    return min(20, max(0, score))


# ─── Layer2: マクロ経済（25点満点） ────────────────────────────────────────

def _layer2_macro(data: StockData, detail: ScoreDetail) -> int:
    per = data.per
    rate = cfg.CURRENT_INTEREST_RATE

    if per is None:
        detail.notes.append("マクロ: PER取得不可 → デフォルト12点")
        return 12

    if rate >= 4.0:
        # 高金利環境：PERに厳しい
        if   per <= 20: score = 25
        elif per <= 25: score = 18
        elif per <= 30: score = 12
        else:           score = 6
        detail.notes.append(f"マクロ: 高金利({rate}%) PER={per:.1f} → {score}点")

    elif rate < 3.0:
        # 低金利環境：高PERを許容
        if   per <= 30: score = 25
        elif per <= 40: score = 18
        else:           score = 10
        detail.notes.append(f"マクロ: 低金利({rate}%) PER={per:.1f} → {score}点")

    else:
        # 中金利環境（3〜4%）：中間基準
        if   per <= 25: score = 25
        elif per <= 35: score = 18
        elif per <= 45: score = 12
        else:           score = 6
        detail.notes.append(f"マクロ: 中金利({rate}%) PER={per:.1f} → {score}点")

    return score


# ─── Layer3: 企業業績（30点満点） ──────────────────────────────────────────

def _layer3_fundamental(data: StockData, detail: ScoreDetail) -> int:

    # EPS成長率（10点満点）
    eps = data.eps_growth
    if eps is None:
        eps_score = 2  # 不明は控えめに
        detail.notes.append("業績: EPS成長率不明 → 2点")
    elif eps >= 20: eps_score = 10
    elif eps >= 10: eps_score = 7
    elif eps >= 0:  eps_score = 4
    else:           eps_score = 0

    # 売上成長率（8点満点）
    rev = data.revenue_growth
    if rev is None:
        rev_score = 2
        detail.notes.append("業績: 売上成長率不明 → 2点")
    elif rev >= 15: rev_score = 8
    elif rev >= 8:  rev_score = 5
    elif rev >= 0:  rev_score = 3
    else:           rev_score = 0

    # 自己資本比率（7点満点）
    eq = data.equity_ratio
    if eq is None:
        eq_score = 2
        detail.notes.append("業績: 自己資本比率不明 → 2点")
    elif eq >= 40: eq_score = 7
    elif eq >= 20: eq_score = 5
    elif eq >= 0:  eq_score = 3
    else:          eq_score = 0

    # 配当利回り（5点満点）
    div = data.dividend_yield
    if div is None:
        div_score = 1
    elif div >= 2.0: div_score = 5
    elif div >= 0.0: div_score = 3
    else:            div_score = 1

    total = eps_score + rev_score + eq_score + div_score

    detail.eps_growth_score     = eps_score
    detail.revenue_growth_score = rev_score
    detail.equity_ratio_score   = eq_score
    detail.dividend_score       = div_score

    return min(30, max(0, total))


# ─── Layer4: セクターリスク（25点満点） ────────────────────────────────────

def _layer4_sector(data: StockData, detail: ScoreDetail) -> int:
    # セクター名を正規化
    raw_sector = data.sector
    sector = SECTOR_NORMALIZE.get(raw_sector, raw_sector)

    base = cfg.SECTOR_SCORES.get(sector, cfg.SECTOR_SCORE_DEFAULT)

    # 防衛・宇宙関連キーワードボーナス
    bonus = 0
    matched_kws = [kw for kw in cfg.DEFENSE_BONUS_KEYWORDS if kw in data.summary]
    if matched_kws:
        bonus = cfg.DEFENSE_BONUS
        detail.notes.append(f"セクター: 防衛ボーナス({', '.join(matched_kws)}) +{bonus}点")

    score = min(25, base + bonus)
    detail.notes.append(f"セクター: {sector}({raw_sector}) base={base} → {score}点")

    return score


# ─── ETF専用レイヤー ───────────────────────────────────────────────────────

def _etf_region(data: StockData) -> str:
    """ETFの投資地域タグ（"US" / "Global" / "Emerging"）を返す。"""
    category_lower = data.etf_category.lower()
    for keyword, region in cfg.ETF_CATEGORY_REGION.items():
        if keyword in category_lower:
            return region
    return "US"  # デフォルトは米国


def _etf_layer1_region(data: StockData, detail: ScoreDetail) -> int:
    """Layer1（ETF版）: 投資地域ベースの地政学スコア（20点満点）。"""
    region = _etf_region(data)
    score = cfg.ETF_REGION_GEO_SCORE.get(region, 13)
    detail.notes.append(
        f"地政学(ETF): category='{data.etf_category}' → {region} → {score}点"
    )
    return score


def _etf_layer3_cost(data: StockData, detail: ScoreDetail) -> int:
    """Layer3（ETF版）: 経費率コスト評価（30点満点）。
    内訳: 経費率スコア(最大28点) + 配当スコア(最大2点)
    """
    # 経費率スコア（28点満点）
    er = data.expense_ratio
    if er is None:
        cost_score = 10
        detail.notes.append("コスト: 経費率不明 → 10点")
    else:
        cost_score = next(
            pts for threshold, pts in cfg.ETF_EXPENSE_RATIO_SCORES
            if er <= threshold
        )
        detail.notes.append(f"コスト: 経費率={er:.2f}% → {cost_score}点")

    # 配当スコア（2点満点）
    div = data.dividend_yield
    if div is None:
        div_score = 0
    elif div >= 1.0: div_score = 2
    else:            div_score = 1

    total = cost_score + div_score
    detail.dividend_score = div_score
    detail.notes.append(
        f"コスト合計: {cost_score}(経費率) + {div_score}(配当) = {total}点"
    )
    return min(30, max(0, total))


def _etf_layer4_sector(data: StockData, detail: ScoreDetail) -> int:
    """Layer4（ETF版）: broad market→20点固定、セクターETF→SECTOR_SCORES参照。"""
    raw_sector = data.sector
    sector = SECTOR_NORMALIZE.get(raw_sector, raw_sector)

    if not sector:
        # セクター情報なし = broad market ETF（全市場インデックス）
        score = 20
        detail.notes.append(f"セクター(ETF): broad market → {score}点固定")
    else:
        score = cfg.SECTOR_SCORES.get(sector, cfg.SECTOR_SCORE_DEFAULT)
        detail.notes.append(f"セクター(ETF): {sector} → {score}点")

    return min(25, score)


# ─── 判定ラベル ────────────────────────────────────────────────────────────

def verdict(total: int) -> str:
    if   total >= 75: return "✅ 強く推奨"
    elif total >= 60: return "✅ 積立候補"
    elif total >= 45: return "⚠️  要注意"
    else:             return "❌ 非推奨"
