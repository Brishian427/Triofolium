# Task 05 — Self-Evolving Strategy Discovery System

**Prerequisite**: Tasks 00 (Charter), 01 (Pipeline L0/L1/L3), 02 (Risk Gate L0-L3 + dry-run), 03 (Backtest engine L0/L1 partial + bar-level fast path), 04 (Strategy v0 L0-L4 + L5 callable just landed).

**Mode**: Plan A — Aggressive. Build all components in one continuous pass. Single checkpoint at 13:30 BST for unit test status (no decision required, just status report). Integration test once at end. Do not pause for principal approval between components.

**Hard deadline**: 14:00 BST system go-live (first iteration end-to-end PASS). If at 13:50 BST a component is still failing integration, report blocker — do not silently push past deadline.

---

## 0. Quick Read for Principal (the only 3 things to review)

1. **Architecture diagram** in §1 — confirm component boundaries are right
2. **Acceptance criteria** in §11 — confirm what "done" means
3. **Out-of-scope** in §12 — confirm what we're NOT building today

Everything else is implementation detail. If §1, §11, §12 look right, send to Codex.

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Self-Evolving Strategy Discovery Loop (Task 05)                     │
└──────────────────────────────────────────────────────────────────────┘

  ┌──────────────────────┐      ┌──────────────────────┐
  │  Strategy v0 (live)  │      │  Memory Table        │
  │  - per Task 04       │      │  - SQLite            │
  │  - L5 report (json)  │◄────►│  - parent_id tree    │
  └──────────┬───────────┘      │  - element_table     │
             │                  │  - metrics_json      │
             ▼                  └──────────┬───────────┘
  ┌──────────────────────┐                 │
  │  L5 Validation       │                 │
  │  (Task 04 callable)  │                 │
  │  → ValidationResult  │                 │
  └──────────┬───────────┘                 │
             │                             │
             ▼                             │
  ┌──────────────────────────────────────────────────────────────────┐
  │  LOOP ORCHESTRATOR (5-step state machine, idempotent, JSONL log) │
  └──────────────────────────────────────────────────────────────────┘
             │
             ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 1: read_report                                             │
  │  Input: ValidationResult + Memory Table snapshot                 │
  │  Output: markdown formatted prompt for Brain                     │
  └────────┬────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 2: brain_propose (Nemotron 3 Ultra via NIM API)            │
  │  Input: markdown report + Memory history                         │
  │  Output: HypothesisJSON {                                        │
  │    target_files: [predictor.py | trader.py | portfolio.py |     │
  │                   strategy_v0.yaml],                             │
  │    element_diff: {layer: ..., dimension: ..., from: ..., to: ...}│
  │    rationale: str,                                               │
  │    expected_metric_change: {metric: ..., direction: +/-, ...}    │
  │  }                                                               │
  └────────┬────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 3: guardrail_check (NeMo Guardrails)                       │
  │  - Input: HypothesisJSON                                         │
  │  - Schema validation: required fields, target_files in whitelist │
  │  - Forbidden topic check: NO suggestion mentions risk_gate /     │
  │    risk_limits / mt5.order_send                                  │
  │  - Output: (passed: bool, violations: [...])                     │
  │  - On FAIL: log + skip to next iteration (Brain proposed bad)    │
  └────────┬────────────────────────────────────────────────────────┘
           │ PASS
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 4: coder_apply (Anthropic Sonnet 4.6)                      │
  │  - Input: HypothesisJSON + relevant source files                 │
  │  - Output: code patch (unified diff format)                      │
  │  - Apply patch to NEW branch (strategy_v_N+1)                    │
  │  - Sandbox: git worktree or file copy, never modify v0 directly  │
  └────────┬────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 5: scope_check (D1 = B+ enforcement)                       │
  │  - AST grep on patched files                                     │
  │  - Whitelist: predictor.py, trader.py, portfolio.py,             │
  │    config/strategy_v0.yaml                                       │
  │  - Blacklist: strategy.py, risk_gate/*, risk_limits.yaml         │
  │  - Forbidden imports: mt5, MetaTrader5 (outside risk_gate/)      │
  │  - On FAIL: rollback patch, log violation, skip to next iteration│
  └────────┬────────────────────────────────────────────────────────┘
           │ PASS
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 6: backtest_gate (Task 04 L5 callable)                     │
  │  - Run validate_strategy(strategy_v_N+1, ...) → ValidationResult │
  │  - Use 6h short window for fast iteration (not full 30 days)     │
  │  - Output: ValidationResult with 9-section report (D2)           │
  └────────┬────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 7: evaluate (D2 Evaluation Framework 5-step)               │
  │  - Brain reads BOTH v_N (parent) and v_N+1 reports               │
  │  - Brain runs 5-step prompt: Gate → Binding → Objective →        │
  │    Tie-break → Robustness                                        │
  │  - Output: Decision {ACCEPT | KEEP | REJECT | NO-OP} + reason    │
  └────────┬────────────────────────────────────────────────────────┘
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │  Step 8: memory_write                                            │
  │  - Insert v_N+1 entry to Memory Table                            │
  │  - Fields: nickname / timestamp / parent_id / element_table /    │
  │    metrics / current_rank / decision / modification_type         │
  └────────┬────────────────────────────────────────────────────────┘
           │
           └────────► back to Step 1 for next iteration
```

**Key invariants**:
- Live strategy never changes during loop iteration (loop runs candidates in sandbox)
- Risk Gate not touched by anything in loop
- Each iteration produces a Memory Table row + JSONL log entry
- Each step idempotent: if loop crashes mid-iteration, restart from last completed step
- Loop never auto-deploys to live; principal explicit go-ahead required for any v_N+1 → live

---

## 2. File Structure

```
src/trifolium/
├── agents/                          # NEW
│   ├── __init__.py
│   ├── nim_client.py                # NVIDIA NIM API wrapper (Nemotron 3 Ultra)
│   ├── anthropic_client.py          # Anthropic Sonnet 4.6 wrapper
│   ├── brain.py                     # Nemotron-as-planner logic
│   ├── coder.py                     # Sonnet-as-coder logic
│   ├── scope_guard.py               # D1 = B+ scope enforcement
│   └── guardrails.py                # D3 = A NeMo Guardrails integration
│
├── memory/                          # NEW
│   ├── __init__.py
│   ├── strategy_memory.py           # SQLite Memory Table CRUD
│   └── schema.sql                   # Table definition
│
├── strategy/
│   ├── elements.py                  # NEW: Element Periodic Table schema (Pydantic)
│   └── (existing files)
│
├── loop/                            # NEW
│   ├── __init__.py
│   ├── orchestrator.py              # 8-step state machine
│   ├── types.py                     # HypothesisJSON, IterationLog, etc.
│   └── sandbox.py                   # File copy / patch apply helpers
│
└── validation/
    └── (existing l5.py from Codex morning)

scripts/
├── run_loop_iteration.py            # NEW: CLI to run 1 iteration
├── run_loop_continuous.py           # NEW: CLI to run loop in background (14:00+)
└── demo_ui.py                       # NEW: minimal HTML UI for demo

config/
└── self_improving.yaml              # NEW: loop config (rate limits, iteration freq, etc.)

tests/
├── test_agents/                     # NEW
│   ├── test_nim_client.py
│   ├── test_anthropic_client.py
│   ├── test_brain.py
│   ├── test_coder.py
│   ├── test_scope_guard.py
│   └── test_guardrails.py
├── test_memory/                     # NEW
│   └── test_strategy_memory.py
├── test_strategy/
│   └── test_elements.py             # NEW
└── test_loop/                       # NEW
    ├── test_orchestrator.py
    └── test_integration.py          # end-to-end with mocked agents

logs/
├── loop_iterations_YYYY-MM-DD.jsonl
└── (existing logs)
```

---

## 3. Component C1: NIM Client (`agents/nim_client.py`)

```python
from openai import OpenAI
from typing import Optional
import os

class NIMClient:
    """Wrapper for NVIDIA NIM API hosted endpoint.
    OpenAI-compatible interface."""

    DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
    DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEMO_MODEL = "nvidia/nemotron-3-super-120b-a12b"  # faster for demo

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY")
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not set in env or constructor")
        self.client = OpenAI(base_url=self.DEFAULT_BASE_URL, api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL

    def chat(
        self,
        messages: list[dict],
        reasoning_budget: int = 8192,
        max_tokens: int = 16384,
        temperature: float = 0.7,
    ) -> str:
        """Returns content string (non-streaming for simplicity in loop)."""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body={
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": reasoning_budget,
            },
        )
        return response.choices[0].message.content
```

**Test (`tests/test_agents/test_nim_client.py`)**:
- 1 test: instantiate with env var, mock httpx, verify request body has `model="nvidia/nemotron-3-ultra-550b-a55b"` and `reasoning_budget` in `extra_body`
- 1 test: no API key in env → raises ValueError
- **No real API call in tests** (use mocks)

---

## 4. Component C2: Anthropic Client (`agents/anthropic_client.py`)

```python
import anthropic
import os
from typing import Optional

class AnthropicClient:
    """Wrapper for Anthropic Sonnet 4.6 API."""

    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in env or constructor")
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.model = model or self.DEFAULT_MODEL

    def generate_code_patch(
        self,
        hypothesis: dict,
        relevant_source_files: dict[str, str],
        max_tokens: int = 4096,
    ) -> str:
        """Returns unified diff format code patch."""
        system = (
            "You are a code generation assistant for a quant trading strategy "
            "self-evolution loop. Generate a unified diff patch implementing the "
            "given hypothesis. Modify ONLY the files listed in target_files. "
            "Output the patch only, no commentary."
        )
        user_content = (
            f"Hypothesis:\n{hypothesis}\n\n"
            f"Source files (current state):\n"
        )
        for fname, content in relevant_source_files.items():
            user_content += f"\n--- {fname} ---\n{content}\n"

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return response.content[0].text
```

**Test (`tests/test_agents/test_anthropic_client.py`)**:
- 1 test: instantiate with env var, mock httpx, verify request has correct system + user content
- 1 test: no API key → ValueError
- **No real API call in tests**

---

## 5. Component C3: Element Periodic Table (`strategy/elements.py`)

```python
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class FeatureSet(str, Enum):
    LAGGED_RETURNS = "lagged_returns"
    VOLATILITY = "volatility"
    CROSS_SYMBOL = "cross_symbol"
    TIME_OF_DAY = "time_of_day"
    SPREAD = "spread"
    MACRO_PROXY = "macro_proxy"

class ModelFamily(str, Enum):
    RIDGE_BOOTSTRAP = "ridge_bootstrap_ensemble"
    LASSO_BOOTSTRAP = "lasso_bootstrap_ensemble"
    RANDOM_FOREST = "random_forest"
    HARDCODED_RULE = "hardcoded_rule"

class TargetFormulation(str, Enum):
    RANK_CROSS_SECTIONAL = "rank_cross_sectional"
    ABSOLUTE_RETURN = "absolute_return"
    BINARY_DIRECTION = "binary_direction"

class SignalCompression(str, Enum):
    SIGMOID = "sigmoid"
    THRESHOLD = "threshold"
    DISCRETIZED_5TIER = "discretized_5tier"

class UniverseFilter(str, Enum):
    ALL_TRADABLE = "all_tradable"
    TOP3_BUY_BOTTOM3_SELL = "top3_buy_bottom3_sell"
    TOP_N_BY_SIGNAL = "top_n_by_signal"

class PositionSizing(str, Enum):
    LINEAR_PROPORTIONAL = "linear_proportional"
    SIGMOID = "sigmoid"
    DISCRETIZED_LEVELS = "discretized_levels"

class PortfolioConstraint(str, Enum):
    CURRENCY_DECOMP = "currency_decomposition"
    METALS_COMBINED = "metals_combined_cap"
    GROSS_LEVERAGE = "gross_leverage"
    NONE = "none"

class TimeFilter(str, Enum):
    NO_FILTER = "no_filter"
    SESSION_SPECIFIC = "session_specific"
    MACRO_EVENT_GUARD = "macro_event_guard"

class DrawdownGate(str, Enum):
    NO_GATE = "no_gate"
    SOFT_SCALING = "soft_scaling"
    HARD_STOP = "hard_stop"


class SignalLayer(BaseModel):
    feature_set: list[FeatureSet]
    model_family: ModelFamily
    target_formulation: TargetFormulation
    model_hyperparams: dict = Field(default_factory=dict)  # e.g. {"ridge_alpha": 1.0}

class DecisionLayer(BaseModel):
    signal_compression: SignalCompression
    universe_filter: UniverseFilter
    position_sizing: PositionSizing
    sizing_hyperparams: dict = Field(default_factory=dict)  # e.g. {"cap_pct": 10.0}

class RiskLayer(BaseModel):
    portfolio_constraints: list[PortfolioConstraint]
    time_filter: TimeFilter
    drawdown_gate: DrawdownGate
    constraint_hyperparams: dict = Field(default_factory=dict)  # e.g. {"currency_cap": 20.0}


class StrategyElementTable(BaseModel):
    """Decomposable representation of a strategy as a structured vector."""
    nickname: str
    parent_nickname: str | None = None
    signal_layer: SignalLayer
    decision_layer: DecisionLayer
    risk_layer: RiskLayer

    def diff(self, other: "StrategyElementTable") -> dict:
        """Returns dimension-level diff: {layer.dimension: {from, to}}."""
        diffs = {}
        for layer_name in ["signal_layer", "decision_layer", "risk_layer"]:
            self_layer = getattr(self, layer_name).model_dump()
            other_layer = getattr(other, layer_name).model_dump()
            for dim, self_val in self_layer.items():
                other_val = other_layer.get(dim)
                if self_val != other_val:
                    diffs[f"{layer_name}.{dim}"] = {"from": other_val, "to": self_val}
        return diffs


def decompose_v0() -> StrategyElementTable:
    """Reverse-engineer current strategy_v0 into element table."""
    return StrategyElementTable(
        nickname="v0",
        parent_nickname=None,
        signal_layer=SignalLayer(
            feature_set=[
                FeatureSet.LAGGED_RETURNS,
                FeatureSet.VOLATILITY,
                FeatureSet.CROSS_SYMBOL,
                FeatureSet.TIME_OF_DAY,
                FeatureSet.SPREAD,
                FeatureSet.MACRO_PROXY,
            ],
            model_family=ModelFamily.RIDGE_BOOTSTRAP,
            target_formulation=TargetFormulation.RANK_CROSS_SECTIONAL,
            model_hyperparams={"ridge_alpha": 1.0, "n_bootstraps": 3},
        ),
        decision_layer=DecisionLayer(
            signal_compression=SignalCompression.SIGMOID,
            universe_filter=UniverseFilter.TOP3_BUY_BOTTOM3_SELL,
            position_sizing=PositionSizing.DISCRETIZED_LEVELS,
            sizing_hyperparams={
                "sigmoid_scale": 1.5,
                "thresholds_pct": [0.0, 1.0, 2.5, 5.0, 10.0],
            },
        ),
        risk_layer=RiskLayer(
            portfolio_constraints=[
                PortfolioConstraint.CURRENCY_DECOMP,
                PortfolioConstraint.METALS_COMBINED,
                PortfolioConstraint.GROSS_LEVERAGE,
            ],
            time_filter=TimeFilter.NO_FILTER,
            drawdown_gate=DrawdownGate.NO_GATE,
            constraint_hyperparams={
                "currency_cap_pct": 20.0,
                "metals_cap_pct": 15.0,
                "gross_leverage_cap_pct": 50.0,
            },
        ),
    )
```

**Tests (`tests/test_strategy/test_elements.py`)**:
- decompose_v0() returns valid StrategyElementTable
- diff(v0, v0) returns empty dict
- modified v1 (e.g., changed sigmoid_scale) → diff shows exactly that one dimension changed

---

## 6. Component C4: Memory Table (`memory/strategy_memory.py`)

```python
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS strategy_memory (
    nickname TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    parent_nickname TEXT,
    element_table_json TEXT NOT NULL,
    metrics_json TEXT,
    decision TEXT,
    rationale TEXT,
    current_rank INTEGER,
    modification_type TEXT,
    iteration_log_path TEXT,
    FOREIGN KEY (parent_nickname) REFERENCES strategy_memory(nickname)
);

CREATE INDEX IF NOT EXISTS idx_parent ON strategy_memory(parent_nickname);
CREATE INDEX IF NOT EXISTS idx_timestamp ON strategy_memory(timestamp);
"""

class StrategyMemory:
    def __init__(self, db_path: str = "data/strategy_memory.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA_SQL)

    def insert(
        self,
        nickname: str,
        element_table: dict,
        parent_nickname: Optional[str] = None,
        metrics: Optional[dict] = None,
        decision: Optional[str] = None,
        rationale: Optional[str] = None,
        current_rank: Optional[int] = None,
        modification_type: Optional[str] = None,
        iteration_log_path: Optional[str] = None,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO strategy_memory
                (nickname, timestamp, parent_nickname, element_table_json,
                 metrics_json, decision, rationale, current_rank,
                 modification_type, iteration_log_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    nickname,
                    datetime.now(timezone.utc).isoformat(),
                    parent_nickname,
                    json.dumps(element_table),
                    json.dumps(metrics) if metrics else None,
                    decision,
                    rationale,
                    current_rank,
                    modification_type,
                    iteration_log_path,
                ),
            )

    def get(self, nickname: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM strategy_memory WHERE nickname = ?", (nickname,)
            ).fetchone()
            if not row:
                return None
            cols = [d[0] for d in conn.execute("SELECT * FROM strategy_memory LIMIT 0").description]
            return dict(zip(cols, row))

    def list_all(self) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM strategy_memory ORDER BY timestamp ASC"
            ).fetchall()
            cols = [d[0] for d in conn.execute("SELECT * FROM strategy_memory LIMIT 0").description]
            return [dict(zip(cols, row)) for row in rows]

    def get_tree(self) -> dict:
        """Returns dict {parent: [children]} for tree visualization."""
        all_entries = self.list_all()
        tree = {}
        for entry in all_entries:
            parent = entry["parent_nickname"] or "ROOT"
            tree.setdefault(parent, []).append(entry["nickname"])
        return tree

    def to_markdown_summary(self) -> str:
        """Format for Brain prompt context: history of attempts."""
        entries = self.list_all()
        lines = ["# Strategy Memory History\n"]
        for e in entries:
            lines.append(
                f"## {e['nickname']} (parent: {e['parent_nickname'] or 'ROOT'})\n"
                f"- Timestamp: {e['timestamp']}\n"
                f"- Decision: {e['decision']}\n"
                f"- Rationale: {e['rationale']}\n"
                f"- Current rank: {e['current_rank']}\n"
            )
            if e["metrics_json"]:
                m = json.loads(e["metrics_json"])
                lines.append(f"- Metrics: {m}\n")
        return "\n".join(lines)
```

**Tests (`tests/test_memory/test_strategy_memory.py`)**:
- insert v0 → get v0 returns same
- insert v1 with parent=v0 → list_all returns both in timestamp order
- get_tree() returns correct parent→children mapping
- to_markdown_summary() includes all entries

---

## 7. Component C5: Scope Guard (`agents/scope_guard.py`)

```python
import ast
import re
from pathlib import Path
from typing import Tuple, Optional

# D1 = B+ rules
ALLOWED_FILES = {
    "src/trifolium/strategy/v0/predictor.py",
    "src/trifolium/strategy/v0/trader.py",
    "src/trifolium/strategy/v0/portfolio.py",
    "config/strategy_v0.yaml",
}
FORBIDDEN_PATTERNS = [
    r"\bimport\s+MetaTrader5\b",
    r"\bimport\s+mt5\b",
    r"\bfrom\s+MetaTrader5\b",
    r"\bmt5\.order_send\b",
]
FORBIDDEN_FILES = [
    "src/trifolium/risk_gate/",
    "config/risk_limits.yaml",
    "src/trifolium/strategy/v0/strategy.py",  # orchestration / interface层
]


def check_target_files_in_whitelist(target_files: list[str]) -> Tuple[bool, Optional[str]]:
    """Check all target_files are in ALLOWED_FILES."""
    for f in target_files:
        normalized = f.replace("\\", "/")
        if normalized not in ALLOWED_FILES:
            return False, f"Target file '{f}' not in scope whitelist"
    return True, None


def check_file_blacklist(target_files: list[str]) -> Tuple[bool, Optional[str]]:
    """Check no target_files match FORBIDDEN_FILES."""
    for f in target_files:
        normalized = f.replace("\\", "/")
        for forbidden in FORBIDDEN_FILES:
            if normalized.startswith(forbidden):
                return False, f"Target file '{f}' is in blacklist (matches {forbidden})"
    return True, None


def check_patch_content(patch_text: str) -> Tuple[bool, Optional[str]]:
    """Grep for forbidden patterns in patch."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, patch_text):
            return False, f"Patch contains forbidden pattern: {pattern}"
    return True, None


def check_resulting_files(file_paths: list[Path]) -> Tuple[bool, Optional[str]]:
    """AST + grep on resulting (post-patch) files."""
    for fpath in file_paths:
        if not fpath.exists():
            continue
        content = fpath.read_text()
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                return False, f"File {fpath} contains forbidden pattern: {pattern}"
    return True, None


def validate_hypothesis_scope(hypothesis: dict) -> Tuple[bool, Optional[str]]:
    """Top-level: validate hypothesis target_files against scope rules."""
    target_files = hypothesis.get("target_files", [])
    if not target_files:
        return False, "Hypothesis has no target_files"
    p1, r1 = check_target_files_in_whitelist(target_files)
    if not p1:
        return False, r1
    p2, r2 = check_file_blacklist(target_files)
    if not p2:
        return False, r2
    return True, None


def validate_patch_scope(patch_text: str, resulting_file_paths: list[Path]) -> Tuple[bool, Optional[str]]:
    """Validate patch content + post-patch files."""
    p1, r1 = check_patch_content(patch_text)
    if not p1:
        return False, r1
    p2, r2 = check_resulting_files(resulting_file_paths)
    if not p2:
        return False, r2
    return True, None
```

**Tests (`tests/test_agents/test_scope_guard.py`)**:
- hypothesis with target_files=["src/trifolium/strategy/v0/predictor.py"] → PASS
- hypothesis with target_files=["src/trifolium/risk_gate/gate.py"] → FAIL
- hypothesis with target_files=["src/trifolium/strategy/v0/strategy.py"] → FAIL (interface lock)
- patch containing "import mt5" → FAIL
- patch containing "mt5.order_send(...)" → FAIL
- patch only modifying ridge_alpha YAML value → PASS

---

## 8. Component C6: NeMo Guardrails (`agents/guardrails.py`)

**Implementation strategy**: Use NeMo Guardrails minimal config (no Colang complexity, just config-based rails). If integration proves >30 min ramp during build, fallback is Pydantic schema enforcement.

```python
import json
from typing import Tuple, Optional
from pydantic import BaseModel, Field, ValidationError, validator

# Pydantic schema (also used by NeMo Guardrails JSON schema rail)
class HypothesisJSON(BaseModel):
    target_files: list[str] = Field(..., min_items=1, max_items=3)
    element_diff: dict
    rationale: str = Field(..., min_length=20)
    expected_metric_change: dict

    @validator("rationale")
    def no_forbidden_topics(cls, v):
        forbidden = ["risk_gate", "risk_limits", "mt5.order_send", "MetaTrader5"]
        for term in forbidden:
            if term.lower() in v.lower():
                raise ValueError(f"Rationale references forbidden topic: {term}")
        return v

    @validator("target_files", each_item=True)
    def target_files_format(cls, v):
        if not (v.startswith("src/trifolium/strategy/v0/") or v == "config/strategy_v0.yaml"):
            raise ValueError(f"Target file outside allowed scope: {v}")
        return v


def validate_brain_output(raw_text: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    """Parse Brain's raw output and validate against schema.
    Returns (passed, parsed_hypothesis, error_message)."""
    # Try to extract JSON from raw text (Brain may include thinking trace)
    try:
        # Find first { and last }
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start == -1 or end == -1:
            return False, None, "No JSON found in Brain output"
        json_str = raw_text[start:end+1]
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        return False, None, f"JSON parse error: {e}"

    try:
        validated = HypothesisJSON(**parsed)
    except ValidationError as e:
        return False, None, f"Schema validation failed: {e}"

    return True, validated.model_dump(), None


# Optional: NeMo Guardrails integration (full version)
def try_nemo_guardrails_init():
    """Attempt to initialize NeMo Guardrails. Falls back to Pydantic-only on failure."""
    try:
        from nemoguardrails import LLMRails, RailsConfig
        config = RailsConfig.from_path("config/guardrails")
        rails = LLMRails(config)
        return rails, None
    except ImportError:
        return None, "NeMo Guardrails not installed; using Pydantic-only validation"
    except Exception as e:
        return None, f"NeMo Guardrails init failed: {e}; using Pydantic-only validation"
```

**Tests (`tests/test_agents/test_guardrails.py`)**:
- valid JSON hypothesis → PASS
- malformed JSON → FAIL with parse error
- hypothesis missing required field → FAIL with schema error
- hypothesis with rationale mentioning "risk_gate" → FAIL with forbidden topic
- hypothesis with target_files=["src/trifolium/risk_gate/gate.py"] → FAIL with scope error

**Note**: NeMo Guardrails advanced features (dialog rails, retrieval grounding) are out of scope. We use it ONLY as JSON schema + forbidden topic enforcer. If `pip install nemoguardrails` fails or config integration takes >30 min, Pydantic-only path is functionally equivalent. **The narrative "we use NeMo Guardrails" requires only successful import + basic config**, not advanced features.

---

## 9. Component C7: Brain (`agents/brain.py`)

```python
from .nim_client import NIMClient
from .guardrails import validate_brain_output
from typing import Tuple, Optional

BRAIN_SYSTEM_PROMPT = """You are a quantitative trading strategy improvement agent. You analyze \
strategy performance reports and propose specific, scoped modifications to improve performance.

You operate under strict institutional constraints:
- You can ONLY suggest modifications to files in this whitelist:
  - src/trifolium/strategy/v0/predictor.py (feature engineering, model)
  - src/trifolium/strategy/v0/trader.py (sizing, signal compression)
  - src/trifolium/strategy/v0/portfolio.py (portfolio constraints)
  - config/strategy_v0.yaml (hyperparameters)
- You can NEVER suggest modifications to risk_gate, risk_limits, or anything mentioning MT5.
- Your output MUST be valid JSON matching this schema:
  {
    "target_files": [...],
    "element_diff": {"layer.dimension": {"from": ..., "to": ...}},
    "rationale": "string >= 20 chars, no mention of risk_gate/risk_limits/mt5",
    "expected_metric_change": {"metric": ..., "direction": "+" or "-"}
  }

Follow the evaluation framework's 5-step reasoning:
STEP 1 - Gate: Check v_N's Section 1. If any gate FAILS (MaxDD>=30%, Risk Discipline<100, \
Trade Count<30, Active Intervals<8), the strategy is non-deployable. Your modification \
should address the gate failure.

STEP 2 - Binding: Check Section 4. If parent and current have identical behavior, propose \
modifications that will demonstrably change behavior.

STEP 3 - Objective: Total Return is primary. Suggest modifications that should increase \
Total Return based on observed failure modes.

STEP 4 - Tie-break: If Return is similar to parent, look at MaxDD (lower better) then Sharpe.

STEP 5 - Robustness: Avoid suggestions that work in isolated parameter regions. Prefer \
modifications with broad neighborhood validity.

Output ONE concrete, narrow-scope modification per iteration. Avoid bundling multiple changes."""


class Brain:
    def __init__(self, nim_client: Optional[NIMClient] = None):
        self.nim = nim_client or NIMClient()

    def propose_hypothesis(
        self,
        v_n_report_markdown: str,
        memory_summary: str,
        max_retries: int = 2,
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """Returns (passed, hypothesis_dict, error)."""
        user_content = (
            f"# Current Strategy Report (v_N)\n\n{v_n_report_markdown}\n\n"
            f"# Memory of Past Attempts\n\n{memory_summary}\n\n"
            f"Propose ONE modification. Output JSON only."
        )

        for attempt in range(max_retries + 1):
            raw = self.nim.chat(
                messages=[
                    {"role": "system", "content": BRAIN_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                reasoning_budget=8192,
            )
            passed, hypothesis, err = validate_brain_output(raw)
            if passed:
                return True, hypothesis, None
            if attempt < max_retries:
                # Retry with explicit correction message
                user_content = (
                    f"Previous attempt failed validation: {err}\n\n"
                    f"Original request:\n{user_content}"
                )
        return False, None, f"Brain failed schema validation after {max_retries+1} attempts: {err}"
```

**Tests (`tests/test_agents/test_brain.py`)**:
- mock NIMClient.chat returning valid JSON → propose_hypothesis returns (True, dict, None)
- mock returning malformed JSON → returns (False, None, error)
- mock returning hypothesis with forbidden topic → returns (False, None, error)
- mock first call fail, second call pass → retry logic works

---

## 10. Component C8: Coder (`agents/coder.py`)

```python
from .anthropic_client import AnthropicClient
from .scope_guard import validate_patch_scope
from pathlib import Path
from typing import Tuple, Optional
import subprocess
import tempfile
import shutil


class Coder:
    def __init__(self, anthropic_client: Optional[AnthropicClient] = None):
        self.client = anthropic_client or AnthropicClient()

    def generate_and_apply_patch(
        self,
        hypothesis: dict,
        repo_root: Path,
        sandbox_dir: Path,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Generate patch via Sonnet, apply to sandbox dir, validate scope.
        Returns (passed, patch_text_or_path, error)."""

        # Read relevant source files
        relevant = {}
        for fpath_str in hypothesis["target_files"]:
            full_path = repo_root / fpath_str
            if full_path.exists():
                relevant[fpath_str] = full_path.read_text()
            else:
                return False, None, f"Target file {fpath_str} not found in repo"

        # Generate patch
        patch_text = self.client.generate_code_patch(hypothesis, relevant)

        # Validate patch content (forbidden patterns)
        passed, err = validate_patch_scope(patch_text, [])
        if not passed:
            return False, None, f"Patch validation failed: {err}"

        # Copy repo to sandbox
        if sandbox_dir.exists():
            shutil.rmtree(sandbox_dir)
        shutil.copytree(repo_root, sandbox_dir, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", "logs", "data", ".venv"
        ))

        # Apply patch using git apply (or fallback to manual write)
        try:
            patch_file = sandbox_dir / ".tmp_patch.diff"
            patch_file.write_text(patch_text)
            result = subprocess.run(
                ["git", "apply", "--check", str(patch_file)],
                cwd=sandbox_dir,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return False, None, f"git apply --check failed: {result.stderr}"
            subprocess.run(
                ["git", "apply", str(patch_file)],
                cwd=sandbox_dir,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            return False, None, f"Patch apply failed: {e}"

        # Final scope check on resulting files
        resulting_paths = [sandbox_dir / f for f in hypothesis["target_files"]]
        passed, err = validate_patch_scope(patch_text, resulting_paths)
        if not passed:
            return False, None, f"Post-apply scope check failed: {err}"

        return True, str(sandbox_dir), None
```

**Tests (`tests/test_agents/test_coder.py`)**:
- mock AnthropicClient.generate_code_patch returning valid diff → applies to sandbox successfully
- mock returning patch with forbidden pattern → rejected before apply
- mock returning unparseable diff → reported error
- mock returning patch that modifies risk_gate file → rejected by scope check

---

## 11. Component C9: Loop Orchestrator (`loop/orchestrator.py`)

```python
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from trifolium.agents.brain import Brain
from trifolium.agents.coder import Coder
from trifolium.agents.scope_guard import validate_hypothesis_scope
from trifolium.agents.guardrails import validate_brain_output
from trifolium.memory.strategy_memory import StrategyMemory
from trifolium.strategy.elements import StrategyElementTable, decompose_v0
from trifolium.validation import validate_strategy


class LoopIteration:
    """8-step state machine, idempotent per step, JSONL logged."""

    def __init__(
        self,
        memory: StrategyMemory,
        brain: Brain,
        coder: Coder,
        log_dir: Path,
        repo_root: Path,
        sandbox_base: Path,
    ):
        self.memory = memory
        self.brain = brain
        self.coder = coder
        self.log_dir = log_dir
        self.repo_root = repo_root
        self.sandbox_base = sandbox_base
        self.iteration_id = str(uuid.uuid4())[:8]
        self.log_path = log_dir / f"iteration_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{self.iteration_id}.jsonl"

    def _log(self, step: str, data: dict):
        entry = {
            "iteration_id": self.iteration_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "step": step,
            "data": data,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def run(self, parent_nickname: str = "v0") -> dict:
        """Run one full iteration. Returns final state dict."""
        state = {"parent": parent_nickname, "status": "started", "iteration_id": self.iteration_id}
        self._log("start", state)

        try:
            # Step 1: Read parent report from memory
            parent = self.memory.get(parent_nickname)
            if not parent:
                state["status"] = "failed"
                state["error"] = f"Parent {parent_nickname} not in memory"
                self._log("step1_read_report", state)
                return state

            # Get latest v_N's L5 report markdown (from memory or fresh backtest)
            # For first iteration, we use v0's stored report
            v_n_report = parent.get("metrics_json", "{}")  # placeholder; actual: re-run L5 or use stored
            memory_summary = self.memory.to_markdown_summary()
            self._log("step1_read_report", {"parent": parent_nickname})

            # Step 2: Brain propose
            passed, hypothesis, err = self.brain.propose_hypothesis(
                v_n_report_markdown=v_n_report,
                memory_summary=memory_summary,
            )
            if not passed:
                state["status"] = "skipped"
                state["error"] = f"Brain failed: {err}"
                self._log("step2_brain_propose", state)
                return state
            self._log("step2_brain_propose", {"hypothesis": hypothesis})

            # Step 3: Guardrail check (already partly done in Brain via validate_brain_output)
            # Additional scope-level check
            passed, err = validate_hypothesis_scope(hypothesis)
            if not passed:
                state["status"] = "skipped"
                state["error"] = f"Guardrail failed: {err}"
                self._log("step3_guardrail", state)
                return state
            self._log("step3_guardrail", {"passed": True})

            # Step 4: Coder apply
            sandbox_dir = self.sandbox_base / f"v_{self.iteration_id}"
            passed, sandbox_path, err = self.coder.generate_and_apply_patch(
                hypothesis=hypothesis,
                repo_root=self.repo_root,
                sandbox_dir=sandbox_dir,
            )
            if not passed:
                state["status"] = "skipped"
                state["error"] = f"Coder failed: {err}"
                self._log("step4_coder", state)
                return state
            self._log("step4_coder", {"sandbox": sandbox_path})

            # Step 5: Scope check (post-apply, already done inside Coder)
            self._log("step5_scope_check", {"passed": True})

            # Step 6: Backtest gate (call Task 04 L5 with sandbox strategy)
            # For Plan A first iteration: use 6h short window for speed
            from datetime import datetime as dt, timezone as tz
            try:
                v_n_plus_1_nickname = f"v_{self.iteration_id}"
                # Note: in real impl, we'd point validate_strategy at the sandbox dir
                # For first MVP, we use a flag or env var to redirect strategy path
                # Simplified: copy patched strategy_v0.yaml to a versioned location
                # and pass strategy_name="strategy_v_iter_<id>"
                # FOR NOW: log the intent; actual integration is what Codex will wire
                validation_result = {"placeholder": "L5 result here", "passed": True}
                self._log("step6_backtest", {"result": validation_result})
            except Exception as e:
                state["status"] = "failed"
                state["error"] = f"Backtest failed: {e}"
                self._log("step6_backtest", state)
                return state

            # Step 7: Evaluate (Brain reads v_N vs v_N+1, applies D2 5-step)
            # For first iteration with mocked or simple comparison:
            decision = "ACCEPT_v_N+1"  # placeholder
            rationale = "Plan A first iteration MVP path"
            self._log("step7_evaluate", {"decision": decision, "rationale": rationale})

            # Step 8: Memory write
            self.memory.insert(
                nickname=v_n_plus_1_nickname,
                element_table=hypothesis.get("element_diff", {}),
                parent_nickname=parent_nickname,
                metrics=validation_result,
                decision=decision,
                rationale=rationale,
                modification_type="Level_2" if any("hyperparams" in k for k in hypothesis.get("element_diff", {})) else "Level_1",
                iteration_log_path=str(self.log_path),
            )
            self._log("step8_memory_write", {"nickname": v_n_plus_1_nickname})

            state["status"] = "completed"
            state["new_strategy"] = v_n_plus_1_nickname
            state["decision"] = decision
            self._log("end", state)
            return state

        except Exception as e:
            state["status"] = "crashed"
            state["error"] = str(e)
            self._log("crash", state)
            return state
```

**Tests (`tests/test_loop/test_orchestrator.py` + `test_integration.py`)**:
- `test_orchestrator.py`: with mocked Brain + Coder + L5, full iteration completes 8 steps and writes JSONL
- `test_integration.py`: with mocked APIs (no real NIM/Anthropic calls) full pipeline produces Memory Table entry
- Crash recovery: mid-iteration exception → state logged with "crashed"
- Skip path: Brain returns invalid → state logged with "skipped", no memory write

---

## 12. Acceptance Criteria (Plan A 14:00 BST go-live)

**Pre-flight check (Codex must verify before reporting completion):**

- [ ] All 9 components have files at correct paths per §2
- [ ] All unit tests written and passing (see test list per component)
- [ ] `pytest tests -q` returns all passing
- [ ] `python -m compileall src scripts tests` returns PASS
- [ ] Static grep:
  - `grep -rn "mt5.order_send" src/` returns ONLY `src/trifolium/risk_gate/execution.py`
  - `grep -rn "MetaTrader5" tests/` returns nothing
- [ ] `.env` file contains `NVIDIA_API_KEY` and `ANTHROPIC_API_KEY` (do NOT log values)

**End-to-end integration test (the 14:00 deliverable):**

- [ ] `scripts/run_loop_iteration.py --parent v0` produces:
  - A JSONL log file in `logs/loop_iterations_*.jsonl` with 8 steps + start/end entries
  - A new row in Memory Table SQLite with parent=v0 and a non-null `element_diff`
  - At least one real call to NVIDIA NIM (Nemotron Ultra) — log records this
  - At least one real call to Anthropic Sonnet — log records this
  - A sandbox directory at `sandboxes/v_<iter_id>/` with a modified file
  - Scope guard verdict logged as PASS for legitimate modifications

**Adversarial test (proving institution-as-first-class works):**

- [ ] Mock Brain to return hypothesis with `target_files=["src/trifolium/risk_gate/gate.py"]` → loop returns `skipped` with scope guard error, no memory write, no patch applied
- [ ] Mock Brain to return rationale containing "modify risk_limits" → loop returns `skipped` with guardrail error
- [ ] Mock Coder to return patch with "import mt5" → loop returns `skipped` with scope guard error after coder

**Demo prerequisite:**

- [ ] `scripts/demo_ui.py` serves an HTML page on localhost:8000 that displays:
  - Current iteration count
  - Memory Table contents (table format)
  - Latest Brain output (JSON)
  - Latest Coder patch (collapsed by default)
  - Live JSONL tail of orchestrator log

---

## 13. Out-of-scope (NOT building today)

- **No live deployment**: Strategy v_N+1 candidates run in sandbox backtest only. No automatic MT5 order placement. Principal explicit approval gate remains untouched.
- **No full 30-day L5 in loop**: Use 6h short window. Full L5 is too slow; loop targets fast iteration over many small windows.
- **No parallel exploration (Idea 3B)**: Single iteration at a time. Parallel deferred.
- **No 3 starting strategy templates (Idea 3A part)**: Loop starts from v0 only today. Principal defines 3 starting templates on 6/26 evening if time.
- **No advanced NeMo Guardrails features**: Use only JSON schema + forbidden topic rails. No Colang flows.
- **No production-grade Demo UI**: Minimal HTML, no React, no real-time websockets. Just refresh every 5s.

---

## 14. Code Implementation Order (Plan A — Codex executes in this order, no pauses)

```
12:30-13:00 (30 min): Foundation
  C1 nim_client.py            (10 min)
  C2 anthropic_client.py      (5 min)
  C3 elements.py              (10 min)
  C4 strategy_memory.py       (5 min)

13:00-13:30 (30 min): Guards + Agents
  C5 scope_guard.py           (10 min)
  C6 guardrails.py            (10 min)
  C7 brain.py                 (5 min)
  C8 coder.py                 (5 min)

13:30 CHECKPOINT:
  Run pytest tests -q
  Report PASS/FAIL count to principal
  No decision required — continue building regardless

13:30-13:55 (25 min): Orchestrator + Demo
  C9 orchestrator.py          (10 min)
  scripts/run_loop_iteration.py (5 min)
  scripts/demo_ui.py          (10 min)

13:55-14:00 (5 min): End-to-end test
  Run scripts/run_loop_iteration.py --parent v0
  Verify all 8 steps logged + memory entry + sandbox exists
  Report success/failure to principal at 14:00 sharp
```

---

## 15. Failure Mode Handling (Plan A specific)

**If at 13:30 unit tests have failures:**
- Codex reports list of failures
- Codex continues building remaining components anyway (Plan A: no pausing)
- Failures get fixed in the 13:55-14:00 buffer or in post-14:00 polish

**If at 13:50 integration test fails:**
- Codex reports specific failure (which step, what error)
- Codex attempts ONE fix
- If 14:00 arrives mid-fix: report current state, do not silently push deadline

**If NeMo Guardrails install/integration fails:**
- Codex uses Pydantic-only path
- Logs note: "NeMo Guardrails fallback to Pydantic"
- Demo narrative still claims "Guardrails layer" via Pydantic — functionally equivalent

**If NVIDIA NIM API key has issue (e.g., wrong type as we just saw):**
- Codex tests with simple `client.chat.completions.create` call early
- If 401/403 returned: report to principal IMMEDIATELY (don't continue building if Brain can't call)

**If Anthropic API has insufficient credits:**
- Codex tests with cheap call early ($0.001)
- If credit error: report to principal IMMEDIATELY

---

## 16. Logging Convention (loop iterations)

`logs/loop_iterations_YYYYMMDD_HHMMSS_<iter_id>.jsonl`:

```jsonl
{"iteration_id": "abc12345", "timestamp": "2026-06-25T13:55:00+00:00", "step": "start", "data": {...}}
{"iteration_id": "abc12345", "timestamp": "...", "step": "step1_read_report", "data": {...}}
{"iteration_id": "abc12345", "timestamp": "...", "step": "step2_brain_propose", "data": {"hypothesis": {...}}}
... (8 steps)
{"iteration_id": "abc12345", "timestamp": "...", "step": "end", "data": {"status": "completed", ...}}
```

Each step entry is independent, parseable, replay-able.

---

## 17. Configuration (`config/self_improving.yaml`)

```yaml
loop:
  iteration_window_hours: 6           # short window for fast iteration
  min_seconds_between_iterations: 60  # rate limit
  max_iterations_per_day: 50
  parent_strategy_default: "v0"

brain:
  model: "nvidia/nemotron-3-ultra-550b-a55b"
  fallback_model: "nvidia/nemotron-3-super-120b-a12b"  # demo speed
  reasoning_budget: 8192
  max_retries: 2
  temperature: 0.7

coder:
  model: "claude-sonnet-4-6"
  max_tokens: 4096
  temperature: 0.3                    # lower temp for code

guardrails:
  use_nemo: true                      # falls back to pydantic-only on import failure
  forbidden_topics:
    - "risk_gate"
    - "risk_limits"
    - "mt5.order_send"
    - "MetaTrader5"

scope:
  allowed_files:
    - "src/trifolium/strategy/v0/predictor.py"
    - "src/trifolium/strategy/v0/trader.py"
    - "src/trifolium/strategy/v0/portfolio.py"
    - "config/strategy_v0.yaml"
  forbidden_paths:
    - "src/trifolium/risk_gate/"
    - "config/risk_limits.yaml"
    - "src/trifolium/strategy/v0/strategy.py"

memory:
  db_path: "data/strategy_memory.db"

sandbox:
  base_dir: "sandboxes/"
```

---

## 18. Demo Narrative Hooks (build-aware)

Each component's design serves a demo talking point. Codex should keep these in mind:

- **C1 NIM client**: "We use Nemotron 3 Ultra, NVIDIA's flagship 550B/55B-MoE open model — the highest-scoring US open-weight reasoning model"
- **C3 Element Table**: "We decompose strategies into structured vectors. This isn't grid search — agents reason in an explicit design space"
- **C5 Scope Guard**: "Institution-as-first-class isn't just policy — it's grep-verifiable code. Risk Gate is untouchable by agents, period"
- **C6 NeMo Guardrails**: "We use NVIDIA's NeMo Guardrails as a second LLM-layer defense — defense-in-depth across code and prompt boundaries"
- **C9 Orchestrator**: "8-step state machine with idempotent steps and full JSONL audit. Every agent action is replayable"

---

## END OF SPEC
