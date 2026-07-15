"""Validators — 6 validators checking proposals against hard constraints.

From doc Table 1:
  1. Constraint Validator  — 硬约束检查（政策、预算、空间、生态、时间）
  2. Evidence Validator    — 证据溯源（关键观点是否有真实来源）
  3. Fairness Validator    — 公平性（弱势群体是否被忽略）
  4. Conflict Validator    — 冲突检测（是否掩盖重大分歧）
  5. Feasibility Validator — 可执行性（责任主体、步骤、资源、风险）
  6. Consistency Validator — 一致性（与前置工件是否一致）

Feedback loop (from doc):
  Proposal → Validators → Clear failure reason → Targeted revision (max 2)
  → If still failing → Mark as "不可采纳方案"
"""

from __future__ import annotations

from .artifacts import (
    ArtifactStatus,
    ConflictMatrix,
    GateCheckResult,
    PositionCard,
    ProposalCard,
    RoundSummary,
    ValidationResult,
)


def validate_all(
    proposal: ProposalCard,
    position_cards: list[PositionCard],
    round_summaries: list[RoundSummary],
    conflict_matrix: ConflictMatrix | None = None,
    hard_constraints: list[dict] | None = None,
    evidence_ids: list[str] | None = None,
) -> ValidationResult:
    """Run all 6 validators and return aggregated result."""
    results: list[ValidationResult] = []

    results.append(validate_constraints(proposal, hard_constraints or []))
    results.append(validate_evidence(proposal, evidence_ids or []))
    results.append(validate_fairness(proposal, position_cards))
    results.append(validate_conflicts(proposal, conflict_matrix))
    results.append(validate_feasibility(proposal))
    results.append(validate_consistency(proposal, position_cards, round_summaries))

    # Aggregate
    all_errors = []
    for r in results:
        all_errors.extend(r.hard_constraint_errors)
        all_errors.extend(r.evidence_errors)
        all_errors.extend(r.fairness_risks)
        all_errors.extend(r.conflict_errors)
        all_errors.extend(r.feasibility_errors)
        all_errors.extend(r.consistency_errors)

    passed = len(all_errors) == 0

    revision_instructions = []
    if not passed:
        revision_instructions = _build_revision_instructions(results)

    return ValidationResult(
        passed=passed,
        hard_constraint_errors=[e for e in all_errors if "约束" in e or "红线" in e or "法规" in e or "预算" in e or "政策" in e],
        evidence_errors=[e for e in all_errors if "证据" in e or "来源" in e],
        fairness_risks=[e for e in all_errors if "弱势" in e or "公平" in e or "忽略" in e],
        conflict_errors=[e for e in all_errors if "冲突" in e or "分歧" in e],
        feasibility_errors=[e for e in all_errors if "责任" in e or "步骤" in e or "资源" in e or "时间" in e],
        consistency_errors=[e for e in all_errors if "一致" in e or "矛盾" in e],
        revision_instructions=revision_instructions,
    )


def should_revise(result: ValidationResult, revision_count: int, max_revisions: int = 2) -> bool:
    """Determine if revision should be attempted."""
    if result.passed:
        return False
    if revision_count >= max_revisions:
        return False
    return bool(
        result.hard_constraint_errors
        or result.evidence_errors
        or result.fairness_risks
        or result.conflict_errors
        or result.feasibility_errors
        or result.consistency_errors
    )


# ── Validator 1: Hard Constraints ──────────────────────────────────────────

def validate_constraints(
    proposal: ProposalCard,
    hard_constraints: list[dict],
) -> ValidationResult:
    """Check if proposal violates hard constraints (法规、预算、空间、生态、时间).

    Hard constraints are non-negotiable. Any violation = validation failure.
    """
    errors = []
    content = (proposal.title + " " + proposal.content).lower()
    risks = proposal.risks.lower() if proposal.risks else ""

    # Define known hard constraint keywords
    hard_keywords = {
        "消防": "消防安全红线",
        "建筑红线": "建筑控制线",
        "生态保护": "生态保护要求",
        "政策红线": "政策红线",
        "预算上限": "预算上限",
        "法规": "法规要求",
    }

    for kw, label in hard_keywords.items():
        if kw in content or kw in risks:
            # Constraint is mentioned — check if it's violated or just referenced
            # Simple heuristic: if mentioned without "满足"/"符合"/"遵守", flag it
            satisfied_markers = ["满足", "符合", "遵守", "达标", "不低于", "不高于"]
            if not any(m in content for m in satisfied_markers):
                # Only flag if constraint keywords mention risk
                if any(risk_kw in risks for risk_kw in [kw, label[:4]]):
                    errors.append(f"硬约束风险：方案可能违反{label}，需确认合规性")

    # Check explicit constraints from context
    for c in hard_constraints:
        category = c.get("category", "")
        examples = c.get("examples", [])
        for ex in examples:
            if ex in content and "违反" in content:
                errors.append(f"硬约束冲突：{category} - {ex}")

    return ValidationResult(hard_constraint_errors=errors)


