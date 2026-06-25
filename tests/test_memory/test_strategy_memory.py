from __future__ import annotations

from trifolium.memory import StrategyMemory


def test_strategy_memory_insert_get_tree_and_summary(tmp_path):
    memory = StrategyMemory(tmp_path / "memory.db")
    memory.insert(nickname="v0", element_table={"a": 1})
    memory.insert(nickname="v1", parent_nickname="v0", element_table={"b": 2}, metrics={"passed": True}, decision="KEEP")

    assert memory.get("v0")["nickname"] == "v0"
    assert [item["nickname"] for item in memory.list_all()] == ["v0", "v1"]
    assert memory.get_tree()["v0"] == ["v1"]
    assert "v1" in memory.to_markdown_summary()

