from __future__ import annotations

from pathlib import Path

from trifolium.agents.coder import Coder


class FakeAnthropic:
    def __init__(self, patch: str):
        self.patch = patch

    def generate_code_patch(self, hypothesis, relevant):
        return self.patch


def _repo(tmp_path: Path) -> Path:
    target = tmp_path / "repo" / "src" / "trifolium" / "strategy" / "config"
    target.mkdir(parents=True)
    (target / "strategy_v0.yaml").write_text('destroyer_validation_sharpe_threshold: "0.0"\n', encoding="utf-8")
    return tmp_path / "repo"


def test_coder_applies_valid_patch_to_sandbox(tmp_path):
    repo = _repo(tmp_path)
    patch = (
        "diff --git a/src/trifolium/strategy/config/strategy_v0.yaml b/src/trifolium/strategy/config/strategy_v0.yaml\n"
        "--- a/src/trifolium/strategy/config/strategy_v0.yaml\n"
        "+++ b/src/trifolium/strategy/config/strategy_v0.yaml\n"
        "@@ -1 +1 @@\n"
        '-destroyer_validation_sharpe_threshold: "0.0"\n'
        '+destroyer_validation_sharpe_threshold: "-0.05"\n'
    )
    coder = Coder(FakeAnthropic(patch))
    passed, sandbox, error = coder.generate_and_apply_patch(
        hypothesis={"target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"]},
        repo_root=repo,
        sandbox_dir=tmp_path / "sandbox",
    )
    assert passed is True
    assert error is None
    assert "-0.05" in (Path(sandbox) / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml").read_text()


def test_coder_accepts_plain_unified_diff_in_code_fence(tmp_path):
    repo = _repo(tmp_path)
    patch = (
        "```diff\n"
        "--- a/src/trifolium/strategy/config/strategy_v0.yaml\n"
        "+++ b/src/trifolium/strategy/config/strategy_v0.yaml\n"
        "@@ -1 +1 @@\n"
        '-destroyer_validation_sharpe_threshold: "0.0"\n'
        '+destroyer_validation_sharpe_threshold: "-0.05"\n'
        "```"
    )
    coder = Coder(FakeAnthropic(patch), allow_fallback=True)
    passed, sandbox, error = coder.generate_and_apply_patch(
        hypothesis={"target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"]},
        repo_root=repo,
        sandbox_dir=tmp_path / "sandbox",
    )
    assert passed is True
    assert error is None
    assert coder.last_metadata["fallback_used"] is False
    assert "-0.05" in (Path(sandbox) / "src" / "trifolium" / "strategy" / "config" / "strategy_v0.yaml").read_text()


def test_coder_rejects_forbidden_patch(tmp_path):
    repo = _repo(tmp_path)
    coder = Coder(FakeAnthropic("diff --git a/x b/x\n+import mt5\n"))
    passed, _sandbox, error = coder.generate_and_apply_patch(
        hypothesis={"target_files": ["src/trifolium/strategy/config/strategy_v0.yaml"]},
        repo_root=repo,
        sandbox_dir=tmp_path / "sandbox",
    )
    assert passed is False
    assert "forbidden" in error
