"""Offline provenance regressions; no model, historical artifacts or network required."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain.interview_plan import EvidenceSource, SelectedTask, SelectedTechnology
from evals.retrieval_dataset import CASES
from evals.run_grounding_eval import _plan_case


@pytest.mark.parametrize(
    ("source", "introduced", "corroborated"),
    [(EvidenceSource.JOBSPEC, 0, 0), (EvidenceSource.BOTH, 0, 2), (EvidenceSource.ONET, 2, 0)],
)
@pytest.mark.parametrize("correct_match", [True, False])
async def test_leakage_distinguishes_new_requirements_from_jd_corroboration(
    source, introduced, corroborated, correct_match
):
    case = CASES[0]
    plan = SimpleNamespace(
        occupation_match=SimpleNamespace(
            onet_soc_code=case.acceptable[0] if correct_match else "wrong-occupation",
            title="Synthetic occupation",
            score=0.5,
        ),
        onet_grounding_used=True,
        onet_context="Synthetic context",
        technologies=[SelectedTechnology(name="Python", source=source)],
        tasks=[SelectedTask(task="Develop software", source=source)],
    )
    result = await _plan_case(SimpleNamespace(plan=AsyncMock(return_value=plan)), case)
    assert result.onet_items == introduced
    assert result.corroborated_items == corroborated
    assert result.leaked_requirement is (not correct_match and introduced > 0)
    assert result.outcome == ("grounded_correct" if correct_match else "grounded_wrong")
