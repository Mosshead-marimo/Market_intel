from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from statistics import mean
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tradesentinel.domain.market_shift import (
    MarketShiftCategory,
    MarketShiftCategorySignal,
    MarketShiftDirection,
    MarketShiftDriver,
    MarketShiftEvidence,
    MarketShiftNarrative,
    MarketShiftObservation,
    MarketShiftScoreInput,
    MarketShiftSnapshot,
)
from tradesentinel.modules.market_shift.errors import (
    MarketShiftConfigurationError,
    MarketShiftInputIncompleteError,
)

ZERO = Decimal("0")
ONE = Decimal("1")


class _RuleModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CategoryRule(_RuleModel):
    weight: Decimal = Field(gt=0, le=1)
    maximum_age_hours: int = Field(gt=0)


class MetricRule(_RuleModel):
    category: MarketShiftCategory
    unit: str
    scale: Decimal = Field(gt=0)
    polarity: Literal["positive_when_rising", "negative_when_rising", "context_only"]
    weight: Decimal = Field(gt=0)


class ScoringConfiguration(_RuleModel):
    version: str
    confidence_threshold: Decimal = Field(ge=0, le=1)
    direction_thresholds: dict[str, Decimal]
    confidence_weights: dict[str, Decimal]
    categories: dict[MarketShiftCategory, CategoryRule]
    metrics: dict[str, MetricRule]

    @model_validator(mode="after")
    def validate_complete(self) -> ScoringConfiguration:
        if set(self.categories) != set(MarketShiftCategory):
            raise ValueError("configuration must declare every Market Shift category")
        if sum((item.weight for item in self.categories.values()), ZERO) != ONE:
            raise ValueError("category weights must sum to one")
        expected_confidence = {"coverage", "freshness", "agreement", "temporal_alignment"}
        if set(self.confidence_weights) != expected_confidence:
            raise ValueError("confidence weights are incomplete")
        if sum(self.confidence_weights.values(), ZERO) != ONE:
            raise ValueError("confidence weights must sum to one")
        if not {"improving", "deteriorating"} <= set(self.direction_thresholds):
            raise ValueError("direction thresholds are incomplete")
        for name, rule in self.metrics.items():
            if rule.category not in self.categories:
                raise ValueError(f"metric {name} references an unknown category")
        return self


def load_configuration(path: Path | None = None) -> ScoringConfiguration:
    source = path or Path(__file__).with_name("scoring.yaml")
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
        return ScoringConfiguration.model_validate(value)
    except (OSError, yaml.YAMLError, ValidationError, ValueError) as exc:
        raise MarketShiftConfigurationError() from exc


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _bounded(value: Decimal, lower: Decimal = -ONE, upper: Decimal = ONE) -> Decimal:
    return max(lower, min(upper, value))


