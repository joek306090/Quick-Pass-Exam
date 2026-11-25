"""Deterministic completeness review of Agent declarations, not semantic proof."""
from __future__ import annotations
from typing import Any

LABELS = {"core": "核心必背", "required": "必背", "watch": "留意", "basic": "了解"}
RELATIONS = ("prerequisites", "next_concepts", "related_concepts")


def review_generation(questions, concepts, cases, methods, sources, evidence, profile,
                      inventory=None):
    findings = []

    def flag(section, code, item, repair):
        findings.append({"section": section, "code": code, "id": item,
                         "severity": "warning", "repair": repair})

    # Do not promote textbook domains or Agent chapter guesses to syllabus authority.
    nodes = {}

    def walk(rows):
        if not isinstance(rows, list):
            return
        for row in rows:
            if isinstance(row, dict):
                if isinstance(row.get("id"), str) and row.get("title"):
                    if row["id"] in nodes:
                        flag("chapters", "SYLLABUS_NODE_DUPLICATE", row["id"], "为各分卷考纲节点提供唯一 ID；重新核对章节引用。")
                    nodes[row["id"]] = row["title"]
                walk(row.get("children"))

    walk(profile.get("syllabus_tree"))
    if not concepts:
        for section in ("chapters", "levels", "graph"):
            flag(section, "CONCEPTS_EMPTY", "package", "无考点可验收；先核实是否漏生成，不能把空考点集当作章节/等级/图谱通过。")
    if concepts and (not nodes or not profile.get("syllabus_authority")):
        flag("chapters", "SYLLABUS_AUTHORITY_MISSING", "profile",
             "在 profile 补入已核验的 syllabus_authority 和 syllabus_tree；不可用领域列表代替考纲。")
    concept_ids = {c["id"] for c in concepts}
    evidence_by_id = {e["id"]: e for e in evidence}
    question_ids = {q["id"] for q in questions} | {
        q["id"] for c in cases for q in c["sub_questions"]}
    edges = set()
    isolated = []
    for c in concepts:
        cid = c["id"]
        chapter = c.get("chapter")
        if not isinstance(chapter, str) or chapter not in nodes:
            flag("chapters", "CONCEPT_CHAPTER_UNMATCHED", cid,
                 "chapter 填权威 syllabus_tree 节点 ID；无法对应时保留缺口，不得猜章节。")
        advice = c.get("study_advice")
        if (not isinstance(advice, dict) or not isinstance(advice.get("kind"), str)
                or advice["kind"] not in LABELS
                or advice.get("label") != LABELS.get(advice["kind"])):
            flag("levels", "STUDY_ADVICE_MISSING_OR_INVALID", cid,
                 "填写 study_advice 的四档 kind/label；difficulty_level 不是优先等级。")
        basis = advice.get("evidence") if isinstance(advice, dict) else None
        valid_basis = isinstance(basis, list) and bool(basis)
        for b in basis if isinstance(basis, list) else []:
            if not isinstance(b, dict) or not isinstance(b.get("reason"), str) or not b["reason"].strip():
                valid_basis = False
                continue
            kind = b.get("type")
            if kind == "question_frequency":
                ids = b.get("question_ids")
                valid_basis &= (isinstance(ids, list) and bool(ids)
                                and all(isinstance(i, str) and i in question_ids and i in c.get("source_questions", []) for i in ids)
                                and type(b.get("count")) is int and b["count"] == len(set(ids))
                                and isinstance(b.get("scope"), str) and bool(b["scope"].strip()))
            elif kind == "syllabus_weight":
                node = b.get("node_id")
                valid_basis &= (isinstance(node, str) and node in nodes
                                and bool(profile.get("syllabus_authority"))
                                and isinstance(b.get("locator"), str) and bool(b["locator"].strip())
                                and isinstance(b.get("value"), (str, int, float)) and not isinstance(b.get("value"), bool)
                                and bool(str(b["value"]).strip()))
            elif kind == "source_evidence":
                ids = b.get("evidence_ids")
                valid_basis &= (isinstance(ids, list) and bool(ids)
                                and all(isinstance(i, str) and i in evidence_by_id
                                        and cid in evidence_by_id[i].get("concept_ids", []) for i in ids))
            else:
                valid_basis = False
        if not valid_basis:
            flag("levels", "STUDY_ADVICE_BASIS_MISSING_OR_INVALID", cid,
                 "逐档说明依据并定位真题 ID/统计范围、考纲权重或本卡证据 ID；不能为过校验随填。")
        relations = c.get("learning_relations")
        local = 0
        if "learning_relations" in c and not isinstance(relations, dict):
            flag("graph", "LEARNING_RELATION_INVALID", cid, "learning_relations 必须为关系对象，不能用字符串/数组替代。")
        if isinstance(relations, dict):
            if set(relations) - set(RELATIONS):
                flag("graph", "LEARNING_RELATION_UNSUPPORTED", cid, "沿用 prerequisites/next_concepts/related_concepts；包含/对比/易混用 related_concepts 并写明学习理由。")
            for kind in RELATIONS:
                values = relations.get(kind, [])
                if not isinstance(values, list):
                    flag("graph", "LEARNING_RELATION_INVALID", cid, "关系值必须为现有考点 ID 数组。")
                    continue
                for target in values:
                    if not isinstance(target, str) or target not in concept_ids or target == cid:
                        flag("graph", "LEARNING_RELATION_INVALID", cid, "删除自环/悬空关系；对照原件核对两端与学习理由。")
                    else:
                        edges.add((cid, kind, target))
                        local += 1
        if not local:
            isolated.append(cid)
    if len(concepts) > 1 and not edges:
        flag("graph", "LEARNING_GRAPH_EMPTY", "package", "独立审阅前置/包含/对比/易混关系；不要根据章节顺序硬造边。")
    for cid in isolated:
        if not any(cid in (a, b) for a, _, b in edges):
            flag("graph", "LEARNING_CONCEPT_ISOLATED", cid, "检查是否遗漏学习关系；确实独立时报告原因，不要凑关系。")

    teaching = {s["id"]: s for s in sources if s.get("role") == "teaching_material"}
    linked = {sid: set() for sid in teaching}
    for e in evidence:
        if e.get("source_id") in linked:
            linked[e["source_id"]].update(set(e.get("concept_ids", [])) & concept_ids)
    files = (inventory or {}).get("files", [])
    declared = {f.get("path"): f for f in files if isinstance(f, dict)}
    confirmed = (inventory or {}).get("confirmed_materials")

    if not isinstance(confirmed, list):
        flag("teaching", "CONFIRMED_MATERIALS_UNKNOWN", "inventory", "冻结用户确认的教辅相对路径清单 confirmed_materials，包括暂缺原件；不要只从已复制目录反推。")
    else:
        for name in confirmed:
            if not isinstance(name, str) or name not in declared:
                flag("teaching", "CONFIRMED_MATERIAL_NOT_IN_INVENTORY", str(name), "补登记该教辅并取回原件；缺文件时明确报告，不得缩小用户清单。")
            elif declared[name].get("decision") != "included":
                flag("teaching", "CONFIRMED_MATERIAL_NOT_INCLUDED", name, "核对用户确认的排除理由；未读/无法解析不算完成。")
            elif declared[name].get("source_id") not in teaching:
                flag("teaching", "CONFIRMED_MATERIAL_SOURCE_MISMATCH", name, "用户确认教辅须对应 teaching_material 来源；核查错误 role/source_id，不得借题库角色跳过解析与关联核验。")

    material_rows = []
    for sid, source in teaching.items():
        entries = [f for f in files if isinstance(f, dict) and f.get("source_id") == sid and f.get("decision") == "included"]
        parse = entries[0].get("parse_review") if entries else None
        if not entries:
            flag("teaching", "TEACHING_NOT_IN_INVENTORY", sid, "在用户清单登记 included/source_id。")
        elif len(entries) != 1:
            flag("teaching", "TEACHING_INVENTORY_AMBIGUOUS", sid, "多份清单原件共用一个 source_id；逐份登记独立来源与解析状态。")
        good_parse = (isinstance(parse, dict) and isinstance(parse.get("status"), str)
                      and parse["status"] in {"text", "ocr", "visual"})
        if good_parse and isinstance(parse, dict):
            good_parse = (isinstance(parse.get("reason"), str) and bool(parse["reason"].strip())
                          and type(parse.get("pages_read")) is int and parse["pages_read"] > 0
                          and parse["pages_read"] == source.get("page_count", 1))
            if parse.get("status") in {"text", "ocr"}:
                good_parse &= type(parse.get("text_chars")) is int and parse["text_chars"] > 0
        if not good_parse:
            flag("teaching", "TEACHING_PARSE_UNVERIFIED", sid, "parse_review 写 text/ocr/visual、pages_read、text_chars（文字/OCR）和核对说明；扫描件不能以无文本过关。")
        if not linked[sid]:
            flag("teaching", "TEACHING_ZERO_CONCEPTS", sid, "回读原件并建立真实证据；不适用/证据不足时报告具体原因，不能静默通过。")
        material_rows.append({"source_id": sid, "path": source.get("path"),
                              "inventory_entries": entries,
                              "parse_review": parse, "concept_count": len(linked[sid]),
                              "concept_ids": sorted(linked[sid])})
    supported = set().union(*linked.values()) if linked else set()
    uncovered = sorted(concept_ids - supported)
    for cid in uncovered:
        flag("teaching", "CONCEPT_WITHOUT_TEACHING_EVIDENCE", cid, "核查确认清单中的教辅；没有支持时保留来源限制，不造证据。")

    figure_rows = []
    for item in questions + cases + [q for c in cases for q in c["sub_questions"]]:
        value = item.get("needs_figure")
        if type(value) is not bool:
            flag("figures", "NEEDS_FIGURE_UNKNOWN", item["id"], "对照题干/选项/案例背景原图，填写 boolean；未知保留 null，不可默认 false。")
            item["needs_figure"] = None
        figure_rows.append({"id": item["id"], "needs_figure": item.get("needs_figure")})
    sections: dict[str, Any] = {section: {"status": "review_required" if any(f["section"] == section for f in findings) else "passed"}
                for section in ("teaching", "chapters", "levels", "graph", "figures")}
    sections["teaching"].update(materials=material_rows, concepts_without_teaching_evidence=uncovered)
    sections["graph"].update(edge_count=len(edges), isolated_concept_ids=[c for c in isolated if not any(c in (a, b) for a, _, b in edges)])
    sections["figures"]["questions"] = figure_rows
    return {"status": "review_required" if findings else "passed",
            "validation": "deterministic_declarations_only", "semantic_verification": "not_performed",
            **sections, "findings": findings}
