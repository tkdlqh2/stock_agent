"""포트폴리오 리포트 빌더 — 캐시된 펀더멘털 브리핑 + 라이브 차트 결합.

두 레이어의 주기 분리:
- **차트(단계3·4)**: 호출할 때마다 라이브로 계산(일/주 단위로 돌리는 용도).
- **펀더멘털 브리핑**: `briefs/<ticker>.json` 캐시 사용(분기·월 단위 갱신). 오래되면 '갱신 필요' 표시.

provider 는 지연 생성(필요한 시장만). 네트워크는 호출 시점에만 발생.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .data.provider import PykrxProvider, YFinanceProvider, default_window
from .engine.decide import decide
from .models import Action
from .fundamentals.brief import FundamentalBrief, render_brief
from .fundamentals.store import load_brief, load_portfolio, load_watchlist

# 워치리스트에서 '진입 검토' 신호로 볼 액션(매수 우호).
_ENTRY_ACTIONS = {Action.BUY, Action.CHASE_BUY}


class _Providers:
    """시장별 provider 지연 캐시."""

    def __init__(self) -> None:
        self._us: YFinanceProvider | None = None
        self._kr: PykrxProvider | None = None

    def get(self, market: str):
        if market == "us":
            if self._us is None:
                self._us = YFinanceProvider()
            return self._us
        if self._kr is None:
            self._kr = PykrxProvider()
        return self._kr


def analyze_holding(ticker: str, market: str, brief: FundamentalBrief | None,
                    providers: _Providers, today: date) -> dict:
    """단일 보유 자산 분석 결과(차트 verdict + 브리핑 + staleness)."""
    prov = providers.get(market)
    start, end = default_window()
    daily = prov.ohlcv(ticker, start, end, freq="day")
    weekly = prov.ohlcv(ticker, start, end, freq="week")
    monthly = prov.ohlcv(ticker, start, end, freq="month")
    supply = None if market == "us" else prov.supply(ticker, start, end)
    hint = brief.to_fundamentals_hint() if brief else None
    v = decide(ticker, daily, supply=supply, fundamentals=hint,
               weekly_ohlcv=weekly, monthly_ohlcv=monthly)
    return {
        "ticker": ticker,
        "market": market,
        "last_close": float(daily["close"].iloc[-1]),
        "verdict": v,
        "brief": brief,
        "brief_stale": brief.is_stale(today) if brief else None,
    }


def build_report(base_dir: Path, today: date | None = None) -> str:
    """portfolio.json + briefs/ 캐시를 읽어 통합 리포트 마크다운 생성."""
    today = today or date.today()
    holdings = load_portfolio(base_dir)
    providers = _Providers()

    rows, details, stale = [], [], []
    for h in holdings:
        tk, market = h["ticker"], h["market"]
        brief = load_brief(tk, base_dir)
        r = analyze_holding(tk, market, brief, providers, today)
        v = r["verdict"]
        d = v.to_dict()
        name = brief.name if brief else tk
        sp = d["supply_pattern"] if market == "kr" else "N/A"
        outlook = brief.sector_outlook.value if brief else "-"
        stale_mark = " ⏰갱신필요" if r["brief_stale"] else ""
        rows.append(f"| {name}({tk}) | {market.upper()} | {d['position']} | {d['signal']} | "
                    f"{d['action']} | {sp} | {outlook}{stale_mark} |")
        if r["brief_stale"]:
            stale.append(f"{name}({tk}): 브리핑 {brief.as_of} 기준, {brief.review_cadence_days}일 경과 → 갱신 권장")
        seg = [f"### {name} ({tk}) — 최근종가 {r['last_close']:,.2f}  [{market.upper()}]", "",
               "**① 차트 자동판정 (라이브)**",
               f"- 포지션: {d['position']} · 신호: {d['signal']} · 액션: **{d['action']}**"
               + (f" · 수급: {sp}(확증={d['confirmed']})" if market == "kr" else ""),
               f"- 근거: {', '.join(d['reasons']) if d['reasons'] else '특이 신호 없음'}",
               f"- 경보: {', '.join(d['alerts']) if d['alerts'] else '없음'}", ""]
        if brief:
            seg += [f"**② 펀더멘털 브리핑 (캐시, as_of {brief.as_of}{stale_mark})**", render_brief(brief), ""]
        else:
            seg += ["**② 펀더멘털 브리핑**: 없음(briefs/{}.json 생성 필요)".format(tk), ""]
        details.append("\n".join(seg))

    out = ["# 포트폴리오 통합 리포트 (캐시 브리핑 + 라이브 차트)", "",
           f"- 생성일: {today} · 차트=라이브(일/주 단위 권장) · 펀더멘털=캐시(분기·월 갱신)",
           "- ⚠️ 분석 보조이며 투자 권유 아님. 전량매도 등 최종 판단은 사람.", ""]
    if stale:
        out += ["> ⏰ **전망 갱신 필요**: " + " · ".join(stale), ""]
    out += ["## 보유 — 요약", "",
            "| 자산 | 시장 | 포지션 | 신호 | 액션 | 수급 | 전망 |",
            "|------|------|--------|------|------|------|------|", *rows, "",
            "## 보유 — 상세", "", *details]

    # 워치리스트(미보유 매수 후보) — 진입 신호 감시
    watch = load_watchlist(base_dir)
    if watch:
        wrows, signaled = [], []
        for w in watch:
            tk, market = w["ticker"], w["market"]
            brief = load_brief(tk, base_dir)
            r = analyze_holding(tk, market, brief, providers, today)
            d = r["verdict"].to_dict()
            name = brief.name if brief else tk
            entry = "🟢 진입검토" if r["verdict"].action in _ENTRY_ACTIONS else "⏳ 관망"
            if r["verdict"].action in _ENTRY_ACTIONS:
                signaled.append(f"{name}({tk}): {d['action']} — {', '.join(d['reasons']) or d['signal']}")
            wrows.append(f"| {name}({tk}) | {market.upper()} | {d['position']} | {d['signal']} | "
                         f"{d['action']} | **{entry}** | {', '.join(d['reasons']) or '특이신호 없음'} |")
        out += ["", "## 워치리스트 — 매수 신호 감시 (미보유)", ""]
        if signaled:
            out += ["> 🟢 **진입 신호 포착**: " + " · ".join(signaled), ""]
        else:
            out += ["> ⏳ 진입 신호 없음 — 전 후보 관망. 자리 오면 표의 '진입검토'가 켜집니다.", ""]
        out += ["| 후보 | 시장 | 포지션 | 신호 | 액션 | 진입 | 근거 |",
                "|------|------|--------|------|------|------|------|", *wrows]

    return "\n".join(out)


def main() -> None:  # pragma: no cover - 런타임 진입점
    """`python -m stock_agent.report [base_dir]` — 캐시 브리핑 + 라이브 차트로 리포트 생성."""
    import sys

    base_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    today = date.today()
    report = build_report(base_dir, today)
    dest = base_dir / "reports" / f"포트폴리오_리포트_{today}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(report, encoding="utf-8")
    print(f"리포트 저장: {dest}")


if __name__ == "__main__":  # pragma: no cover
    main()

