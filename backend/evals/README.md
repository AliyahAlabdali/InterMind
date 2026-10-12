# InterMind Evaluation

Performance measurements across three areas of InterMind: adaptive follow-up decisions, evidence-backed reporting, and backend response latency.

## Performance Results

| Metric | Result | Evaluation Scope |
|---|---:|---|
| **Follow-up F1** | **0.8852** | 90 labeled test cases |
| **Evidence-backed Claims** | **90.20%** | 221 of 245 reviewed claims |
| **P95 Response Latency** | **3.834 s** | 100 live backend requests |

### Evaluation Notes

These metrics represent separate, controlled evaluations rather than a single measure of overall system accuracy.

Claim-support judgments were adopted by one reviewer following AI-assisted assessment. Latency was measured on a fixed backend request path, not as end-to-end browser response time.

For detailed measurement procedures, sample selection, and limitations, see the [Methodology](methodology.md) and [Results Summary](results_summary.md).
