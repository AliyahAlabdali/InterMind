"""The frozen deterministic rule that routes one evidence string to a grounding tier.

PROTOCOL v1.0 - this module's constants and procedure are the registered rule. They are
calibrated on ``evals/datasets/development/grounding_cases.py`` ONLY, and must not be altered
after final-evaluation predictions have been observed. See PROTOCOL.md section 3.

What this rule is for
---------------------
It is a **triage** rule, not a semantic judge. Lexical overlap cannot establish meaning:
negation, altered quantities, substituted entities and narrowed or widened qualifiers can all
preserve most tokens while changing the claim. So the rule is built to be *safe in one
direction* - it auto-accepts only where lexical identity makes a meaning change very unlikely,
and routes everything else to blind human adjudication. Over-routing costs review time;
under-routing would silently credit unsupported evidence, which is the error that would make a
published traceability figure wrong.

Tiers
-----
``SUPPORTED_EXACT``   the normalised evidence is a contiguous substring of the normalised
                      source answer(s). Meaning is preserved by construction.
``SUPPORTED_LEXICAL`` content-token coverage >= THETA and every guard passes.
``AMBIGUOUS``         everything else -> blind human adjudication.

A guard never promotes a case; it can only prevent an auto-accept. A case blocked by a guard
is ``AMBIGUOUS``, never ``UNSUPPORTED``: the rule does not claim to detect unsupported
evidence, only to decline to vouch for it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

#: Registered content-token coverage threshold. Calibrated on the development set ONLY.
#:
#: The decision rule was pre-committed before the development set was run: pick the lowest
#: threshold that produces ZERO false accepts (auto-accepting evidence a human would call
#: unsupported), since a false accept would silently inflate a published traceability figure
#: whereas over-routing only costs review time. The data then selected 0.90: at 0.80 two cases
#: still auto-accepted wrongly - a fabricated entity that was one token in seven
#: ("...index on tenant id and created at in MongoDB", coverage 0.86) and an attribution shift
#: from "I" to "the team" (0.88, the pronoun being a stopword). Both fall below 0.90.
#:
#: The cost is real and is reported rather than hidden: raising 0.80 -> 0.90 also stops
#: auto-accepting one genuinely supported paraphrase on the development set, and raises that
#: set's adjudication load from 81% to 92%. The choice between 0.80 and 0.90 turns on two
#: cases, which is thin; this is why every result reports the full sensitivity table at
#: 0.70 / 0.80 / 0.90 so the threshold is never load-bearing on its own.
THETA = 0.90

#: Sensitivity points reported alongside every result so the threshold is never load-bearing.
THETA_SENSITIVITY = (0.70, 0.80, 0.90)

#: Registered threshold for adjacency (content-bigram) coverage, required in addition to THETA.
#:
#: Unigram coverage alone admitted three distinct false accepts on the development set, all
#: from the same cause: a bag of words loses word order, so evidence can reuse an answer's
#: vocabulary while changing who did what to which thing. "moved the checkout service onto
#: Kubernetes" scored 1.00 against an answer about the *payment* service (both words occur, in
#: different roles); "the team wrote the Helm charts" scored 0.88 against "I wrote the Helm
#: charts" (the pronoun is a stopword, hence invisible); "...index on tenant id and created at
#: in MongoDB" scored 0.86 because the one fabricated token was a seventh of the string.
#:
#: Requiring adjacent content-token pairs to also appear in the answer restores enough word
#: order to catch all three, because each rewrite creates a bigram the answer never contains
#: ("checkout service", "team wrote", "at mongodb"). It remains a lexical test - it cannot
#: detect reversed causality expressed with different adjacencies - but it closes the cheapest
#: and most consequential class of false accept.
#:
#: 0.60 chosen on the development set only. Paraphrase legitimately disturbs adjacency more
#: than vocabulary, so this floor must sit well below THETA or valid paraphrases would be
#: rejected rather than adjudicated; 0.60 was the highest value admitting no false accept while
#: still auto-accepting the development set's faithful restatements.
THETA_BIGRAM = 0.60

#: Evidence with fewer content tokens than this cannot be auto-accepted by the lexical tier.
#:
#: Below four tokens, coverage is a coarse ladder (0, 1/3, 1/2, 2/3, 1) on which a single
#: shared token can clear any threshold, and one shared token is not evidence of semantic
#: support - "used Kubernetes" overlaps an answer that only ever said "Kubernetes" in passing.
#: Short strings therefore go to Tier 1 (exact, where brevity is harmless) or to adjudication.
MIN_CONTENT_TOKENS_FOR_LEXICAL = 4

#: Tokens whose presence inverts a claim. Their presence in the evidence blocks auto-accept.
#:
#: A negated claim and its positive form share nearly every content token, so coverage cannot
#: separate them, and the error is maximally consequential - "has not used Kafka" vs "has used
#: Kafka" is the difference between two opposite report statements. Tier 1 is unaffected, since
#: an exact substring carries its own negation.
NEGATION_TOKENS = frozenset(
    {
        "not",
        "no",
        "never",
        "without",
        "cannot",
        "cant",
        "dont",
        "doesnt",
        "didnt",
        "none",
        "nothing",
        "neither",
        "nor",
        "lack",
        "lacks",
        "lacked",
        "lacking",
        "unable",
        "failed",
        "unfamiliar",
        "nope",
        "havent",
        "hasnt",
        "wasnt",
        "werent",
        "isnt",
        "arent",
        "wont",
        "couldnt",
        "shouldnt",
        "rarely",
        "barely",
        "hardly",
    }
)

#: Frozen stopword list. Deliberately function words only - nothing domain-specific, so the
#: list cannot be tuned to favour any particular kind of answer.
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "than",
        "that",
        "this",
        "these",
        "those",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "doing",
        "have",
        "has",
        "had",
        "having",
        "i",
        "we",
        "you",
        "he",
        "she",
        "it",
        "they",
        "them",
        "their",
        "my",
        "our",
        "your",
        "his",
        "her",
        "its",
        "me",
        "us",
        "so",
        "about",
        "into",
        "over",
        "also",
        "very",
        "just",
        "really",
        "there",
        "here",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "while",
        "would",
        "could",
        "should",
        "will",
        "can",
        "may",
        "might",
        "must",
        "up",
        "out",
        "down",
        "off",
        "again",
        "some",
        "any",
        "all",
        "both",
        "each",
        "more",
        "most",
        "other",
        "such",
        "only",
        "own",
        "same",
        "too",
        "s",
        "t",
        "d",
        "ll",
        "m",
        "re",
        "ve",
        "y",
    }
)

_DIGIT = re.compile(r"\d")
#: Keeps intra-word -, +, /, . and # so C++, CI/CD, scikit-learn, 3.11 and C# survive intact.
_TOKEN = re.compile(r"[a-z0-9]+(?:[-+/.#][a-z0-9]+)*\+*#*")


class Tier(StrEnum):
    SUPPORTED_EXACT = "supported_exact"
    SUPPORTED_LEXICAL = "supported_lexical"
    AMBIGUOUS = "ambiguous"


def normalize(text: str) -> str:
    """NFKC -> casefold -> collapse punctuation to spaces (keeping intra-word joiners).

    No stemming or lemmatisation, deliberately: inflection slack is absorbed by THETA instead,
    which keeps the rule inspectable. A reader can verify any verdict by eye; a stemmer's
    behaviour on "operating"/"operations"/"operator" would have to be taken on trust.
    """
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(_TOKEN.findall(text))


def content_tokens(text: str) -> list[str]:
    """Normalised tokens with stopwords removed, order preserved, duplicates kept."""
    return [t for t in normalize(text).split() if t not in STOPWORDS]


def content_bigrams(text: str) -> list[tuple[str, str]]:
    """Adjacent pairs of content tokens, after stopword removal.

    Pairing *content* tokens rather than raw tokens means "I wrote the Helm charts" and "wrote
    Helm charts" produce the same adjacencies, so paraphrase that only changes function words
    is not punished - while a substituted or inserted content word always breaks a pair.
    """
    tokens = content_tokens(text)
    return list(zip(tokens, tokens[1:], strict=False))


@dataclass(frozen=True)
class GroundingResult:
    tier: Tier
    coverage: float
    bigram_coverage: float
    matched: tuple[str, ...]
    missing: tuple[str, ...]
    guard: str | None
    content_token_count: int

    @property
    def auto_supported(self) -> bool:
        return self.tier in (Tier.SUPPORTED_EXACT, Tier.SUPPORTED_LEXICAL)


def classify(evidence: str, source_answers: list[str], theta: float = THETA) -> GroundingResult:
    """Route one evidence string against the answer turn(s) it is allowed to draw on.

    ``source_answers`` is the full set of turns the evidence may legitimately cite - for direct
    evidence, every turn sharing the target's ``root_question_id``; for cross-target evidence,
    the single turn it was recorded in (PROTOCOL.md 2.1). Passing the report's
    ``candidate_answer`` alone would wrongly fail main-answer evidence on followed-up targets.
    """
    normalized_evidence = normalize(evidence)
    haystack = " ".join(normalize(a) for a in source_answers)

    evidence_tokens = content_tokens(evidence)
    n = len(evidence_tokens)
    haystack_tokens = set(content_tokens(" ".join(source_answers)))

    matched = tuple(t for t in evidence_tokens if t in haystack_tokens)
    missing = tuple(t for t in evidence_tokens if t not in haystack_tokens)
    coverage = len(matched) / n if n else 0.0

    source_bigrams = set(content_bigrams(" ".join(source_answers)))
    evidence_bigrams = content_bigrams(evidence)
    bigram_coverage = (
        sum(1 for b in evidence_bigrams if b in source_bigrams) / len(evidence_bigrams)
        if evidence_bigrams
        else 0.0
    )

    # The minimum-length rule applies to EVERY tier, including exact match. A one-word evidence
    # string is a contiguous substring of any answer that mentions the word once, which is why
    # the bare token "Kubernetes" was auto-accepted against an answer that merely named it -
    # the development set's starkest false accept. Naming a technology the candidate mentioned
    # is not evidence about the candidate, however exactly it matches.
    if n < MIN_CONTENT_TOKENS_FOR_LEXICAL:
        return GroundingResult(
            Tier.AMBIGUOUS, coverage, bigram_coverage, matched, missing, "too_short", n
        )

    # Tier 1. An exact substring preserves negation, quantity, entity and word order by
    # construction, so the remaining guards cannot apply.
    if normalized_evidence and normalized_evidence in haystack:
        return GroundingResult(Tier.SUPPORTED_EXACT, 1.0, 1.0, matched, (), None, n)

    guard = _guard(evidence_tokens, haystack_tokens, n)
    if guard is None and bigram_coverage < THETA_BIGRAM:
        guard = f"adjacency:{bigram_coverage:.2f}"
    if guard is None and coverage >= theta:
        tier = Tier.SUPPORTED_LEXICAL
    else:
        tier = Tier.AMBIGUOUS
    return GroundingResult(tier, coverage, bigram_coverage, matched, missing, guard, n)


def _guard(evidence_tokens: list[str], haystack_tokens: set[str], n: int) -> str | None:
    """The first registered guard that blocks a lexical auto-accept, or None.

    Order is fixed so the reported reason is deterministic.
    """
    if n < MIN_CONTENT_TOKENS_FOR_LEXICAL:
        return "too_short"
    if any(t in NEGATION_TOKENS for t in evidence_tokens):
        return "negation_present"
    unmatched_numeric = [
        t for t in evidence_tokens if _DIGIT.search(t) and t not in haystack_tokens
    ]
    if unmatched_numeric:
        return f"numeric_mismatch:{','.join(unmatched_numeric)}"
    return None