class MarketShiftScoringService:
    def __init__(self) -> None:
        self.configuration = load_configuration()
        self.configuration_fingerprint = _digest(self.configuration.model_dump(mode="json"))

    def calculate(self, payload: MarketShiftScoreInput) -> MarketShiftSnapshot:
        by_category: dict[MarketShiftCategory, list[MarketShiftObservation]] = {
            category: [] for category in MarketShiftCategory
        }
        for observation in payload.observations:
            if (
                observation.known_at > payload.window.end
                or observation.retrieved_at > payload.window.end
            ):
                continue
            if observation.instrument_id not in {None, payload.instrument.instrument_id}:
                continue
            by_category[observation.category].append(observation)

        missing: list[str] = []
        selected: dict[
            MarketShiftCategory,
            list[tuple[str, MetricRule, MarketShiftObservation, MarketShiftObservation]],
        ] = {}
        for category, observations in by_category.items():
            pairs: list[tuple[str, MetricRule, MarketShiftObservation, MarketShiftObservation]] = []
            for metric, rule in self.configuration.metrics.items():
                if rule.category != category or rule.polarity == "context_only":
                    continue
                candidates = [item for item in observations if item.metric == metric]
                current = self._latest(candidates, payload.window.current_start, payload.window.end)
                previous = self._latest(
                    candidates, payload.window.previous_start, payload.window.current_start
                )
                if current is not None and previous is not None:
                    age_hours = (payload.window.end - current.retrieved_at).total_seconds() / 3600
                    if age_hours > self.configuration.categories[category].maximum_age_hours:
                        continue
                    if current.unit != rule.unit or previous.unit != rule.unit:
                        continue
                    pairs.append((metric, rule, current, previous))
            if not pairs:
                missing.append(category.value)
            selected[category] = pairs
        if missing:
            raise MarketShiftInputIncompleteError(tuple(sorted(missing)))

        evidence: list[MarketShiftEvidence] = []
        signals: list[MarketShiftCategorySignal] = []
        deltas: dict[MarketShiftCategory, list[tuple[str, Decimal, str, datetime]]] = {}
        window_seconds = Decimal(
            str((payload.window.end - payload.window.current_start).total_seconds())
        )
        for category in MarketShiftCategory:
            category_rule = self.configuration.categories[category]
            values: list[tuple[str, Decimal, str, datetime]] = []
            metric_weight_total = ZERO
            metric_score_total = ZERO
            freshness_values: list[Decimal] = []
            alignment_values: list[Decimal] = []
            for metric, rule, current, previous in selected[category]:
                sign = Decimal("-1") if rule.polarity == "negative_when_rising" else ONE
                delta = _bounded(((current.value - previous.value) / rule.scale) * sign)
                fingerprint = _digest((current.source_id, previous.source_id, metric, delta))
                evidence_id = f"mse_{fingerprint[:16]}"
                evidence.append(
                    MarketShiftEvidence(
                        evidence_id=evidence_id,
                        category=category,
                        metric=metric,
                        source_id=current.source_id,
                        provider=current.provider,
                        timestamp=current.observed_at,
                        current_value=current.value,
                        previous_value=previous.value,
                        normalized_delta=delta,
                        source_url=current.source_url,
                    )
                )
                values.append((metric, delta, evidence_id, current.observed_at))
                metric_score_total += delta * rule.weight
                metric_weight_total += rule.weight
                age_seconds = max(0.0, (payload.window.end - current.retrieved_at).total_seconds())
                evidence_age_hours = Decimal(str(age_seconds / 3600))
                freshness_values.append(
                    _bounded(
                        ONE - evidence_age_hours / Decimal(category_rule.maximum_age_hours),
                        ZERO,
                        ONE,
                    )
                )
                gap = Decimal(str(abs((payload.window.end - current.observed_at).total_seconds())))
                alignment_values.append(_bounded(ONE - gap / window_seconds, ZERO, ONE))
            category_score = _bounded(metric_score_total / metric_weight_total)
            agreement = _bounded(
                ONE
                - Decimal(str(mean(float(abs(item[1] - category_score)) for item in values)))
                / Decimal("2"),
                ZERO,
                ONE,
            )
            configured_count = sum(
                rule.category == category and rule.polarity != "context_only"
                for rule in self.configuration.metrics.values()
            )
            coverage = Decimal(len(values)) / Decimal(configured_count)
            freshness = Decimal(str(mean(float(value) for value in freshness_values)))
            alignment = Decimal(str(mean(float(value) for value in alignment_values)))
            confidence = (
                coverage * self.configuration.confidence_weights["coverage"]
                + freshness * self.configuration.confidence_weights["freshness"]
                + agreement * self.configuration.confidence_weights["agreement"]
                + alignment * self.configuration.confidence_weights["temporal_alignment"]
            ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            signals.append(
                MarketShiftCategorySignal(
                    category=category,
                    score=category_score.quantize(Decimal("0.0001")),
                    weight=category_rule.weight,
                    weighted_contribution=(category_score * category_rule.weight).quantize(
                        Decimal("0.0001")
                    ),
                    coverage=coverage,
                    freshness=freshness,
                    agreement=agreement,
                    temporal_alignment=alignment,
                    confidence=confidence,
                    evidence_ids=tuple(item[2] for item in values),
                )
            )
            deltas[category] = values

        score = (
            sum((signal.weighted_contribution for signal in signals), ZERO) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        confidence = sum((signal.confidence * signal.weight for signal in signals), ZERO).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
        direction = self._direction(score, confidence)
        drivers = [
            MarketShiftDriver(
                label=metric.replace("_", " ").title(),
                category=category,
                contribution=(delta * self.configuration.categories[category].weight).quantize(
                    Decimal("0.0001")
                ),
                confidence=next(item.confidence for item in signals if item.category == category),
                observed_at=timestamp,
                evidence_ids=(evidence_id,),
            )
            for category, values in deltas.items()
            for metric, delta, evidence_id, timestamp in values
        ]
        catalysts = tuple(
            sorted(
                (item for item in drivers if item.contribution > ZERO),
                key=lambda item: (-item.contribution, item.label),
            )[:5]
        )
        risks = tuple(
            sorted(
                (item for item in drivers if item.contribution < ZERO),
                key=lambda item: (item.contribution, item.label),
            )[:5]
        )
        narratives = tuple(self._narrative(item) for item in (*catalysts, *risks))
        generated_at = datetime.now(UTC)
        input_fingerprint = _digest(
            [
                item.model_dump(mode="json")
                for item in sorted(
                    payload.observations,
                    key=lambda value: str(value.observation_id),
                )
            ]
        )
        calculation_id = uuid5(
            NAMESPACE_URL,
            f"market-shift:{payload.instrument.instrument_id}:{payload.idempotency_key}:{input_fingerprint}",
        )
        return MarketShiftSnapshot(
            calculation_id=calculation_id,
            instrument=payload.instrument,
            generated_at=generated_at,
            data_cutoff=payload.window.end,
            window=payload.window,
            score=score,
            direction=direction,
            confidence=confidence,
            category_signals=tuple(signals),
            catalysts=catalysts,
            risks=risks,
            narratives=narratives,
            evidence=tuple(evidence),
            scoring_rule_version=self.configuration.version,
            configuration_fingerprint=self.configuration_fingerprint,
            input_fingerprint=input_fingerprint,
        )

    @staticmethod
    def _latest(
        values: list[MarketShiftObservation], start: datetime, end: datetime
    ) -> MarketShiftObservation | None:
        eligible = [
            item for item in values if start <= item.observed_at < end and item.known_at <= end
        ]
        return max(
            eligible,
            key=lambda item: (
                item.observed_at,
                item.known_at,
                str(item.observation_id),
            ),
            default=None,
        )

    def _direction(self, score: Decimal, confidence: Decimal) -> MarketShiftDirection:
        if confidence < self.configuration.confidence_threshold:
            return MarketShiftDirection.UNCERTAIN
        if score >= self.configuration.direction_thresholds["improving"]:
            return MarketShiftDirection.IMPROVING
        if score <= self.configuration.direction_thresholds["deteriorating"]:
            return MarketShiftDirection.DETERIORATING
        return MarketShiftDirection.STABLE

    @staticmethod
    def _narrative(driver: MarketShiftDriver) -> MarketShiftNarrative:
        magnitude = min(ONE, abs(driver.contribution) * Decimal("5"))
        positive = driver.contribution > ZERO
        return MarketShiftNarrative(
            narrative_id=(
                f"msn_{_digest((driver.label, driver.category, driver.contribution))[:16]}"
            ),
            label=driver.label,
            direction="strengthening" if positive else "weakening",
            current_prevalence=magnitude if positive else ZERO,
            previous_prevalence=ZERO if positive else magnitude,
            change=magnitude if positive else -magnitude,
            evidence_ids=driver.evidence_ids,
        )
