# 生成完整性：教辅、章节、等级、图谱与图表

Agent-first 不执行旧内容生成器 prompt。编写 JSON 前按本合同组织输入、输出和逐项验收；本地检查只核对声明与引用，不能证明内容语义真实。缺口会进入 `reports/quality-report.json.generation_review`，并使 manifest 的 `quality_status` 为 `review_required`，不能把结构 passed 当作内容通过。

## 输入：确认资料与权威考纲

在筛选原件前，冻结用户确认的教辅清单到 `source-inventory.json.confirmed_materials`（相对原始根目录的路径数组）。不要只从 source-root 中已经存在的文件反推用户清单；用户提到但尚未提供的资料也要列出，向用户报告缺件并取得原件。没有固定教辅本数要求。用户明确排除的论文等保留 excluded 与具体原因，不因本规范自动改成 included。

每个 included 教辅的清单记录增加 `parse_review`：

```json
{
  "path": "guide.pdf", "decision": "included", "source_id": "guide",
  "parse_review": {"status": "ocr", "pages_read": 12, "text_chars": 3456,
                   "reason": "逐页 OCR 后对照原图检查，图表单独核对"}
}
```

status 使用 `text`、`ocr`、`visual`；失败/未读可写 `failed`、`unread` 并说明原因，不能视为完成。PDF 的 pages_read 应覆盖实际物理页数；非分页文档按 1 个文档单元记录。text/ocr 填实际非零文本量，visual 说明实际视觉检查范围，不能凭空声明解析完成。此记录是 Agent 审阅声明，不是程序运行 OCR 的证明。已有 `no_evidence_reason` 仍保留，但零关联不能因填写理由静默通过。

profile 要提供已核验的 `syllabus_authority`（官方来源、版本与节点核验说明）和 `syllabus_tree`。树形节点结构为 `{id, title, children: [...]}`；节点 ID 全树唯一，两个考纲分卷的节点 ID 应含分卷前缀，不能把同一考试的两份考纲当成两个考试。不可从教辅目录或 domain_examples 自动生成考纲权威结构。公开内置 profile 尚未附带权威树：缺树会明确报告，补齐官方数据前不得宣称章节验收合格。仅有第三方 syllabus_source URL 不能替代官方节点核验。

## 输出：三项独立的考点要求

1. `concepts[].chapter` 填权威考纲节点 **ID**（展示标题从树读取）。空值、不在树中的 ID、缺权威树都必须报告；不得用 parent 或考点标题兜底过关。
2. `concepts[].study_advice` 为四档复习优先级，不是 `difficulty_level`：

```json
{
  "kind": "core", "label": "核心必背",
  "evidence": [{"type": "question_frequency", "question_ids": ["q1", "q2"],
                "count": 2, "scope": "本次已完整阅读的两份试卷",
                "reason": "两份卷分别考查同一判定规则，结合考纲要求优先复习"}],
  "text": "先掌握判定规则，再做变式"
}
```

kind/label 固定对应：`core/核心必背`、`required/必背`、`watch/留意`、`basic/了解`。每档都要有 evidence；不要为凑齐四档强制分配比例，也不按单一题数机械定档。question_frequency 引用本卡真实 source_questions，count 等于去重题数，scope 指明统计局限，不能把样本频次冒充全考试频率。也可使用 `{type: "syllabus_weight", node_id, value, locator, reason}` 定位官方考纲权重，或 `{type: "source_evidence", evidence_ids: [...], reason}` 引用关联本卡的教辅证据。reason 解释为什么这些依据支持此档，而不只写“重要”。缺依据则保留未知并报告，不得猜。
3. `learning_relations` 独立验收，沿用 `{prerequisites: [id], next_concepts: [id], related_concepts: [id]}`。前置/后续用前两项；包含/对比/易混用 related_concepts，具体关系和学习理由写在卡片可见文字中，不私建 Web 无法消费的结构。检查悬空 ID、自环、整包零关系与孤立考点。确实独立就解释限制，不为了凑边虚构关系。补齐章节不等于知识图谱合格。

## 输出：题目图表依赖与整页溯源

为 `questions[]`、`cases[]` 和 `cases[].sub_questions[]` 分别填写 `needs_figure`。判断题干/选项/共享背景本身是否依赖图表，不是判断“有没有整页截图”。有必需图表填 true，可靠核验纯文字填 false，无法判断填 null。缺失或非 boolean 都按未知报告，不默认 false。案例子问依赖共享图表时也填 true。

`diagram_image`/案例 `diagram_images` 保留必需图表，`source_page`/`source_pages` 继续保留溯源整页。不要为了隐藏溯源图删除原页或必需图表。Web 仅显式 false 折叠溯源整页；true/null/缺失采取保守可见策略，显式图表始终保留。

## 交付检查

- 查看 generation_review.teaching 的每份教辅 concept_count/concept_ids、parse_review 和 concepts_without_teaching_evidence。缺清单、未解析、零关联、没有教辅证据的考点均需逐项修复或如实报告。代码只数真实声明的边，不证明 supports 合理。
- 分别审阅 chapters、levels、graph；任何一项 review_required 都不能宣传“考纲和知识图谱已合格”。
- 每张 calculation 方法默认编写 qp_steps；按 qp-steps.md 对不能可靠编写的卡逐项解释纯文字降级，禁止无效步骤凑数。
- 对照源 payload → ZIP data → Web vault → 页面逐字段核对；纯文字、有图、未知三态都要覆盖，方法播放器和图谱边都需浏览器检查。只重打包不算通过；合成样本仅算冒烟，真实资料回归另附证据。
- 新包使用新输出目录；用户要求旧包不动时不替换旧包、不迁移作答。分别报告结构、Agent 语义审阅、浏览器和人工内容验收。
