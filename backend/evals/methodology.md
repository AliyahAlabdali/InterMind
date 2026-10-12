# Evaluation Methodology

InterMind was evaluated across three areas: follow-up decision quality, report evidence support, and backend response latency. Each metric was measured separately using defined test cases and verified results.

## 1. Follow-up F1

**Result: 0.8852 | 90 test cases**

InterMind's final follow-up decisions were compared against predefined human labels indicating whether an additional interview question was warranted.

F1 combines precision and recall into a single measure of decision quality. The evaluation used 90 saved predictions from a partially completed run, with the recovery and verification process documented under v1.1.

The test cases included repeated question groups and do not represent 90 independent applicants.

## 2. Evidence-backed Claims

**Result: 90.20% | 245 claims across 15 reports**

Each report claim was checked against the candidate's complete answer to determine whether the claim was fully supported by the available evidence.

Of 245 claims, 221 were fully supported.

Final judgments were adopted by one human reviewer following AI-assisted assessment. The review was retrospective, and the reports were based on scripted scenarios rather than a random sample of applicants.

This metric measures evidence support, not hiring accuracy.

## 3. P95 Response Latency

**Result: 3.834 seconds | 100 live requests**

Response time was measured at InterMind's backend answer endpoint, covering answer evaluation and next-question generation.

P95 represents the response time at or below which 95% of the measured requests completed.

The test used a controlled advance-question scenario. Browser rendering, network latency, and other interview paths were not included.

## Interpretation

These results describe performance within the evaluated scenarios and should not be interpreted as overall system accuracy or predictive hiring validity.

Additional evaluation details and verified counts are available in the [Results Summary](results_summary.md).
