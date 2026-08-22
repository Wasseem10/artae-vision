"""Runtime enforcement for control-plane model-routing decisions."""

from __future__ import annotations

from dataclasses import dataclass

from video_intelligence_inference.control_plane import ResolvedRuleConfig


@dataclass(frozen=True, slots=True)
class RuntimeExecutionPlan:
    deterministic_rules: tuple[ResolvedRuleConfig, ...]
    semantic_rules: tuple[ResolvedRuleConfig, ...]

    @property
    def needs_detector(self) -> bool:
        return bool(self.deterministic_rules)

    @property
    def needs_vision_provider(self) -> bool:
        return bool(self.semantic_rules)


def route_rules(rules: tuple[ResolvedRuleConfig, ...]) -> RuntimeExecutionPlan:
    """Validate strategies and group jobs without silently changing their semantics."""
    deterministic: list[ResolvedRuleConfig] = []
    semantic: list[ResolvedRuleConfig] = []
    for rule in rules:
        inferred = (
            "semantic_window" if rule.rule_type == "semantic_vision" else "deterministic_tracking"
        )
        strategy = rule.execution_strategy or inferred
        if strategy != inferred:
            raise ValueError(
                f"Rule {rule.rule_id} strategy '{strategy}' conflicts with {rule.rule_type}"
            )
        if strategy == "semantic_window":
            semantic.append(rule)
        else:
            deterministic.append(rule)
    return RuntimeExecutionPlan(tuple(deterministic), tuple(semantic))