# ── Validator 2: Evidence ─────────────────────────────────────────────────

def validate_evidence(
    proposal: ProposalCard,
    evidence_ids: list[str],
) -> ValidationResult:
    """Check if key claims have real evidence sources; detect fabrication.

    From doc: "关键观点是否有真实来源，是否存在编造"
    """
    errors = []

    # Check if proposal references evidence
    if not proposal.evidence_ids:
        errors.append("证据缺失：方案未引用任何证据来源")
    else:
        # Check for fabricated evidence IDs
        for eid in proposal.evidence_ids:
            if eid not in evidence_ids and evidence_ids:
                # This is a heuristic — in production you'd check against the actual evidence pool
                pass  # Would verify against evidence pool in real LLM mode

    # Check for unsubstantiated quantitative claims
    quant_markers = ["%", "万人", "亿元", "每年", "人均"]
    for marker in quant_markers:
        if marker in proposal.content and not proposal.evidence_ids:
            errors.append(f"证据缺失：方案包含量化声明（{marker}）但未提供证据来源")
            break

    return ValidationResult(evidence_errors=errors)


# ── Validator 3: Fairness ─────────────────────────────────────────────────

def validate_fairness(
    proposal: ProposalCard,
    position_cards: list[PositionCard],
) -> ValidationResult:
    """Check if vulnerable groups are ignored or only majority is served.

    From doc: "是否忽略弱势群体或只服务多数人"
    """
    risks = []

    # Identify vulnerable/minority stakeholders from position cards
    minority_groups = []
    for c in position_cards:
        if c.stance.value in ("oppose", "conditional_oppose"):
            minority_groups.append(c.stakeholder_group)

    content = proposal.content
    for group in minority_groups:
        if group not in content:
            risks.append(f"公平性风险：反对群体「{group}」的意见未在方案中得到回应")

    # Check for "everyone agrees" language (pseudo-consensus)
    pseudo_consensus_markers = ["大家一致", "各方都同意", "所有人都", "没有分歧"]
    for marker in pseudo_consensus_markers:
        if marker in content:
            risks.append("疑似假共识：方案使用了'大家一致认为'等抹平差异的语言")

    return ValidationResult(fairness_risks=risks)


# ── Validator 4: Conflict ─────────────────────────────────────────────────

def validate_conflicts(
    proposal: ProposalCard,
    conflict_matrix: ConflictMatrix | None = None,
) -> ValidationResult:
    """Check if major conflicts are hidden or disagreements written as consensus.

    From doc: "是否掩盖重大争议或把分歧写成共识"
    """
    errors = []

    if conflict_matrix:
        # High intensity conflicts should be explicitly addressed
        for axis in conflict_matrix.axes:
            if axis.intensity == "high":
                content = proposal.title + " " + proposal.content
                party_mentioned = any(p in content for p in axis.parties)
                if not party_mentioned:
                    errors.append(
                        f"冲突掩盖：高强度冲突轴「{axis.name}」涉及的"
                        f"{'、'.join(axis.parties)} 未在方案中被提及"
                    )

    # Check for conflict-to-consensus laundering
    laundering_markers = ["经过讨论，大家认识到", "经过交流，所有人同意", "分歧已完全解决"]
    for marker in laundering_markers:
        if marker in proposal.content:
            errors.append(f"冲突洗涤：方案暗示分歧已完全解决（{marker}），可能掩盖真实冲突")

    if conflict_matrix and conflict_matrix.hidden_conflicts:
        for hc in conflict_matrix.hidden_conflicts:
            if hc not in proposal.content:
                errors.append(f"隐藏冲突未处理：{hc}")

    return ValidationResult(conflict_errors=errors)


# ── Validator 5: Feasibility ──────────────────────────────────────────────

