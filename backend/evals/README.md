# InterMind evaluation

Three measured results describe InterMind's follow-up routing, report claims, and answer-endpoint response time. They come from separately locked recovery, human-review, and live-latency records. The original final run was interrupted; no result is presented as a completed v1.0 evaluation.

| Portfolio metric | Result | Scope |
| --- | ---: | --- |
| Follow-up F1 | **0.8852** | InterMind's final route versus frozen human labels on 90 cases |
| Evidence-backed claims | **90.20%** | 221 fully supported report claims out of 245 reviewed claims |
| P95 response latency | **3.834 s** | Server-side answer endpoint, 100 live advance-path requests |

The claim verdicts were adopted by one human reviewer after AI-assisted review; they were not independent initial blind human ratings. The latency result measures a fixed advance-path fixture through the backend, not browser-perceived or natural production traffic latency. See [methodology](methodology.md) for the measurement boundaries and [results summary](results_summary.md) for the verified counts.
