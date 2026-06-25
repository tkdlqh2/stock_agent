"""MCP 서버 스텁 — `종목코드 -> OHLCV/수급/판정` 도구화.

명세서 방향: 증권 API(여기선 pykrx 공개데이터)를 MCP 서버로 감싸 도구로 노출.
mcp 패키지는 선택 의존성(`pip install -e ".[mcp]"`)이며 지연 import 한다.

도구:
  analyze_ticker(ticker, ...)  -> 종목별 Verdict(현재 포지션/권장 액션/근거/경보)
  get_ohlcv(ticker, ...)       -> 표준 OHLCV
  get_supply(ticker, ...)      -> 외국인/기관/개인 순매수

실행:  python -m stock_agent.mcp_server   (stdio transport)
"""
from __future__ import annotations

from pathlib import Path

from .data.provider import PykrxProvider, default_window
from .engine.decide import decide
from .engine.sell_rules import Fundamentals


def _home() -> Path:
    """포트폴리오/브리핑 캐시 위치. 환경변수 STOCK_AGENT_HOME 우선, 없으면 프로젝트 루트."""
    import os

    env = os.getenv("STOCK_AGENT_HOME")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def build_server():  # pragma: no cover - 통합(런타임) 코드
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "mcp 가 필요합니다. `pip install -e \".[mcp]\"` 로 설치하세요."
        ) from exc

    mcp = FastMCP("stock-agent")
    provider = PykrxProvider()

    @mcp.tool()
    def get_ohlcv(ticker: str, freq: str = "day") -> list[dict]:
        """종목코드 -> OHLCV(일/주/월봉). freq: day|week|month."""
        start, end = default_window()
        df = provider.ohlcv(ticker, start, end, freq=freq)  # type: ignore[arg-type]
        return df.reset_index().astype(str).to_dict(orient="records")

    @mcp.tool()
    def get_supply(ticker: str) -> list[dict]:
        """종목코드 -> 외국인/기관/개인 순매수."""
        start, end = default_window()
        df = provider.supply(ticker, start, end)
        return df.reset_index().astype(str).to_dict(orient="records")

    @mcp.tool()
    def analyze_ticker(
        ticker: str,
        target_reached: bool = False,
        thesis_broken: bool = False,
    ) -> dict:
        """종목 분석 -> 현재 포지션 / 권장 액션 / 근거 / 경보.

        target_reached·thesis_broken 은 사람(단계1·2) 입력. 기본 False.
        """
        start, end = default_window()
        ohlcv = provider.ohlcv(ticker, start, end, freq="day")
        weekly = provider.ohlcv(ticker, start, end, freq="week")
        supply = provider.supply(ticker, start, end)
        fund = Fundamentals(target_reached=target_reached, thesis_broken=thesis_broken)
        verdict = decide(ticker, ohlcv, supply, fund, weekly_ohlcv=weekly)
        return verdict.to_dict()

    @mcp.tool()
    def analyze_portfolio() -> str:
        """저장된 워치리스트(portfolio.json) + 캐시 브리핑(briefs/)으로 통합 리포트 생성.

        차트는 라이브, 펀더멘털은 캐시(분기·월 갱신). 마크다운 리포트를 반환한다.
        """
        from .report import build_report

        return build_report(_home())

    return mcp


def main() -> None:  # pragma: no cover - 런타임 진입점
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
