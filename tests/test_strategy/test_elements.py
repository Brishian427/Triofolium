from __future__ import annotations

from trifolium.strategy.elements import SignalCompression, decompose_v0


def test_decompose_v0_returns_element_table():
    table = decompose_v0()
    assert table.nickname == "v0"
    assert table.decision_layer.signal_compression == SignalCompression.SIGMOID


def test_diff_detects_one_dimension():
    v0 = decompose_v0()
    v1 = v0.model_copy(deep=True)
    v1.decision_layer.sizing_hyperparams["sigmoid_scale"] = 1.2
    diff = v1.diff(v0)
    assert list(diff) == ["decision_layer.sizing_hyperparams"]

