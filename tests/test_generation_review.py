"""Synthetic completeness regression; no claims about real source semantics."""
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generation_review import LABELS, review_generation
from test_case_contract import sample, check


def payload() -> dict[str, Any]:
    return dict(
        questions=[{"id": "q", "needs_figure": False}], cases=[], methods=[],
        concepts=[{"id": cid, "chapter": "exam:1", "source_questions": ["q"],
                   "study_advice": {"kind": "required", "label": "必背", "evidence": [
                       {"type": "question_frequency", "count": 1, "question_ids": ["q"],
                        "scope": "synthetic sample", "reason": "Sample demonstrates the rule"}]},
                   "learning_relations": {"related_concepts": [other]}}
                  for cid, other in (("a", "b"), ("b", "a"))],
        sources=[{"id": "guide", "path": "guide.pdf", "role": "teaching_material", "page_count": 2}],
        evidence=[{"id": "e", "source_id": "guide", "concept_ids": ["a", "b"]}],
        profile={"syllabus_authority": "synthetic authority, NOT real syllabus",
                 "syllabus_tree": [{"id": "exam:1", "title": "Synthetic chapter"}]},
        inventory={"confirmed_materials": ["guide.pdf"], "files": [
            {"path": "guide.pdf", "source_id": "guide", "decision": "included",
             "parse_review": {"status": "text", "pages_read": 2, "text_chars": 20, "reason": "sample text"}}]})


def codes(report):
    return {r["code"] for r in report["findings"]}


def test_complete_declarations_and_four_levels():
    for kind, label in LABELS.items():
        p = payload()
        p["concepts"][0]["study_advice"].update(kind=kind, label=label)
        report = review_generation(**p)
        assert report["status"] == "passed"
        assert report["teaching"]["materials"][0]["concept_count"] == 2
        assert report["graph"]["edge_count"] == 2


@pytest.mark.parametrize("change,expected", [
    (lambda p: p["inventory"]["confirmed_materials"].append("missing.pdf"), "CONFIRMED_MATERIAL_NOT_IN_INVENTORY"),
    (lambda p: p["inventory"]["files"][0].pop("parse_review"), "TEACHING_PARSE_UNVERIFIED"),
    (lambda p: p["inventory"]["files"][0]["parse_review"].update(pages_read=1), "TEACHING_PARSE_UNVERIFIED"),
    (lambda p: p["evidence"].clear(), "TEACHING_ZERO_CONCEPTS"),
    (lambda p: p["profile"].clear(), "SYLLABUS_AUTHORITY_MISSING"),
    (lambda p: p["concepts"][0].update(chapter=""), "CONCEPT_CHAPTER_UNMATCHED"),
    (lambda p: p["concepts"][0].pop("study_advice"), "STUDY_ADVICE_MISSING_OR_INVALID"),
    (lambda p: p["concepts"][0]["study_advice"].update(kind=[]), "STUDY_ADVICE_MISSING_OR_INVALID"),
    (lambda p: p["concepts"][0]["study_advice"].update(evidence=[]), "STUDY_ADVICE_BASIS_MISSING_OR_INVALID"),
    (lambda p: p["concepts"][0]["study_advice"]["evidence"][0].update(count=2), "STUDY_ADVICE_BASIS_MISSING_OR_INVALID"),
    (lambda p: p["concepts"][0]["study_advice"]["evidence"][0].update(question_ids=["unknown"]), "STUDY_ADVICE_BASIS_MISSING_OR_INVALID"),
    (lambda p: p["concepts"][0]["learning_relations"].update(related_concepts=["a", "unknown"]), "LEARNING_RELATION_INVALID"),
    (lambda p: [c.pop("learning_relations") for c in p["concepts"]], "LEARNING_GRAPH_EMPTY"),
])
def test_each_dimension_is_independent(change, expected):
    p = payload()
    change(p)
    report = review_generation(**p)
    assert report["status"] == "review_required"
    assert expected in codes(report)
    assert all(f["repair"] for f in report["findings"])


@pytest.mark.parametrize("value", [None, "false", 0, {}, []])
def test_unknown_figure_never_becomes_false(value):
    p = payload()
    p["questions"][0]["needs_figure"] = value
    assert "NEEDS_FIGURE_UNKNOWN" in codes(review_generation(**p))
    assert p["questions"][0]["needs_figure"] is None


def test_missing_figures_cases_children_and_explicit_booleans():
    p = payload()
    p["cases"] = [{"id": "case", "needs_figure": True,
                   "sub_questions": [{"id": "sub"}]}]
    result = review_generation(**p)
    assert result["figures"]["questions"] == [
        {"id": "q", "needs_figure": False}, {"id": "case", "needs_figure": True},
        {"id": "sub", "needs_figure": None}]


def test_zero_evidence_reason_does_not_silence_warning():
    p = payload()
    p["inventory"]["files"][0]["no_evidence_reason"] = "No supporting passage"
    p["evidence"] = []
    report = review_generation(**p)
    assert report["teaching"]["concepts_without_teaching_evidence"] == ["a", "b"]
    assert "TEACHING_ZERO_CONCEPTS" in codes(report)


@pytest.mark.parametrize("basis", [
    {"type": "source_evidence", "evidence_ids": ["e"], "reason": "Direct source support"},
    {"type": "syllabus_weight", "node_id": "exam:1", "value": "required",
     "locator": "synthetic section 1", "reason": "Explicit synthetic requirement"},
])
def test_alternative_level_basis_requires_real_links(basis):
    p = payload()
    p["concepts"][0]["study_advice"]["evidence"] = [basis]
    assert review_generation(**p)["levels"]["status"] == "passed"
    p["evidence"].clear()
    p["profile"].clear()
    assert "STUDY_ADVICE_BASIS_MISSING_OR_INVALID" in codes(review_generation(**p))


def test_unsupported_graph_keys_and_duplicate_syllabus_are_not_passed():
    p = payload()
    p["concepts"][0]["learning_relations"]["contains"] = ["b"]
    p["profile"]["syllabus_tree"].append({"id": "exam:1", "title": "duplicate"})
    assert codes(review_generation(**p)) >= {"LEARNING_RELATION_UNSUPPORTED", "SYLLABUS_NODE_DUPLICATE"}


def test_missing_steps_report_each_reason_without_inventing_steps():
    cases, methods = sample()
    methods[0]["qp_steps_omission_reason"] = "No reliable numeric basis in source"
    _, normalized, report = check(cases, methods)
    row = next(f for f in report["findings"] if f["code"] == "METHOD_QP_STEPS_MISSING")
    assert row["id"] == "method1" and row["reason"] == methods[0]["qp_steps_omission_reason"]
    assert "qp_steps" not in normalized[0]


def test_real_generation_persists_review_and_unknown(tmp_path):
    from test_agent_content import _agent_payload, _write
    from generator import generate_package
    source = _write(tmp_path, _agent_payload(tmp_path))
    out = generate_package(source, tmp_path / "output", profile_name="ruankao-xitixiangmu", agent_content=True)
    manifest = json.loads((out / "manifest.json").read_text())
    report = json.loads((out / "reports/quality-report.json").read_text())["generation_review"]
    assert manifest["quality_status"] == manifest["generation_review_status"] == "review_required"
    assert "CONCEPT_CHAPTER_UNMATCHED" in codes(report)
    assert json.loads((out / "data/questions.json").read_text())[0]["needs_figure"] is None
