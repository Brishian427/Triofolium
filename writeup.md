# Project Trifolium: A Self-Evolving Auto-Research System for Algorithmic Trading under Risk Governance

## Abstract

Project Trifolium is a self-evolving auto-research system for algorithmic trading under risk governance. It uses a multi-LLM agent loop to explore strategy design space, mutate candidates in sandboxes, evaluate them through an IMC-competition-validated D2 framework, and connect live execution to MT5 only through institutional controls. The result is not a claim of magic alpha. It is a working research process: candidate generation, sandboxed mutation, backtesting, gate-first evaluation, risk-governed execution, JSONL auditability, and post-incident attribution.

## 1. Motivation and Design Philosophy

Project Trifolium began as a transfer-learning experiment from IMC Prosperity 4 into the MOMQ Finals. In IMC, the most important lesson was that profitable competition systems often look less like pure prediction engines and more like control systems. A model can estimate the next price movement, but the system wins or loses through the rules that decide when to trust the estimate, how to size it, how to exit, and how to prevent a local optimization from breaking a global constraint.

That lesson shaped the MOMQ build. The competition setting was a virtual account near $1 million, 30:1 leverage, multi-asset access across FX, metals, and crypto, and rank-based scoring. The obvious path was to search for a high Sharpe strategy. We deliberately optimized for the Tech Prize instead: build an institution that can improve itself, explain itself, and survive contact with live execution. The core thesis was that architectural sophistication matters more than a single lucky strategy curve.

The phrase we used internally was: this is a control problem, not a prediction problem. The project therefore emphasizes risk governance, evaluation design, mutation boundaries, and audit logs. Strategy v0 was allowed to be weak. The institution around it was not.

## 2. Architecture

The full architecture is documented in [architecture.md](architecture.md). The self-evolving loop used an Architecture 5 Robust design. A navigator model handles triage and branch navigation. An architect model proposes candidate hypotheses. A coder model generates patches. A fallback path provides degraded-mode resilience when the stronger model path fails or times out.

The model roles were intentionally separated. The Navigator, based on the NVIDIA/Mistral Nemotron family, is meant for fast routing: is this a local parameter change, a structural change, or a dead branch? The Architect, using NVIDIA Nemotron Super 120B where available, is used for lower-frequency hypothesis generation. The Coder, Anthropic Sonnet, is used to convert a hypothesis into a patch. The fallback path exists because live systems cannot assume a perfect API day.

The loop does not modify production code directly. It operates through sandbox candidates and a scope guard. The guard is one of the most important parts of the system: self-evolution is only useful if it cannot self-modify into unsafe states. Risk Gate files, risk limits, and the live strategy interface are treated as institutional boundaries rather than strategy material.

To make exploration structured, we implemented an Element Periodic Table decomposition. A strategy is described through three layers: Signal, Decision, and Risk. Signal includes feature set, model family, and target formulation. Decision includes signal compression, universe filter, and position sizing. Risk includes portfolio constraints, time filters, and drawdown gates. This decomposition prevents the loop from seeing strategy mutation as a bag of arbitrary code edits.

Evaluation is handled by the D2 framework: a 9-section report with gate-first logic. The sections are Identity, Gate Check, Primary Objective, Secondary Metrics, Binding Check, Robustness, Regime Consistency, Failure Modes, Decision. The gate-first philosophy matters. If trade count, risk discipline, drawdown, or active intervals fail, secondary metrics cannot rescue the candidate. This avoids a common competition failure mode: optimizing whatever statistic is easiest to move.

## 3. Self-Evolving Loop: What We Found

Across Phase G, H, and I, we explored 8+ strategy candidates. The most useful discovery was negative in the scientific sense: strategy v0 had a marginal directional edge, but the edge magnitude was too close to transaction cost. The H2 strict candidate passed the hard D2 gates, showed roughly a 53% win rate, and was robust under perturbation, but the realized return was approximately flat after spread. This is not a parameter tuning problem. It is an architectural boundary.

The original strategy family used ridge bootstrap, cross-sectional ranking, and 15-minute FX signals. The loop tried to make it trade, then tried to make it robust, then tried to make it less overfit to forced participation. We learned that lowering thresholds can create activity without creating edge. Forced participation increased trade count but flattened conviction. A better version needed either a different target formulation, such as absolute forward return, or context features such as recent one-hour momentum and volatility.

One important meta-discovery was about evaluation itself. Before D2 was fully wired, the Brain repeatedly proposed confidence-threshold edits. That was Goodhart's Law in miniature: the system optimizes whatever report it sees. If the report only exposes old Filter 1/2/3 diagnostics, the Brain learns to manipulate those. Once D2 was implemented, the Brain had a richer objective: gates first, binding second, objective third, robustness as override. In a self-evolving loop, the evaluation report is not paperwork. It is the reward interface.

## 4. Live Deployment and Profit Harvester

The live deployment path used MT5 with a single Risk Gate protecting automated order submission. The Risk Gate records every order request, every check result, the final decision, and any MT5 response to JSONL. The exported demo data contains 12,619 logged Risk Gate decisions.