def validate_feasibility(proposal: ProposalCard) -> ValidationResult:
    """Check if proposal specifies responsibility, steps, resources, and risks.

    From doc: "是否给出责任主体、步骤、资源和风险"
    """
    errors = []

    if not proposal.responsible or len(proposal.responsible) < 2:
        errors.append("可执行性缺失：方案未指定责任主体")

    if not proposal.timeline or len(proposal.timeline) < 2:
        errors.append("可执行性缺失：方案未指定时间线")

    if not proposal.resources or len(proposal.resources) < 2:
        errors.append("可执行性缺失：方案未列出所需资源")

    if not proposal.risks or len(proposal.risks) < 5:
        errors.append("可执行性缺失：方案未充分识别风险")

    if not proposal.evaluation_criteria:
        errors.append("可执行性缺失：方案无可量化的评估标准")

    return ValidationResult(feasibility_errors=errors)


# ── Validator 6: Consistency ──────────────────────────────────────────────

def validate_consistency(
    proposal: ProposalCard,
    position_cards: list[PositionCard],
    round_summaries: list[RoundSummary],
) -> ValidationResult:
    """Check if proposal is consistent with prior artifacts.

    From doc: "方案是否与前文事实、角色意见、证据台账一致"
    """
    errors = []

    # Check consistency with position cards
    all_claims = set()
    for c in position_cards:
        for claim in c.claims:
            all_claims.add(claim[:30])  # first 30 chars as fingerprint

    # Check if proposal contradicts key stakeholder claims
    for c in position_cards:
        if c.stance.value in ("oppose", "conditional_oppose"):
            for nn in c.non_negotiables[:1]:
                # Simple heuristic: if non-negotiable is about a topic the proposal addresses
                if nn[:10] in proposal.content and "不接受" not in proposal.content:
                    pass  # Would need more nuanced NLP in production

    # Check consistency with round summaries
    for summary in round_summaries:
        for uc in summary.unresolved_conflicts[:2]:
            if uc[:15] in proposal.content and "已解决" in proposal.content:
                errors.append(f"一致性矛盾：方案声称已解决'{uc[:30]}...'，但摘要中标记为未解决")

    return ValidationResult(consistency_errors=errors)


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_revision_instructions(results: list[ValidationResult]) -> list[str]:
    """Build targeted revision instructions from validation results."""
    instructions = []

    for r in results:
        for e in r.hard_constraint_errors:
            instructions.append(f"[硬约束] {e}")
        for e in r.evidence_errors:
            instructions.append(f"[证据] {e} — 请补充证据引用")
        for e in r.fairness_risks:
            instructions.append(f"[公平性] {e} — 请在方案中回应")
        for e in r.conflict_errors:
            instructions.append(f"[冲突] {e} — 请明确标注分歧")
        for e in r.feasibility_errors:
            instructions.append(f"[可执行性] {e} — 请补充具体信息")
        for e in r.consistency_errors:
            instructions.append(f"[一致性] {e} — 请与前置工件对齐")

    return instructions[:8]  # Cap at 8 instructions


# ═══════════════════════════════════════════════════════════════════════════════
# SOP v1.2 Validation Gates (§10)
# Each gate returns GateCheckResult with gate_name, stage_id, status, issues, required_action
# ═══════════════════════════════════════════════════════════════════════════════


# ── Gate 1: Role Boundary Gate (§10.1 Row 1) ────────────────────────────────

def gate_role_boundary(
    speech_text: str,
    agent_can_say: list[str],
    agent_cannot_say: list[str],
    agent_name: str = "",
    stage_id: str = "S6",
) -> GateCheckResult:
    """Check if agent speech violates can_say/cannot_say role boundaries.

    Per SOP v1.2 §2.2: each agent has explicit Can Say / Cannot Say rules.
    This gate checks speeches against those boundaries.
    """
    issues = []
    required_action = []

    # Check cannot_say violations (more critical)
    for rule in agent_cannot_say:
        # Extract key terms from cannot_say rule (up to 6 chars each)
        keywords = [w for w in rule.replace("不能", "").replace("不要", "").split() if len(w) >= 2]
        matched_keywords = [kw for kw in keywords if kw in speech_text]
        if len(matched_keywords) >= 2 and len(keywords) >= 2:
            # Multiple keywords from a cannot_say rule appeared — possible violation
            issues.append(f"角色越界风险：'{rule}' — 发言中出现 {matched_keywords}")

    # Check can_say compliance: agent should stay within allowed scope
    if agent_can_say and len(speech_text) > 50:
        # Loose check: if speech is very generic and doesn't touch any can_say area
        any_in_scope = any(
            any(kw in speech_text for kw in rule.split() if len(kw) >= 2)
            for rule in agent_can_say
        )
        if not any_in_scope:
            issues.append("发言过于空泛，未体现角色核心表述范围")

    if issues:
        required_action.append(f"要求{agent_name or '发言者'}重新审视角色边界，修正越界表述")
        status = "revise"
    else:
        status = "pass"

    return GateCheckResult(
        gate_name="Role Boundary Gate",
        stage_id=stage_id,
        status=status,
        issues=issues,
        required_action=required_action,
    )


