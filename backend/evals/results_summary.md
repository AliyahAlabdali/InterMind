# Verified results summary

| Metric | Result | Sample | What it means |
| --- | ---: | ---: | --- |
| Follow-up F1, final routed decision | **0.8852** | 90 labeled cases | Agreement with frozen human follow-up decisions, summarized by F1 |
| Evidence-backed claims, fully supported | **90.20%** | 221/245 claims across 15 reports | Pooled share of reviewed report assertions supported by candidate answers |
| P95 response latency, server-side advance path | **3.834 s** | 100 live requests, 20 per job | 95th ordered answer-endpoint duration under the fixed fixture |

The follow-up result was recovered from validated outputs of an incomplete run under a separate v1.1 method. The claim result uses one human reviewer's AI-assisted, adopted final judgments under a retrospective v1.1a addendum, without a documented independent initial human review. The latency fixture measures backend processing, not browser-perceived speed or natural production-path latency. The five jobs and candidate personas were authored for evaluation, not sampled from real applicants.

[Measurement details](methodology.md) · [Evaluation overview](README.md)