The deployed profit harvester was intentionally simple. It used principal-defined direction locks, fixed lot sizes, a $5 take-profit threshold, cooldown, and retrace-based re-entry. It polled at one-second cadence. This was not the self-evolving loop's final strategy. It was a live execution mechanism designed to test whether a small, rule-consistent executor could repeatedly harvest local movement under institutional governance.

The result was positive and auditable. The export attributes approximately +$494.98 realized PnL to `magic=10181` and `comment=profit_harvester`. The exact count depends on whether one counts deals, order pairs, or strategy lifecycle events, but the key point is attribution: automated harvester activity can be separated cleanly from manual/client-side activity by MT5 `magic` and `comment`.

The project also generated a full demo export package: MT5 history deals, MT5 order history, open positions, Risk Gate decisions, harvester key events, account state time series, and raw logs. This is important because live trading systems are often impossible to evaluate after the fact. Trifolium was designed to leave evidence.

## 5. Constitutional Design Refinements Discovered Live

Two design refinements emerged only during live operation.

First, rate limits must distinguish risk-increasing actions from risk-reducing actions. We observed that take-profit close orders can be blocked by a naive rate limiter when the harvesting window is saturated. That is institutionally wrong. A close or reduce-only order reduces exposure; throttling it can increase risk. The refinement is to exempt reduce-only orders from throttle checks while keeping hard-kills universal.

Second, session gates must not encode the operator's real-world calendar. At one point the system was silent for hours because a session gate mapped live trading to a human schedule. This is a subtle category error. A trading system should decide whether to act based on signal, cost, and risk, not on whether the principal is asleep or in an interview. If human availability matters, it belongs in an operator-protection layer, not in the alpha strategy.

Both refinements preserve the single-gatekeeper invariant. The point is not to remove governance. The point is to make governance semantically correct.

## 6. The Natural Experiment: Algorithmic versus Discretionary Execution

The final hours produced an uncomfortable but valuable natural experiment. The automated harvester followed its rules and produced positive realized PnL. The principal also traded manually under time pressure, using related directional theses but larger discretionary exposure. The manual path demonstrated that there was real exploitable movement, including a profitable XAGUSD discretionary edge earlier in the session, but recovery trading and oversized metals exposure produced a large floating loss.

The audit infrastructure made this distinction visible. Automated positions used `magic=10181` and explicit comments such as `profit_harvester`. Manual/client-side actions used `magic=0` and blank comments. This allowed us to separate automated system behavior from human override behavior instead of arguing from memory.

The architectural lesson is stark: principal-risk is system-risk. An institution that only constrains bot code is incomplete. If the human operator can override size, direction, and holding period under stress, then the institution's safety envelope still has a hole. The next system layer must protect the principal from the principal's own high-pressure override behavior.

This connects directly to the discretionary trading literature. Barber and Odean's "Trading Is Hazardous to Your Wealth" frames overtrading and behavioral bias as systematic risks. Lo's Adaptive Markets Hypothesis suggests that behavior, environment, and learning interact under stress. Trifolium observed the same thing in miniature: automation preserved rule adherence; discretionary intervention converted thesis into path-dependent exposure.

## 7. What We Would Build Next

The next layer is principal protection. Manual exposure caps should be enforced separately from bot exposure caps. Manual trades should be tagged, isolated, and excluded from automated take-profit unless explicitly opted in. Post-loss cooldowns should prevent recovery mode. Large metals trades should require confirmation, size limits, and trend context. In short, the Risk Gate should protect both the machine and the person operating the machine.

On the strategy side, the next target is absolute-return formulation. Cross-sectional rank helped structure FX decisions, but it may discard magnitude information. A candidate that predicts absolute forward return could size by expected edge over spread instead of relative rank. We would also add momentum context: recent one-hour growth, realized volatility, and distance from local extremes. Finally, we would move from a single 15-minute horizon to a multi-horizon ensemble across 15-minute, 1-hour, and 4-hour views.

On the self-evolution side, the D2 report should remain the Brain's contract. Every future loop iteration should consume the same machine-readable D2 JSON and produce a structured hypothesis tied to failed gates, weak binding, or robustness concerns.

## 8. Lessons Learned

From IMC, we brought the lesson that independent priors can beat circular estimation. In the option task, a constant sigma prior beat a more elaborate smile fit because the market-implied smile was itself circular. From MOMQ, we learned the analogous institutional rule: evaluation metric equals optimization target. A spec that is not implemented is not a spec. It is an invitation for the loop to optimize the wrong thing.

From live trading, we learned that small automated edge cannot rescue oversized manual exposure. The harvester worked, but it could not offset a late, large, discretionary metals position. From the incident, we learned the most important systems lesson of the project: in a human-in-the-loop trading institution, the human is part of the threat model.

Project Trifolium is therefore best understood not as a finished alpha engine, but as a working prototype of a trading institution. It generated strategies, evaluated them, rejected weak candidates, deployed a simple live executor, logged decisions, attributed outcomes, and learned from failure. That is exactly the kind of AI-native setup we set out to build.

## References

- IMC Prosperity 4 competition, 2026.
- Barber, B. and Odean, T. (2000). "Trading Is Hazardous to Your Wealth."
- Lo, A. (2004). "The Adaptive Markets Hypothesis."
- Goodhart, C. (1975). Goodhart's Law.
- NVIDIA NIM API documentation.
- Anthropic Claude API documentation.