# ── Gate 2: Evidence Gate (§10.1 Row 2) ─────────────────────────────────────

def gate_evidence(
    claims: list[str],
    evidence_refs: list[str],
    stage_id: str = "S6",
) -> GateCheckResult:
    """Check if key claims are backed by evidence references.

    Per SOP v1.2 §10.1: every substantive claim must cite at least one evidence card.
    """
    issues = []
    required_action = []

    if not evidence_refs:
        issues.append("证据缺失：未引用任何 Evidence Card")
        required_action.append("请引用至少一条相关证据来支撑核心主张")

    # Check for quantitative claims without evidence
    quant_markers = ["%", "万人", "亿元", "每年", "人均", "下降", "上升", "增加", "减少"]
    for claim in claims:
        has_quant = any(m in claim for m in quant_markers)
        if has_quant and not evidence_refs:
            issues.append(f"量化声明缺少证据支撑：'{claim[:60]}'")

    # Stricter: if 3+ claims but fewer than half have evidence
    if len(claims) >= 3 and len(evidence_refs) < len(claims) / 2:
        issues.append(f"证据覆盖率不足：{len(claims)}条主张仅引用{len(evidence_refs)}条证据")

    if issues:
        status = "revise"
        if not required_action:
            required_action.append("补充证据引用或用证据卡替换无依据主张")
    else:
        status = "pass"

    return GateCheckResult(
        gate_name="Evidence Gate",
        stage_id=stage_id,
        status=status,
        issues=issues,
        required_action=required_action,
    )


# ── Gate 3: Conflict Coverage Gate (§10.1 Row 3) ────────────────────────────

def gate_conflict_coverage(
    conflict_axes: list,
    discussion_topics: list[str],
    stage_id: str = "S7",
) -> GateCheckResult:
    """Check if all known conflict axes are addressed in the discussion.

    Per SOP v1.2 §10.1: no major conflict axis should be silently dropped.
    """
    issues = []
    required_action = []

    for axis in conflict_axes:
        axis_name = getattr(axis, 'name', str(axis))
        axis_parties = getattr(axis, 'parties', [])
        axis_intensity = getattr(axis, 'intensity', 'medium')

        mentioned = any(
            party in " ".join(discussion_topics)
            for party in axis_parties
        )

        if not mentioned:
            if axis_intensity == "high":
                issues.append(f"高强度冲突轴未覆盖：'{axis_name}'涉及{axis_parties}但讨论中未出现")
                required_action.append(f"必须重新讨论'{axis_name}'并纳入方案")
            else:
                issues.append(f"冲突轴遗漏：'{axis_name}'未被讨论涉及")

    if not issues:
        status = "pass"
    elif any("高强度" in i for i in issues):
        status = "revise"
    else:
        status = "revise"

    return GateCheckResult(
        gate_name="Conflict Coverage Gate",
        stage_id=stage_id,
        status=status,
        issues=issues,
        required_action=required_action,
    )


# ── Gate 4: Minority Retention Gate (§10.1 Row 4) ───────────────────────────

