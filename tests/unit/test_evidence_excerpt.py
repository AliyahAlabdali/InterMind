"""Regression tests for the evidence-excerpt truncation bug.

A raw ``answer[:200]`` slice used to chop the report's evidence quote through the middle of
whatever word happened to sit at the 200th character (e.g. "independently lead production
deploy|ments", "rapid prototyping velocit|y") - unreadable, and not what the candidate wrote.
``_evidence_excerpt`` (in :mod:`app.llm.fake_client`) fixes this by truncating at the last
whitespace before the limit and marking the cut with a single ellipsis. These tests pin down
the helper itself and confirm all three `_fake_evaluate_answer` branches that build the
report's `evidence` field actually go through it.
"""

from __future__ import annotations

from app.llm.fake_client import _evidence_excerpt, _is_no_evidence
from app.llm.fake_client import _fake_evaluate_answer as fake_evaluate_answer

# Deliberately >200 characters, with the 200th character landing inside a word - reproduces
# the exact failure mode from the bug report.
LONG_ANSWER_MID_WORD_AT_200 = (
    "I independently led the production deployment pipeline for our checkout service, "
    "coordinating with three other engineers to roll out changes safely, and we shipped "
    "several successful production deployments that cut query latency by 40 percent overall."
)

SHORT_ANSWER = "I fixed a bug once and wrote a small test for it."


def test_short_answer_is_returned_completely_unchanged():
    assert len(SHORT_ANSWER) <= 200
    assert _evidence_excerpt(SHORT_ANSWER) == SHORT_ANSWER


def test_answer_exactly_at_the_limit_is_unchanged():
    exactly_200 = "x" * 200
    assert _evidence_excerpt(exactly_200) == exactly_200


def test_long_answer_where_character_200_lands_inside_a_word_is_not_cut_mid_word():
    assert len(LONG_ANSWER_MID_WORD_AT_200) > 200
    # Character 200 must genuinely land inside a word for this test to be meaningful.
    assert LONG_ANSWER_MID_WORD_AT_200[199].isalpha()
    assert LONG_ANSWER_MID_WORD_AT_200[200].isalpha()

    excerpt = _evidence_excerpt(LONG_ANSWER_MID_WORD_AT_200)

    assert excerpt.endswith("…")
    without_ellipsis = excerpt[:-1]
    # The excerpt (minus the ellipsis) must be an exact, whole-word-boundary prefix of the
    # original answer - i.e. it must end right where a real word ends, and the next character
    # in the original text (if any) must be whitespace.
    assert LONG_ANSWER_MID_WORD_AT_200.startswith(without_ellipsis)
    next_char_index = len(without_ellipsis)
    if next_char_index < len(LONG_ANSWER_MID_WORD_AT_200):
        assert LONG_ANSWER_MID_WORD_AT_200[next_char_index] == " "


def test_evidence_never_ends_in_a_partial_word_across_many_lengths():
    """Sweep a range of limits/inputs to make sure the "never cut mid-word" guarantee isn't
    just a coincidence of one specific input."""
    base = (
        "The candidate described building an internal analytics dashboard that aggregated "
        "usage metrics from several microservices and rendered them for the support team "
        "to triage incidents faster than before, cutting median response time significantly."
    )
    for limit in range(20, 260, 7):
        excerpt = _evidence_excerpt(base, limit=limit)
        if excerpt.endswith("…"):
            without_ellipsis = excerpt[:-1]
            next_char_index = len(without_ellipsis)
            assert base.startswith(without_ellipsis)
            if next_char_index < len(base):
                assert base[next_char_index] == " ", (
                    f"limit={limit} cut mid-word: {excerpt!r}"
                )
        else:
            # Untouched - only valid when the whole answer already fits.
            assert excerpt == base


def test_helper_never_fabricates_content_beyond_a_prefix_of_the_original():
    excerpt = _evidence_excerpt(LONG_ANSWER_MID_WORD_AT_200)
    without_ellipsis = excerpt[:-1] if excerpt.endswith("…") else excerpt
    assert LONG_ANSWER_MID_WORD_AT_200.startswith(without_ellipsis)


# --- all three `_fake_evaluate_answer` branches must use the shared helper -------------------

THOROUGH_ANSWER = (
    "I designed and built a payments reconciliation service that processed millions of "
    "transactions daily, coordinated with the finance team to define edge cases, wrote "
    "extensive unit and integration tests, and deployed it gradually behind a feature flag "
    "to reduce risk."
)
PARTIAL_ANSWER = (
    "We had a slow endpoint because of an inefficient database query that was scanning the "
    "entire orders table on every request during peak traffic, which made the checkout page "
    "noticeably sluggish for customers browsing on mobile devices during sales events."
)
VAGUE_LONG_ANSWER = (
    "Supercalifragilisticexpialidocious asynchronous microservice orchestration "
    "infrastructure automation pseudorandomization multidimensionality interoperability "
    "characterization telecommunicationsinfrastructure."
)


def _input_text(answer: str, *, category: str = "technology", target: str = "SQL") -> str:
    return f"QUESTION: q\nCATEGORY: {category}\nTARGET: {target}\nANSWER: {answer}"


