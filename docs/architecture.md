# Project Trifolium Architecture

This diagram reflects what was actually built during the MOMQ Finals Tech Prize effort: a self-improving research loop, a D2 evaluation layer, a Risk Gate protected MT5 execution path, and a live profit harvester with JSONL audit evidence.

```mermaid
graph TB
    subgraph "Principal Layer"
        P["Principal / Human Operator"]
        P -->|"direction locks + manual trades"| MT5["MT5 Terminal<br/>Account 10181"]
        P -->|"strategy thesis"| HarvConfig["Harvester Config"]
    end

    subgraph "Self-Improving Loop (Architecture 5 Robust)"
        Nav["Navigator<br/>Mistral Nemotron"]
        Arc["Architect<br/>NVIDIA Nemotron Super 120B"]
        Cod["Coder<br/>Anthropic Sonnet"]
        FB["Fallback<br/>Llama / Nano fallback path"]
        Guard["Scope Guard<br/>no risk_gate / live strategy mutation"]
        Sandbox["Sandbox Candidate"]

        Nav -->|"triage Level 1 / Level 2"| Arc
        Nav -.->|"degraded hypothesis path"| FB
        Arc -->|"hypothesis JSON"| Cod
        Cod -->|"unified diff patch"| Guard
        Guard -->|"approved patch"| Sandbox
    end

    subgraph "Evaluation (D2 Framework)"
        BT["Backtest Engine<br/>tick/bar replay"]
        D2["D2 9-Section Report<br/>Gate -> Objective -> Robustness"]
        Mem["Memory Table<br/>candidate history"]
        Elem["Element Periodic Table<br/>Signal / Decision / Risk"]

        Sandbox --> BT
        BT --> D2
        D2 -->|"ACCEPT / REJECT / KEEP"| Mem
        Elem -->|"structured strategy diff"| Arc
        Mem --> Nav
    end

    subgraph "Live Execution"
        Harv["Profit Harvester<br/>1s polling, $5 TP"]
        RG["Risk Gate<br/>single gatekeeper"]
        Exec["MT5 execution adapter<br/>only mt5.order_send path"]
        WD["Watchdog<br/>built for heartbeat restart; disabled during final manual-protection phase"]

        HarvConfig --> Harv
        Harv -->|"OrderRequest"| RG
        RG -->|"allow / reject + JSONL audit"| Exec
        Exec --> MT5
        WD -.->|"restart on stale heartbeat"| Harv
    end

    subgraph "Observability"
        JSONL["JSONL Audit Trail<br/>12,619 Risk Gate decisions"]
        Demo["Demo UI<br/>local dashboard"]
        Export["Demo Data Export<br/>MT5 history + logs"]
        Inc["Incident Report<br/>magic=0 vs magic=10181 attribution"]

        RG --> JSONL
        Harv --> JSONL
        MT5 --> Demo
        MT5 --> Export
        JSONL --> Export
        Export --> Inc
    end
```

## Invariants

- Automated orders are intended to pass through `risk_gate.submit_order`.
- Direct MT5 execution is isolated to the Risk Gate execution adapter.
- Self-improving loop candidates are generated in sandboxes and guarded against mutating live Risk Gate files.
- MT5 `magic` and `comment` fields are used to distinguish automated harvester actions from manual/client-side actions.
- The demo data export is read-only and does not submit, close, or modify live positions.
