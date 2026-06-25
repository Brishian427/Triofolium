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

CREATE INDEX IF NOT EXISTS idx_strategy_memory_parent ON strategy_memory(parent_nickname);
CREATE INDEX IF NOT EXISTS idx_strategy_memory_timestamp ON strategy_memory(timestamp);

