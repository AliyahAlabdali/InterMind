# Recovered report evidence quotation fidelity, aggregation method v1.1

This method applies only to the incomplete v1.0 run recovered under frozen
`PROTOCOL_v1.1.md`. It does not produce the frozen v1.0 Evidence Traceability metric,
claim validity, score defensibility, or numeric score accuracy.

The denominator is every evidence string saved in the 15 recovered persona reports
(239 strings). The frozen recovery audit identifies 217 strings with a unique exact
match in the reported target answer. Under the v1.1 rule these count as automatically
source-attributed. The remaining 22 require the separately frozen, one-human blind
review. Add only human `supported` verdicts to the numerator. Count `unsupported`
and `cannot_tell` separately; `cannot_tell` never counts as supported. Report the
automatic and human contributions to the numerator explicitly.

For each report, give the same counts and the number of distinct report target
answers represented by its evidence strings. Summarize the distribution of report
rates and evidence counts. Evidence strings within the same report or answer are
dependent, so the 239 strings are not 239 independent validation cases. This small
15-report recovery set supports descriptive summaries only; no string-level
binomial confidence interval is presented. A supported statement attributed only
to a different answer is counted as candidate-source fidelity but reported as
cross-target support, not silently treated as support from the reported target.

Rebuild the evidence inventory from the unchanged interrupted progress file and
frozen persona inputs. Require all 239 unique IDs, the exact 22 unresolved IDs,
the frozen human-review copy and its SHA-256 lock, the recovery manifest, and all
v1.0/v1.1 frozen locks. Write the result once to a separate versioned directory
with input, method, code, and output hashes. Never edit the original progress,
protocol, label, pilot, latency, or review files.
