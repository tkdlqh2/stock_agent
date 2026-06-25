"""FundamentalBrief — 섹터·주도주·시나리오 리서치 브리핑 (단계1·2 보조).

차트 엔진(결정론)과 달리 이 브리핑은 **해석**이다. 따라서:
- 모든 정성 판단에 `sources`(출처)를 붙이고,
- `confidence`(확신도)와 `as_of`(기준일)를 명시하며,
- 결론을 단정하지 않고 'thesis_risks'(가정 훼손 후보)를 나열한다.

브리핑은 사람이 읽고 `engine.sell_rules.Fundamentals`(thesis_broken 등)를 직접 설정하는
근거가 된다. 브리핑이 thesis_broken 을 자동 결정하지 않는다(자동화 금지 영역).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from ..engine.sell_rules import Fundamentals


class Outlook(str, Enum):
    POSITIVE = "긍정"
    NEUTRAL = "중립"
    NEGATIVE = "부정"
    UNCLEAR = "불명확"


@dataclass
class FundamentalBrief:
    ticker: str
    name: str
    sector: str
    as_of: date

    # 자산 유형: 'stock'(개별주) / 'etf'(ETF·테마) / 'commodity'(금 등 원자재)
    asset_kind: str = "stock"

    # --- 정성 (LLM/사람 보조 해석, 단정 금지) ---
    sector_outlook: Outlook = Outlook.UNCLEAR
    sector_notes: str = ""                       # 섹터/테마/매크로 전망 근거 요약
    is_market_leader: bool | None = None         # (stock) 섹터 주도주인가
    leader_notes: str = ""                       # 주도주/구성 판단 근거
    top_holdings: list[str] = field(default_factory=list)  # (etf) 상위 구성종목 + 한줄평
    catalysts: list[str] = field(default_factory=list)     # 상방 촉매
    thesis_risks: list[str] = field(default_factory=list)  # 시나리오 훼손 후보(단정X)

    # --- 정량 (자동 보조/훼손 감시 가능) ---
    roic_gt_wacc: bool | None = None
    fcf_positive: bool | None = None
    revenue_trend_up: bool | None = None
    quant_notes: str = ""

    # --- 메타 ---
    confidence: str = "중"                        # 상/중/하 — 리서치 확신도
    sources: list[str] = field(default_factory=list)
    cadence: str = "분기 실적 + 주요 이벤트 트리거"  # 차트와 분리된 갱신 주기(설명)
    review_cadence_days: int = 0                   # 0=유형별 기본(stock/etf=90, commodity=30)

    def __post_init__(self) -> None:
        if not self.review_cadence_days:
            self.review_cadence_days = 30 if self.asset_kind == "commodity" else 90

    def is_stale(self, today: date | None = None) -> bool:
        """as_of 가 review_cadence_days 보다 오래되면 '전망 갱신 필요'."""
        today = today or date.today()
        return (today - self.as_of).days > self.review_cadence_days

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["as_of"] = self.as_of.isoformat()
        d["sector_outlook"] = self.sector_outlook.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "FundamentalBrief":
        d = dict(d)
        d["as_of"] = date.fromisoformat(d["as_of"])
        d["sector_outlook"] = Outlook(d["sector_outlook"])
        return cls(**d)

    def to_fundamentals_hint(self) -> Fundamentals:
        """정량 지표만 게이트로 전달(훼손 감시). thesis_broken/target_reached 는
        사람이 본 브리핑을 읽고 직접 설정한다 — 여기서 자동 설정하지 않는다."""
        return Fundamentals(
            roic_gt_wacc=self.roic_gt_wacc,
            fcf_positive=self.fcf_positive,
            revenue_trend_up=self.revenue_trend_up,
        )


def render_brief(b: FundamentalBrief) -> str:
    """브리핑을 사람이 읽을 마크다운으로. 자산 유형별로 표기를 달리한다."""
    kind_label = {"stock": "개별주", "etf": "ETF/테마", "commodity": "원자재/매크로"}.get(b.asset_kind, b.asset_kind)
    outlook_label = {"stock": "섹터 전망", "etf": "테마 전망", "commodity": "매크로 전망"}.get(b.asset_kind, "전망")
    lines = [
        f"#### {b.name} ({b.ticker}) — 펀더멘털 브리핑 [{kind_label}]",
        f"- 섹터/테마: {b.sector} · 기준일: {b.as_of} · 확신도: {b.confidence} · 갱신주기: {b.cadence}",
        f"- {outlook_label}: **{b.sector_outlook.value}** — {b.sector_notes}",
    ]
    if b.asset_kind == "stock":
        leader = {True: "예(주도주)", False: "아니오", None: "불명확"}[b.is_market_leader]
        lines.append(f"- 주도주 여부: **{leader}** — {b.leader_notes}")
    elif b.asset_kind == "etf":
        if b.leader_notes:
            lines.append(f"- 구성 성격: {b.leader_notes}")
        if b.top_holdings:
            lines.append("- 상위 구성종목: " + "; ".join(b.top_holdings))
    else:  # commodity
        if b.leader_notes:
            lines.append(f"- 수급/구조: {b.leader_notes}")
    if b.catalysts:
        lines.append("- 상방 촉매: " + "; ".join(b.catalysts))
    if b.thesis_risks:
        lines.append("- ⚠ 시나리오 훼손 후보(단정 아님, 사람 점검): " + "; ".join(b.thesis_risks))
    quant = []
    for label, val in [("ROIC>WACC", b.roic_gt_wacc), ("FCF>0", b.fcf_positive), ("매출↑", b.revenue_trend_up)]:
        if val is not None:
            quant.append(f"{label}={'O' if val else 'X'}")
    if quant or b.quant_notes:
        lines.append(f"- 정량(자동 감시): {' · '.join(quant)} {('— ' + b.quant_notes) if b.quant_notes else ''}")
    if b.sources:
        lines.append("- 출처: " + "; ".join(b.sources))
    return "\n".join(lines)
