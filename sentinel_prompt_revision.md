Sentinel Prompt Revision — derived from Developer/Quant critique.

Critical gaps in current prompt:
1. No noise threshold parameters (Kalman filter was set at 0.0005 — destructive)
2. No minimum data requirements (N=1 trade is statistically meaningless)
3. JSON output too skeletal (1 field) — needs full settings block for auto-application
4. No time-scale compatibility checks between sentiment and price signals
5. No correlation analysis between sentiment weights and actual PnL
6. No explicit $1K/day throughput math
7. No integration with Developer/Quant agent's outputs

Solution: Complete rewrite with strict analysis structure and rich JSON output.
