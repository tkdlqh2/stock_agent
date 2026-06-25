"""미래에셋 거래내역(체결) CSV → 매매 일지 임포트.

미래에셋 HTS/MTS 에서 내보낸 '거래내역' CSV(국내/해외)를 파싱해 TradeEntry 로 변환한다.
- 인코딩: 한국 증권사 CSV는 보통 cp949(euc-kr). utf-8-sig 도 시도.
- 컬럼은 한글 헤더로 매칭(공백 제거). 종목번호 = 티커(미국=심볼, 한국=6자리).
- **자동으로 채우는 것**: 날짜·종목·수량·체결단가·수수료·세금·원화손익.
- **수동으로 남는 것**: tag(쉼표/마침표) + rationale(왜) — 시나리오 판단=사람.
  (임포트 후 enrich_entry() 또는 직접 보정으로 채운다.)
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .journal import TradeEntry


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _num(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return 0.0


def import_miraeasset_csv(path: str | Path) -> list[TradeEntry]:
    """미래에셋 거래내역 CSV → 체결 기반 TradeEntry 목록(tag/rationale 미설정)."""
    text = _read_text(Path(path))
    reader = csv.DictReader(io.StringIO(text))
    out: list[TradeEntry] = []
    for row in reader:
        r = {(k or "").strip().replace(" ", ""): (v or "").strip() for k, v in row.items()}
        date = r.get("매매일")
        ticker = r.get("종목번호")
        if not date or not ticker:  # 빈 줄/꼬리 스킵
            continue
        name = r.get("종목명") or ticker
        buy, sell, bal = _num(r.get("매수수량")), _num(r.get("매도수량")), _num(r.get("잔고수량"))
        if sell > 0:
            action = "전량매도" if bal == 0 else "일부매도"
            shares, price = sell, _num(r.get("매도단가"))
        elif buy > 0:
            action, shares, price = "매수", buy, _num(r.get("매수단가"))
        else:
            continue
        pnl = r.get("총평가손익") or r.get("원화매매손익") or ""
        ret = r.get("환산손익률") or r.get("손익률") or ""
        note = f"수수료 {r.get('수수료','-')}·세금 {r.get('세금','-')}"
        if pnl:
            note += f" / 원화손익 {pnl}원" + (f"({ret}%)" if ret else "")
        out.append(TradeEntry(
            date=date.replace("/", "-"), ticker=ticker, name=name,
            action=action, shares=shares, price=price, note=note,
        ))
    return out


def enrich_entry(entry: TradeEntry, *, tag: str, rationale: str,
                 position: str | None = None, signal: str | None = None,
                 name: str | None = None) -> TradeEntry:
    """임포트한 체결에 사람 판단(tag·근거·당시 국면)을 덧붙인다."""
    entry.tag = tag
    entry.rationale = rationale
    if position:
        entry.position = position
    if signal:
        entry.signal = signal
    if name:
        entry.name = name
    return entry