def test_thorough_branch_evidence_matches_the_shared_helper():
    assert len(THOROUGH_ANSWER) > 200
    result = fake_evaluate_answer(_input_text(THOROUGH_ANSWER))
    assert result.decision.value == "advance"
    assert result.evidence == [_evidence_excerpt(THOROUGH_ANSWER)]
    assert result.evidence[0] != THOROUGH_ANSWER[:200]  # would fail if regressed to raw slice


def test_partial_branch_evidence_matches_the_shared_helper():
    assert len(PARTIAL_ANSWER) > 200
    result = fake_evaluate_answer(_input_text(PARTIAL_ANSWER))
    assert result.decision.value == "follow_up"
    assert result.evidence == [_evidence_excerpt(PARTIAL_ANSWER)]
    assert result.evidence[0] != PARTIAL_ANSWER[:200]


def test_vague_branch_evidence_matches_the_shared_helper():
    assert len(VAGUE_LONG_ANSWER) > 200
    assert not _is_no_evidence(VAGUE_LONG_ANSWER)
    result = fake_evaluate_answer(_input_text(VAGUE_LONG_ANSWER))
    assert result.decision.value == "follow_up"
    assert result.evidence == [_evidence_excerpt(VAGUE_LONG_ANSWER)]
    assert result.evidence[0] != VAGUE_LONG_ANSWER[:200]


def test_short_answer_through_the_full_evaluator_is_unchanged_in_evidence():
    result = fake_evaluate_answer(_input_text(SHORT_ANSWER))
    assert result.evidence == [SHORT_ANSWER]


# --- whitespace-aware boundary detection (Copilot SHOULD FIX) --------------------------------
#
# The original boundary search used a literal `" "` only, so tabs/newlines were never
# recognised as valid cut points - `_evidence_excerpt("one\ntwo three", 5)` could still slice
# through "two" because there was no *space* character within the first 5 characters, even
# though there was a newline. These pin down whitespace-of-any-kind boundary detection.


def test_newline_separated_text_does_not_cut_through_a_word():
    # The literal reported example: a plain `" "`-only search finds no space in "one\ntwo"[:5]
    # ("one\nt") and would slice straight through "two".
    excerpt = _evidence_excerpt("one\ntwo three", 5)
    assert excerpt == "one…"


def test_tab_separated_text_does_not_cut_through_a_word():
    excerpt = _evidence_excerpt("first\tsecond\tthird\tfourth", 8)
    assert excerpt == "first…"


def test_mixed_whitespace_boundary_uses_the_last_one_before_the_limit():
    excerpt = _evidence_excerpt("alpha\tbeta\ngamma delta", 14)
    # "alpha\tbeta\ngam" (14 chars) - last whitespace before the limit is the newline after
    # "beta"; "gamma" must not be cut.
    assert excerpt == "alpha\tbeta…"


def test_limit_smaller_than_the_first_word_extends_to_the_word_end_not_the_limit():
    """"never cut a word in half" outranks strictly respecting `limit` - documented behaviour
    (see `_evidence_excerpt`'s docstring): when no whitespace exists anywhere before `limit`,
    the excerpt extends to the end of that first whole word instead of chopping through it."""
    excerpt = _evidence_excerpt("hello world", 3)
    assert excerpt == "hello…"
    assert "hel" not in [excerpt]  # sanity: it must not just be the raw 3-char slice + ellipsis


def test_unbroken_long_token_with_no_whitespace_anywhere_is_returned_whole():
    """A single token longer than `limit` with no whitespace anywhere in the answer has no
    word-boundary-safe prefix at all - the documented fallback is to return it unchanged rather
    than cut it (there is nothing to mark with an ellipsis either, since nothing was omitted)."""
    one_giant_token = "x" * 300
    excerpt = _evidence_excerpt(one_giant_token, limit=200)
    assert excerpt == one_giant_token
    assert not excerpt.endswith("…")


def test_unbroken_long_token_followed_by_more_text_extends_past_the_limit_for_that_one_word():
    """Same "never cut a word in half" priority, but here the oversized token is only the
    *first* word of a longer answer - the excerpt still extends past `limit` to cover that
    whole word, then stops (with an ellipsis, since the rest of the answer *is* omitted)."""
    answer = ("x" * 250) + " rest of the answer goes here"
    excerpt = _evidence_excerpt(answer, limit=200)
    assert excerpt == ("x" * 250) + "…"


def test_normal_200_character_space_delimited_behavior_is_unchanged():
    """The original, already-covered behaviour for plain space-delimited text at the default
    200-character limit must still hold after making boundary detection whitespace-aware."""
    excerpt = _evidence_excerpt(LONG_ANSWER_MID_WORD_AT_200)
    assert excerpt.endswith("…")
    assert LONG_ANSWER_MID_WORD_AT_200.startswith(excerpt[:-1])
    assert " " not in excerpt[-6:-1]  # excerpt ends on the word, not mid-word or on a space


def test_short_answers_with_tabs_and_newlines_remain_completely_unchanged():
    short_with_mixed_whitespace = "one\ttwo\nthree four"
    assert len(short_with_mixed_whitespace) <= 200
    assert _evidence_excerpt(short_with_mixed_whitespace) == short_with_mixed_whitespace
