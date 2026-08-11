from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Literal

from pydantic import JsonValue

from tradesentinel.domain.assistant import AssistantGeneratedOutput, EvidencePacket
from tradesentinel.platform.contracts import (
    CapabilityResult,
    EvidenceKind,
    EvidenceRecord,
    EvidenceSource,
    ExecutionOutcome,
    GroundedClaim,
    MetricGrid,
    ResponseSection,
    SummaryCard,
    WorkflowResult,
)

_SKIPPED_PATH_PARTS = {
    "bars",
    "points",
    "series",
    "discussions",
    "text_excerpt",
    "evidence_excerpt",
}
_NUMBER = re.compile(r"(?<![\w])[-+]?\d[\d,.]*(?:%|[A-Za-z]+)?")
_PROHIBITED = (
    re.compile(r"\b(?:buy|sell|hold)\b", re.IGNORECASE),
    re.compile(r"\b(?:price target|target price|expected to reach)\b", re.IGNORECASE),
    re.compile(r"\b(?:probability|percent chance|% chance)\b", re.IGNORECASE),
    re.compile(r"\b(?:will|likely to)\s+(?:rise|fall|increase|decrease)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:calculate|calculated|compute|computed)\s+(?:rsi|cagr|return|indicator)",
        re.IGNORECASE,
    ),
    re.compile(r"="),
)


def _evidence_id(producer: str, path: str, value: str) -> str:
    digest = hashlib.sha256(f"{producer}|{path}|{value}".encode()).hexdigest()[:16]
    return f"ev_{digest}"


def _provider_name(value: Any) -> str | None:
    if isinstance(value, dict):
        provider = value.get("provider")
        if isinstance(provider, str):
            return provider
        for nested in value.values():
            found = _provider_name(nested)
            if found:
                return found
    if isinstance(value, list):
        for nested in value[:10]:
            found = _provider_name(nested)
            if found:
                return found
    return None


class EvidenceBuilder:
    def __init__(self, maximum_records: int = 160) -> None:
        self.maximum_records = maximum_records

    def build(self, question: str, outcomes: tuple[ExecutionOutcome, ...]) -> EvidencePacket:
        records: list[EvidenceRecord] = []
        sources: list[EvidenceSource] = []
        seen_records: set[str] = set()
        seen_sources: set[str] = set()
        for outcome in outcomes:
            for record in outcome.response.evidence:
                if record.evidence_id not in seen_records:
                    records.append(record)
                    seen_records.add(record.evidence_id)
            for source in outcome.response.sources:
                if source.source_id not in seen_sources:
                    sources.append(source)
                    seen_sources.add(source.source_id)
                record = EvidenceRecord(
                    evidence_id=_evidence_id(outcome.target.name, source.source_id, source.title),
                    kind=EvidenceKind.RESEARCH_CLAIM,
                    title=source.title,
                    value=f"{source.title} ({source.url})",
                    producer=outcome.target.name,
                    provider=source.provider,
                    timestamp=source.published_at or source.retrieved_at,
                    source_ids=(source.source_id,),
                    run_id=outcome.response.run_id,
                    freshness="unknown",
                    untrusted=True,
                )
                if record.evidence_id not in seen_records:
                    records.append(record)
                    seen_records.add(record.evidence_id)
            records.extend(self._component_records(outcome, seen_records))
            records.extend(self._data_records(outcome, seen_records))
            if len(records) >= self.maximum_records:
                break
        return EvidencePacket(
            question=question,
            records=tuple(records[: self.maximum_records]),
            sources=tuple(sources),
        )

    def _component_records(self, outcome: ExecutionOutcome, seen: set[str]) -> list[EvidenceRecord]:
        output: list[EvidenceRecord] = []
        components = list(outcome.response.components)
        while components:
            component = components.pop(0)
            if isinstance(component, ResponseSection):
                components[0:0] = list(component.items)
            elif isinstance(component, MetricGrid):
                for index, metric in enumerate(component.metrics):
                    path = f"components.{component.id}.metrics.{index}"
                    value = f"{metric.label}: {metric.value}"
                    if metric.detail:
                        value += f" ({metric.detail})"
                    record = self._record(outcome, path, metric.label, value)
                    if record.evidence_id not in seen:
                        output.append(record)
                        seen.add(record.evidence_id)
            elif isinstance(component, SummaryCard):
                record = self._record(
                    outcome,
                    f"components.{component.id}",
                    component.heading,
                    component.body,
                )
                if record.evidence_id not in seen:
                    output.append(record)
                    seen.add(record.evidence_id)
        return output

    def _data_records(self, outcome: ExecutionOutcome, seen: set[str]) -> list[EvidenceRecord]:
        result = outcome.result
        results: Iterable[CapabilityResult]
        if isinstance(result, WorkflowResult):
            results = result.steps.values()
        else:
            results = (result,)
        output: list[EvidenceRecord] = []
        for capability_result in results:
            provider = _provider_name(capability_result.data)
            for path, value in self._scalars(capability_result.data):
                if len(output) >= self.maximum_records:
                    break
                record = self._record(
                    outcome,
                    f"{capability_result.capability}.{path}",
                    path.rsplit(".", maxsplit=1)[-1].replace("_", " ").title(),
                    value,
                    provider=provider,
                    capability=capability_result.capability,
                    cutoff=capability_result.metadata.data_cutoff,
                    freshness=capability_result.metadata.freshness,
                )
                if record.evidence_id not in seen:
                    output.append(record)
                    seen.add(record.evidence_id)
        return output

    def _record(
        self,
        outcome: ExecutionOutcome,
        path: str,
        title: str,
        value: str,
        *,
        provider: str | None = None,
        capability: str | None = None,
        cutoff: datetime | None = None,
        freshness: Literal["fresh", "stale", "unknown"] = "unknown",
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=_evidence_id(outcome.target.name, path, value),
            kind=EvidenceKind.CALCULATED_METRIC,
            title=title[:240],
            value=value[:2_000],
            producer=outcome.target.name,
            provider=provider,
            timestamp=cutoff or outcome.response.generated_at,
            run_id=outcome.response.run_id,
            capability=capability,
            json_path=path,
            data_cutoff=cutoff,
            freshness=freshness,
        )

    @staticmethod
    def _scalars(value: JsonValue, path: str = "data") -> Iterable[tuple[str, str]]:
        if isinstance(value, dict):
            for key in sorted(value):
                if key in _SKIPPED_PATH_PARTS:
                    continue
                yield from EvidenceBuilder._scalars(value[key], f"{path}.{key}")
        elif isinstance(value, list):
            if len(value) <= 12:
                for index, item in enumerate(value):
                    yield from EvidenceBuilder._scalars(item, f"{path}.{index}")
        elif value is not None and not isinstance(value, (dict, list)):
            rendered = str(value)
            if rendered and len(rendered) <= 500:
                yield path, rendered


