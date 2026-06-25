"""매매 일지 — 실행한 매매와 '왜'를 기록하고 복기한다.

리포트(전망)와 짝을 이루는 기록 레이어:
- 리포트 = 앞으로의 국면·신호(분석)
- 일지   = 실제 실행한 매매 + 근거 + 당시 국면(기록·복기)

박두환 8장 철학 반영:
- 부분매도(약 30%) = '쉼표', 전량매도 = '마침표'.
- 복기 지표: 사이클 대비 **보유 수량 증가** 추적(복리 작동 증명) → journal_summary().

저장: journal.json(단일 진실) → 매매일지.md(렌더). 둘 다 개인 데이터(gitignore).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path

# 매매 태그 — 8장 어휘
TAG_ENTRY = "진입"        # 신규/추가 매수
TAG_COMMA = "쉼표"        # 부분매도(약 30%) — 코어 보호
TAG_PERIOD = "마침표"     # 전량매도 — 시나리오 달성/훼손
TAG_REBALANCE = "리밸런싱"  # 비중 조정/교체


@dataclass
class TradeEntry:
    date: str                      # 'YYYY-MM-DD'
    ticker: str
    name: str
    action: str                    # 매수/추격매수/일부매도(30%)/전량매도 등
    rationale: str = ""            # 왜 — 규율상 채우는 게 원칙. 임포트 직후엔 비어있을 수 있음.
    shares: float | None = None    # 체결 수량(+매수/-매도는 부호 또는 action으로 구분)
    price: float | None = None     # 체결 단가(현지 통화)
    tag: str = TAG_ENTRY           # 쉼표/마침표/진입/리밸런싱
    position: str | None = None    # 당시 차트 국면(3-x)
    signal: str | None = None      # 당시 신호(4-x)
    note: str = ""

    @property
    def amount(self) -> float | None:
        if self.shares is None or self.price is None:
            return None
        return self.shares * self.price

    @property
    def signed_shares(self) -> float:
        """매수=+, 매도=-. 수량 미기입이면 0."""
        if self.shares is None:
            return 0.0
        s = abs(self.shares)
        return -s if "매도" in self.action else s


def _journal_path(base_dir: Path) -> Path:
    return base_dir / "journal.json"


def load_journal(base_dir: Path) -> list[TradeEntry]:
    path = _journal_path(base_dir)
    if not path.exists():
        return []
    return [TradeEntry(**d) for d in json.loads(path.read_text(encoding="utf-8"))]


def save_journal(entries: list[TradeEntry], base_dir: Path) -> None:
    _journal_path(base_dir).write_text(
        json.dumps([asdict(e) for e in entries], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    render_journal(base_dir, entries)  # 마크다운 동기화


def log_trade(base_dir: Path, entry: TradeEntry) -> None:
    """매매 1건 기록 — journal.json 추가 + 매매일지.md 재렌더."""
    entries = load_journal(base_dir)
    entries.append(entry)
    entries.sort(key=lambda e: e.date)
    save_journal(entries, base_dir)


def journal_summary(base_dir: Path) -> dict[str, dict]:
    """종목별 누적: 순수량(복리 지표)·매수/매도 횟수·쉼표/마침표 횟수."""
    out: dict[str, dict] = {}
    for e in load_journal(base_dir):
        s = out.setdefault(e.ticker, {
            "name": e.name, "net_shares": 0.0,
            "buys": 0, "sells": 0, "comma": 0, "period": 0,
        })
        s["net_shares"] += e.signed_shares
        if "매도" in e.action:
            s["sells"] += 1
        else:
            s["buys"] += 1
        if e.tag == TAG_COMMA:
            s["comma"] += 1
        if e.tag == TAG_PERIOD:
            s["period"] += 1
    return out


def render_journal(base_dir: Path, entries: list[TradeEntry] | None = None) -> Path:
    """journal.json -> 매매일지.md (역순, 최신 위)."""
    entries = entries if entries is not None else load_journal(base_dir)
    lines = ["# 매매 일지", "",
             "> journal.json 에서 자동 생성. 부분매도=쉼표, 전량매도=마침표(8장).", ""]
    for e in sorted(entries, key=lambda x: x.date, reverse=True):
        head = f"## {e.date} · [{e.tag}] {e.action} · {e.name}({e.ticker})"
        lines.append(head)
        qp = []
        if e.shares is not None:
            qp.append(f"{e.shares:,.0f}주")
        if e.price is not None:
            qp.append(f"@{e.price:,.2f}")
        if e.amount is not None:
            qp.append(f"= {e.amount:,.0f}")
        if qp:
            lines.append(f"- 체결: {' '.join(qp)}")
        ctx = [c for c in (e.position, e.signal) if c]
        if ctx:
            lines.append(f"- 당시 국면: {' / '.join(ctx)}")
        lines.append(f"- 근거: {e.rationale}")
        if e.note:
            lines.append(f"- 메모: {e.note}")
        lines.append("")
    path = base_dir / "매매일지.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
