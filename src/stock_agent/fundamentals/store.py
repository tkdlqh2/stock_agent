"""펀더멘털 브리핑 캐시 + 포트폴리오 구성 영속화.

차트는 매일/매주 새로 계산하지만, 전망(브리핑)은 분기·월 단위로만 갱신하면 된다.
그래서 브리핑을 JSON 으로 디스크에 저장(캐시)해두고, 리포트 생성 시 재사용한다.
브리핑이 review_cadence_days 를 넘기면 리포트가 '전망 갱신 필요'로 표시한다.

레이아웃(기본 base_dir = 프로젝트 루트):
  briefs/<TICKER>.json   각 종목 펀더멘털 브리핑
  portfolio.json         보유 구성: [{"ticker","market"}]  (market: us|kr)
"""
from __future__ import annotations

import json
from pathlib import Path

from .brief import FundamentalBrief


def briefs_dir(base_dir: Path) -> Path:
    d = base_dir / "briefs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_brief(brief: FundamentalBrief, base_dir: Path) -> Path:
    path = briefs_dir(base_dir) / f"{brief.ticker}.json"
    path.write_text(json.dumps(brief.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_brief(ticker: str, base_dir: Path) -> FundamentalBrief | None:
    path = briefs_dir(base_dir) / f"{ticker}.json"
    if not path.exists():
        return None
    return FundamentalBrief.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_portfolio(holdings: list[dict], base_dir: Path) -> Path:
    """holdings: [{"ticker": "091230", "market": "kr"}, ...]"""
    path = base_dir / "portfolio.json"
    path.write_text(json.dumps(holdings, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_portfolio(base_dir: Path) -> list[dict]:
    path = base_dir / "portfolio.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_watchlist(items: list[dict], base_dir: Path) -> Path:
    """매수 후보(미보유) — 리포트가 진입 신호를 감시. [{"ticker","market"}]"""
    path = base_dir / "watchlist.json"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_watchlist(base_dir: Path) -> list[dict]:
    path = base_dir / "watchlist.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
