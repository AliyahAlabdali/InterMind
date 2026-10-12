# InterMind Evaluation Results

A summary of InterMind's performance across follow-up decisions, evidence-backed reporting, and backend response time.

## Verified Performance Metrics

| Metric | Result | Evaluation Sample |
|---|---:|---|
| **Follow-up F1** | **0.8852** | 90 labeled cases |
| **Evidence-backed Claims** | **90.20%** | 221 of 245 claims across 15 reports |
| **P95 Backend Latency** | **3.834 s** | 100 live requests |

## Understanding the Results

- **Follow-up F1:** Measures how well InterMind decides when an additional interview question is needed.
- **Evidence-backed Claims:** Measures the proportion of report statements fully supported by candidate answers.
- **P95 Backend Latency:** Indicates that 95% of measured backend requests completed within approximately 3.83 seconds under the tested conditions.

These results reflect controlled evaluations rather than overall hiring accuracy. Details about test design, data sources, review procedures, and limitations are available in the [Evaluation Methodology](methodology.md).

[Evaluation Overview](README.md)
