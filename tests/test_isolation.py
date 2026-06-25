from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MT5_MODULE = "Meta" + "Trader5"


def python_files(*parts: str) -> list[Path]:
    base = ROOT.joinpath(*parts)
    return [path for path in base.rglob("*.py") if "__pycache__" not in path.parts]


def test_no_mt5_order_send_outside_risk_gate() -> None:
    offenders: list[str] = []
    for path in python_files("src") + python_files("scripts"):
        relative = path.relative_to(ROOT)
        if relative.parts[:3] == ("src", "trifolium", "risk_gate"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "order_send":
                offenders.append(f"{relative}:{node.lineno}")
    assert offenders == []


def test_strategy_has_no_mt5_import_or_order_send_path() -> None:
    offenders: list[str] = []
    for path in python_files("src", "trifolium", "strategy"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == MT5_MODULE or alias.name.startswith(MT5_MODULE + ".") for alias in node.names):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:import")
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == MT5_MODULE or node.module.startswith(MT5_MODULE + ".")):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:import_from")
            elif isinstance(node, ast.Attribute) and node.attr == "order_send":
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}:order_send")
    assert offenders == []
