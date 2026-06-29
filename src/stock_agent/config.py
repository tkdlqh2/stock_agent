"""출력 위치 설정 — 사람이 읽는 기록(리포트·매매일지)을 어디에 남길지.

데이터(json·briefs)는 프로젝트(base_dir)에 두고, **문서 출력만** 외부(예: Obsidian 볼트)로
보낼 수 있다. config.json(개인 데이터, gitignore)의 output_dir > 환경변수 STOCK_AGENT_VAULT
> base_dir(미설정 시 프로젝트 안) 순으로 해석한다.

볼트로 설정되면 사용자가 만든 한글 폴더 관례를 따른다:
  <vault>/리포트/포트폴리오_리포트_*.md   ·   <vault>/매매일지/매매일지.md
미설정(프로젝트 내) 기본:
  <base>/reports/*.md   ·   <base>/매매일지.md
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _config_path(base_dir: Path) -> Path:
    return base_dir / "config.json"


def load_config(base_dir: Path) -> dict:
    p = _config_path(base_dir)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_config(base_dir: Path, **kwargs) -> Path:
    cfg = load_config(base_dir)
    cfg.update(kwargs)
    path = _config_path(base_dir)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_output_dir(base_dir: Path) -> Path:
    """리포트·매매일지를 남길 루트. config.json output_dir > env > base_dir."""
    out = load_config(base_dir).get("output_dir") or os.getenv("STOCK_AGENT_VAULT")
    return Path(out) if out else base_dir


def report_dir(base_dir: Path) -> Path:
    """리포트 저장 폴더(없으면 생성). 볼트면 '리포트/', 프로젝트면 'reports/'."""
    out = resolve_output_dir(base_dir)
    d = (out / "리포트") if out != base_dir else (out / "reports")
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_path(base_dir: Path) -> Path:
    """매매일지.md 경로(상위 폴더 생성). 볼트면 '매매일지/매매일지.md'."""
    out = resolve_output_dir(base_dir)
    p = (out / "매매일지" / "매매일지.md") if out != base_dir else (out / "매매일지.md")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