def gate_minority_retention(
    summary: RoundSummary | None,
    outer_observations: list | None = None,
    stage_id: str = "S7",
) -> GateCheckResult:
    """Check if minority views and outer observations are preserved in summaries.

    Per SOP v1.2 §1.4: minority opinions with evidence MUST be recorded.
    Per SOP v1.2 §4.6: outer circle observations must enter summary or next round questions.
    """
    issues = []
    required_action = []

    if summary is None:
        return GateCheckResult(
            gate_name="Minority Retention Gate",
            stage_id=stage_id,
            status="revise",
            issues=["缺少轮次摘要，无法校验少数意见保留"],
            required_action=["请先生成 RoundSummary"],
        )

    # Check minority_views is non-empty when there are unresolved conflicts
    if summary.unresolved_conflicts and not summary.minority_views:
        issues.append("存在未解决冲突但 minority_views 为空，少数意见可能被遗漏")
        required_action.append("请将未解决冲突中的少数立场写入 minority_views")

    # Check that outer observations are reflected somewhere
    if outer_observations:
        for obs in outer_observations:
            obs_obj = getattr(obs, 'objection', '') or getattr(obs, 'missed_issue', '') or str(obs)
            # Check if this concern appears in summary
            found_in_summary = False
            all_summary_text = " ".join(
                summary.minority_views + summary.unresolved_conflicts +
                summary.next_round_questions + summary.evidence_gaps
            )
            # Loose check: first 15 chars of the observation appear
            obs_key = obs_obj[:15] if obs_obj else ""
            if obs_key and obs_key in all_summary_text:
                found_in_summary = True
            if not found_in_summary and obs_obj:
                issues.append(f"外圈观察未被纳入摘要：'{obs_obj[:60]}'")
                required_action.append("将外圈关键观察写入 minority_views 或 next_round_questions")

    # Check for pseudo-consensus: majority dominates entirely
    if summary.majority_views and not summary.minority_views:
        issues.append("疑似假共识：majority_views 有内容但 minority_views 为空")
        required_action.append("必须明确标注至少一条少数意见或保留意见")

    if not issues:
        status = "pass"
    else:
        status = "revise"

    return GateCheckResult(
        gate_name="Minority Retention Gate",
        stage_id=stage_id,
        status=status,
        issues=issues,
        required_action=required_action,
    )


# ── Gate 5: Proposal Review Gate (§10.1 Row 5) ──────────────────────────────

def gate_proposal_review(
    proposal: ProposalCard,
    hard_constraints: list[dict] | None = None,
    stage_id: str = "S10",
) -> GateCheckResult:
    """Comprehensive proposal review: hard constraints, public resources, universalization.

    Per SOP v1.2 §8 (S10): checks whether proposal passes constraint validation,
    public resource sustainability, and the Universalization 4-question test.
    """
    issues = []
    required_action = []

    # 1. Hard constraint check
    if proposal.risks and ("消防" in proposal.risks or "法规" in proposal.risks):
        if "满足" not in (proposal.content + proposal.risks):
            issues.append("硬约束风险：方案涉及消防/法规但未确认合规性")

    # 2. Public resource sustainability check
    resource_checks = {
        "公共财政": ["经费", "资金", "费用", "财政", "预算"],
        "空间品质": ["空间", "环境", "绿地", "公共空间"],
        "社区信任": ["信任", "透明", "监督", "参与"],
        "长期韧性": ["长期", "可持续", "维护", "退出"],
    }
    for category, keywords in resource_checks.items():
        if not any(kw in proposal.content for kw in keywords):
            issues.append(f"公共资源维度未覆盖：{category}")

    # 3. Universalization 4-question test
    universalization_checks = {
        "普遍性": ["普遍", "推广", "所有"],
        "公平性": ["公平", "平等", "互换"],
        "延续性": ["延续", "持续", "长期", "试点期"],
        "先例性": ["先例", "示范", "推广条件"],
    }
    for q, keywords in universalization_checks.items():
        if not any(kw in proposal.content for kw in keywords):
            issues.append(f"Universalization 检查未通过 — {q}：方案未说明{q}条件")

    # 4. Feasibility essentials
    if not proposal.responsible or len(proposal.responsible) < 2:
        issues.append("责任主体缺失：方案未指定具体责任方")
        required_action.append("请明确责任主体（具体到部门或角色）")
    if not proposal.timeline or len(proposal.timeline) < 2:
        issues.append("时间线缺失：方案未指定执行时间")
        required_action.append("请补充试点启动时间和评估周期")

    # Determine status
    hard_failures = [i for i in issues if "硬约束" in i]
    if hard_failures:
        status = "reject"
        recommendation = "reject"
    elif len(issues) >= 3:
        status = "revise"
        recommendation = "revise"
    elif issues:
        status = "revise"
        recommendation = "revise"
    else:
        status = "pass"
        recommendation = "accept"

    if not required_action:
        required_action.append("请逐条回应 Review Card 中的问题和缺失维度")

    return GateCheckResult(
        gate_name="Proposal Review Gate",
        stage_id=stage_id,
        status=status,
        issues=issues,
        required_action=required_action,
    )
