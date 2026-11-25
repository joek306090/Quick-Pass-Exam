"""Build a reproducible synthetic payload -> package -> ZIP smoke handoff.

Not a real-source generation or semantic-quality acceptance test.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from generator import generate_package
from generation_review import LABELS
from qp_steps import basis_hash, validate
from pdf_backend import physical_page_count


def run(work):
    work.mkdir(parents=True, exist_ok=False)
    inputs = work / "input"
    inputs.mkdir()
    base = ROOT / "examples/cases"
    payload = json.loads((base / "agent-content-mixed.json").read_text())
    for source in payload["sources"]:
        shutil.copyfile(base / source["path"], inputs / source["path"])
    # Contract variants only: duplicates are explicitly not new exam knowledge.
    seed = payload["concepts"][0]
    for kind in list(LABELS)[1:]:
        c = copy.deepcopy(seed)
        c["id"] = seed["id"] + "-" + kind
        c["title"] += "（合成合同变体 " + kind + "）"
        payload["concepts"].append(c)
    all_concepts = [c["id"] for c in payload["concepts"]]
    for q in payload["questions"]:
        q["concept_ids"] = all_concepts.copy()
    for case in payload["cases"]:
        for sub in case["sub_questions"]:
            if seed["id"] in sub["concept_ids"]:
                sub["concept_ids"] = all_concepts.copy()
    for e in payload["teaching_evidence"]:
        if seed["id"] in e["concept_ids"]:
            e["concept_ids"] = all_concepts.copy()
    original = copy.deepcopy(payload["questions"][0])
    for index, value in enumerate((False, True, None)):
        q = copy.deepcopy(original)
        q.update(id=f"smoke-choice-{index}", needs_figure=value)
        payload["questions"].append(q)
        for c in payload["concepts"]:
            if c["id"] in q["concept_ids"]:
                c["source_questions"].append(q["id"])
                c["related_questions"].append(q["id"])
        payload["method_coverage"]["items"].append({
            "question_id": q["id"], "classification": "non_calculation",
            "reason": "Synthetic formula recognition, no numerical calculation", "requirements": []})
    for case in payload["cases"]:
        case["needs_figure"] = bool(case["diagram_images"])
        for sub in case["sub_questions"]:
            sub["needs_figure"] = case["needs_figure"]
    concept_ids = [c["id"] for c in payload["concepts"]]
    for index, c in enumerate(payload["concepts"]):
        kind = list(LABELS)[index % len(LABELS)]
        c["chapter"] = "synthetic:cost"
        c["study_advice"] = {"kind": kind, "label": LABELS[kind], "text": "Synthetic smoke advice only",
            "evidence": [{"type": "question_frequency", "question_ids": c["source_questions"],
                          "count": len(set(c["source_questions"])), "scope": "synthetic fixture only",
                          "reason": "Synthetic contract check, NOT actual exam priority"}]}
        c["learning_relations"] = {"related_concepts": [i for i in concept_ids if i != c["id"]]}
    for method in payload["methods"]:
        if method["type"] == "calculation":
            # The public fixture has EV=60, AC=75; do not invent a source trace.
            if method["formula"] == "CPI=EV/AC":
                method["qp_steps"] = {
                    "schema": "qp-steps-v1", "method": method["title"], "kind": "method", "view": "formula",
                    "inputs": [{"id": "EV", "label": "挣值", "example": 60},
                               {"id": "AC", "label": "实际成本（正数）", "example": 75}],
                    "steps": [{"id": "CPI", "title": "计算成本效率", "explain": "同一时点同币种，AC 必须为正数", "expr": "EV/AC"}],
                    "provenance": {"generator": "skill", "source_questions": method["sub_question_ids"],
                        "generated_at": "2026-11-24T00:00:00Z", "basis_hash": basis_hash(method["title"], method["formula"])}}
                assert validate(method["qp_steps"]) == (True, [])
            else:
                method["qp_steps_omission_reason"] = "Synthetic smoke only exercises CPI; this card remains text, not invented steps"
    inventory = {"input_scope": {"root": str(inputs.resolve()), "scopes": ["."]},
                 "confirmed_materials": [s["path"] for s in payload["sources"] if s["role"] == "teaching_material"],
                 "files": [{"path": s["path"], "source_id": s["id"], "decision": "included",
                            "parse_review": {"status": "visual", "pages_read": physical_page_count(inputs / s["path"]),
                                             "reason": "Public synthetic fixture reviewed; smoke only"}}
                           for s in payload["sources"]]}
    path = inputs / "agent-content.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    inv = inputs / "source-inventory.json"
    inv.write_text(json.dumps(inventory, ensure_ascii=False, indent=2))
    package = generate_package(path, work / "package", profile_name="ruankao-xitixiangmu", agent_content=True,
                               source_root=inputs, source_inventory=inv)
    archive = work / "generation-quality-smoke.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(package.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(package).as_posix())
    with zipfile.ZipFile(archive) as z:
        for name in ("questions", "concepts", "methods", "cases"):
            stored = json.loads(z.read(f"data/{name}.json"))
            original_rows = payload[name]
            for a, b in zip(original_rows, stored, strict=True):
                assert a["id"] == b["id"]
                for field in ("study_advice", "chapter", "learning_relations", "qp_steps"):
                    if field in a:
                        assert a[field] == b[field]
                if "needs_figure" in a:
                    assert a["needs_figure"] is b["needs_figure"]
    result = {"scope": "synthetic payload -> deterministic package -> ZIP only; Web/browser pending",
              "payload_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
              "question_count": len(payload["questions"]), "concept_count": len(payload["concepts"]),
              "method_count": len(payload["methods"]),
              "qp_steps_count": sum("qp_steps" in m for m in payload["methods"]),
              "expected_review_gaps": "Public profiles lack authoritative syllabus tree; synthetic chapter intentionally unverified"}
    (work / "smoke-report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(archive)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)