class EvidencePolicy:
    def violations(
        self,
        output: AssistantGeneratedOutput,
        packet: EvidencePacket,
        *,
        thesis: bool = False,
    ) -> tuple[str, ...]:
        records = {record.evidence_id: record for record in packet.records}
        violations: list[str] = []
        for claim in self._claims(output):
            missing = [item for item in claim.evidence_ids if item not in records]
            if missing:
                violations.append(f"{claim.claim_id}:unknown_evidence")
                continue
            cited = [records[item] for item in claim.evidence_ids]
            if thesis and all(item.kind == EvidenceKind.USER_ASSERTION for item in cited):
                violations.append(f"{claim.claim_id}:user_assertion_only")
            if any(pattern.search(claim.text) for pattern in _PROHIBITED):
                violations.append(f"{claim.claim_id}:prohibited_financial_generation")
            supported_text = " ".join(f"{item.title} {item.value}" for item in cited).casefold()
            for number in _NUMBER.findall(claim.text):
                normalized_number = number.rstrip(".,")
                if normalized_number.casefold() not in supported_text:
                    violations.append(f"{claim.claim_id}:unsupported_number:{normalized_number}")
        return tuple(dict.fromkeys(violations))

    def supported_only(
        self, output: AssistantGeneratedOutput, packet: EvidencePacket, *, thesis: bool = False
    ) -> AssistantGeneratedOutput:
        invalid = {
            item.split(":", maxsplit=1)[0]
            for item in self.violations(output, packet, thesis=thesis)
        }

        def retained(claims: tuple[GroundedClaim, ...]) -> tuple[GroundedClaim, ...]:
            return tuple(claim for claim in claims if claim.claim_id not in invalid)

        return output.model_copy(
            update={
                "claims": retained(output.claims),
                "supportive": retained(output.supportive),
                "contradictory": retained(output.contradictory),
                "uncertainties": retained(output.uncertainties),
            }
        )

    @staticmethod
    def _claims(output: AssistantGeneratedOutput) -> tuple[GroundedClaim, ...]:
        return output.claims + output.supportive + output.contradictory + output.uncertainties
