from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.sentiment import (
    AggregateSentimentInput,
    AnalysisStatus,
    CollectDiscussionsInput,
    CollectedDiscussions,
    CompanyDetectionInput,
    CompanyDetectionOutput,
    CompanyMention,
    DetectedDiscussion,
    Discussion,
    Narrative,
    NarrativeExtractionInput,
    NarrativeList,
    SentimentEvidence,
    SentimentLabel,
    SentimentShift,
    SentimentSignal,
    SentimentSnapshot,
    SentimentTrend,
    ShiftDetectionInput,
    SourceWeightInput,
    SourceWeightOutput,
    SpamDecision,
    SpamRemovalInput,
    SpamRemovalOutput,
    TrendBucket,
    TrendDetectionInput,
    WeightedObservation,
    WindowMetrics,
)
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import (
    ProviderContext,
    SentimentObservation,
    SentimentRequest,
)
from tradesentinel.providers.interfaces import SentimentProvider

TOKEN_RE = re.compile(r"[\w$#']+", re.UNICODE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
NEGATIONS = {"not", "no", "never", "isnt", "isn't", "without"}
POSITIVE = {"beat", "beats", "bullish", "growth", "great", "strong", "upside", "profit"}
NEGATIVE = {"bearish", "decline", "downside", "loss", "miss", "risk", "weak", "warning"}
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
}
TOPICS: dict[str, tuple[str, ...]] = {
    "earnings": ("earnings", "revenue", "profit", "guidance"),
    "growth": ("growth", "expansion", "demand"),
    "valuation": ("valuation", "overvalued", "undervalued", "multiple"),
    "products": ("product", "launch", "service"),
    "leadership": ("ceo", "leadership", "management"),
    "regulation/legal": ("regulation", "lawsuit", "legal", "regulator"),
    "operations": ("operations", "factory", "supply", "production"),
    "capital returns": ("dividend", "buyback", "repurchase"),
    "risk": ("risk", "uncertainty", "warning"),
}


def normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(TOKEN_RE.findall(normalized))


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 8)))


def classify(observation: SentimentObservation, version: str) -> SentimentSignal:
    if observation.label is not None:
        return SentimentSignal(
            label=SentimentLabel(observation.label),
            score=observation.provider_score,
            confidence=observation.provider_confidence,
            method="provider",
            version=observation.provider_model or "provider",
        )
    tokens = normalize(observation.text).split()
    positive = negative = 0
    for index, token in enumerate(tokens):
        polarity = 1 if token in POSITIVE else -1 if token in NEGATIVE else 0
        if polarity and any(item in NEGATIONS for item in tokens[max(0, index - 3) : index]):
            polarity *= -1
        positive += polarity > 0
        negative += polarity < 0
    hits = positive + negative
    if not hits:
        return SentimentSignal(label="unknown", method="none", version=version)
    score = Decimal(positive - negative) / Decimal(hits)
    label = "positive" if score > 0 else "negative" if score < 0 else "neutral"
    return SentimentSignal(
        label=label,
        score=score,
        confidence=min(Decimal("1"), Decimal(hits) / Decimal("3")),
        method="lexicon",
        version=version,
        positive_hits=positive,
        negative_hits=negative,
    )


class PublicSentimentService:
    def __init__(self, provider: SentimentProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    async def collect(
        self, context: ExecutionContext, request: CollectDiscussionsInput
    ) -> CollectedDiscussions:
        end = request.as_of or datetime.now(UTC)
        if end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        current_start = end - timedelta(days=request.window_days)
        previous_start = current_start - timedelta(days=request.window_days)
        observations = await self._provider.collect(
            ProviderContext(
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                capability_run_id=context.capability_run_id,
            ),
            SentimentRequest(
                query=f"{request.target.symbol} {request.target.name}",
                start=previous_start,
                end=end,
                limit=request.limit,
            ),
        )
        discussions = tuple(
            sorted(
                (self._discussion(item) for item in observations),
                key=lambda x: (x.occurred_at, str(x.discussion_id)),
            )
        )
        return CollectedDiscussions(
            target=request.target,
            previous_start=previous_start,
            current_start=current_start,
            end=end,
            discussions=discussions,
        )

    def _discussion(self, item: SentimentObservation) -> Discussion:
        raw_author = item.author_id
        author_hash = hashlib.sha256(raw_author.encode()).hexdigest() if raw_author else None
        content_hash = hashlib.sha256(normalize(item.text).encode()).hexdigest()
        return Discussion(
            discussion_id=uuid5(
                NAMESPACE_URL, f"sentiment:{item.metadata.provider}:{item.source_id}"
            ),
            provider_source_id=item.source_id,
            text_excerpt=item.text[: self._settings.sentiment_excerpt_length],
            content_hash=content_hash,
            occurred_at=item.occurred_at,
            author_hash=author_hash,
            language=item.language,
            engagement_count=item.engagement_count,
            provider_spam=item.provider_spam,
            evidence=SentimentEvidence(
                source_id=item.source_id,
                provider=item.metadata.provider,
                source_type=item.source_type,
                observed_at=item.occurred_at,
                retrieved_at=item.metadata.retrieved_at,
                url=item.url,
            ),
            signal=classify(item, self._settings.sentiment_lexicon_version),
        )

    def remove_spam(self, request: SpamRemovalInput) -> SpamRemovalOutput:
        seen: set[str] = set()
        author_times: dict[str, deque[datetime]] = defaultdict(deque)
        retained: list[Discussion] = []
        decisions: list[SpamDecision] = []
        for discussion in sorted(
            request.discussions, key=lambda x: (x.occurred_at, str(x.discussion_id))
        ):
            text = discussion.text_excerpt
            tokens = normalize(text).split()
            reasons: list[str] = []
            if discussion.provider_spam:
                reasons.append("provider_spam")
            if len(tokens) < self._settings.sentiment_spam_minimum_tokens:
                reasons.append("too_short")
            if len(URL_RE.findall(text)) > self._settings.sentiment_spam_max_urls:
                reasons.append("too_many_urls")
            if (
                sum(token.startswith(("#", "$")) for token in TOKEN_RE.findall(text))
                > self._settings.sentiment_spam_max_tags
            ):
                reasons.append("too_many_tags")
            if (
                len(tokens) >= 5
                and max((tokens.count(token) for token in set(tokens)), default=0) / len(tokens)
                > self._settings.sentiment_spam_repeated_ratio
            ):
                reasons.append("repeated_tokens")
            if discussion.content_hash in seen:
                reasons.append("duplicate")
            seen.add(discussion.content_hash)
            if discussion.author_hash:
                queue = author_times[discussion.author_hash]
                while queue and discussion.occurred_at - queue[0] > timedelta(minutes=10):
                    queue.popleft()
                if len(queue) >= self._settings.sentiment_spam_author_burst:
                    reasons.append("author_burst")
                queue.append(discussion.occurred_at)
            decision = SpamDecision(
                discussion_id=discussion.discussion_id,
                spam=bool(reasons),
                reasons=tuple(dict.fromkeys(reasons)),
            )
            decisions.append(decision)
            if not reasons:
                retained.append(discussion)
        return SpamRemovalOutput(retained=tuple(retained), decisions=tuple(decisions))

    def detect_companies(self, request: CompanyDetectionInput) -> CompanyDetectionOutput:
        detected: list[DetectedDiscussion] = []
        co: dict[UUID, InstrumentRef] = {}
        target_name = normalize(request.target.name)
        for discussion in request.discussions:
            plain = normalize(discussion.text_excerpt)
            raw = discussion.text_excerpt.casefold()
            mentions: dict[UUID, CompanyMention] = {}
            for instrument in request.catalog:
                symbol = instrument.symbol.casefold()
                candidates = [(f"${symbol}" in raw, "cashtag", instrument.symbol, "1")]
                if len(symbol) >= 3:
                    candidates.append(
                        (
                            bool(re.search(rf"\b{re.escape(symbol)}\b", plain)),
                            "symbol",
                            instrument.symbol,
                            "0.95",
                        )
                    )
                candidates.append(
                    (normalize(instrument.name) in plain, "name", instrument.name, "0.98")
                )
                candidates.extend(
                    (normalize(alias) in plain, "alias", alias, "0.96")
                    for alias in instrument.aliases
                    if len(normalize(alias)) >= 3
                )
                matches = [item for item in candidates if item[0]]
                if matches:
                    _, method, value, confidence = max(matches, key=lambda item: Decimal(item[3]))
                    mentions[instrument.instrument_id] = CompanyMention(
                        instrument=instrument,
                        matched_value=value,
                        method=method,
                        confidence=Decimal(confidence),
                    )
            relevant = request.target.instrument_id in mentions or any(
                normalize(item.instrument.name) == target_name for item in mentions.values()
            )
            for item in mentions.values():
                if item.instrument.instrument_id != request.target.instrument_id:
                    co[item.instrument.instrument_id] = item.instrument
            detected.append(
                DetectedDiscussion(
                    discussion=discussion,
                    mentions=tuple(
                        sorted(
                            mentions.values(),
                            key=lambda x: (x.instrument.exchange, x.instrument.symbol),
                        )
                    ),
                    target_relevant=relevant,
                )
            )
        return CompanyDetectionOutput(
            target=request.target,
            discussions=tuple(detected),
            relevant=tuple(item for item in detected if item.target_relevant),
            co_mentions=tuple(sorted(co.values(), key=lambda x: (x.exchange, x.symbol))),
        )

    def weight_sources(self, request: SourceWeightInput) -> SourceWeightOutput:
        output = []
        for item in request.discussions:
            provider = Decimal(
                str(
                    self._settings.sentiment_provider_weights.get(
                        item.discussion.evidence.provider, 1.0
                    )
                )
            )
            source_type = Decimal(
                str(
                    self._settings.sentiment_source_type_weights.get(
                        item.discussion.evidence.source_type, 1.0
                    )
                )
            )
            multiplier = Decimal(
                str(1 + min(math.log1p(item.discussion.engagement_count) / 10, 0.5))
            )
            output.append(
                WeightedObservation(
                    discussion=item.discussion,
                    mentions=item.mentions,
                    provider_weight=provider,
                    source_type_weight=source_type,
                    engagement_multiplier=multiplier,
                    weight=provider * source_type * multiplier,
                )
            )
        return SourceWeightOutput(
            observations=tuple(
                sorted(
                    output,
                    key=lambda x: (x.discussion.occurred_at, str(x.discussion.discussion_id)),
                )
            )
        )

    def _metrics(
        self, observations: tuple[WeightedObservation, ...], start: datetime, end: datetime
    ) -> WindowMetrics:
        all_items = tuple(
            item for item in observations if start <= item.discussion.occurred_at < end
        )
        usable = tuple(
            item
            for item in all_items
            if item.discussion.signal.score is not None
            and item.discussion.signal.confidence is not None
        )
        weighted = tuple(
            (
                item,
                item.weight * (item.discussion.signal.confidence or Decimal()),
                item.discussion.signal.score or Decimal(),
                item.discussion.signal.confidence or Decimal(),
            )
            for item in usable
        )
        weights = [entry[1] for entry in weighted]
        total = sum(weights, Decimal())
        if not usable or total == 0:
            return WindowMetrics(start=start, end=end, mention_count=len(all_items), usable_count=0)
        mean = (
            sum(
                (weight * score for _, weight, score, _ in weighted),
                Decimal(),
            )
            / total
        )
        shares = {
            label: sum(
                (
                    weight
                    for item, weight, _, _ in weighted
                    if item.discussion.signal.label == label
                ),
                Decimal(),
            )
            / total
            for label in (SentimentLabel.POSITIVE, SentimentLabel.NEUTRAL, SentimentLabel.NEGATIVE)
        }
        deviation = (
            sum(
                (weight * abs(score - mean) for _, weight, score, _ in weighted),
                Decimal(),
            )
            / total
        )
        agreement = max(Decimal(), Decimal(1) - deviation / Decimal(2))
        signal_confidence = (
            sum(
                (weight * confidence for _, weight, _, confidence in weighted),
                Decimal(),
            )
            / total
        )
        return WindowMetrics(
            start=start,
            end=end,
            mention_count=len(all_items),
            usable_count=len(usable),
            positive_share=shares[SentimentLabel.POSITIVE],
            neutral_share=shares[SentimentLabel.NEUTRAL],
            negative_share=shares[SentimentLabel.NEGATIVE],
            mean_score=mean,
            agreement=agreement,
            mean_signal_confidence=signal_confidence,
        )

    def aggregate(self, request: AggregateSentimentInput) -> SentimentSnapshot:
        current = self._metrics(request.observations, request.current_start, request.end)
        previous = self._metrics(
            request.observations, request.previous_start, request.current_start
        )
        warnings: list[str] = []
        status = AnalysisStatus.COMPLETED
        if current.usable_count == 0:
            status, warnings = (
                AnalysisStatus.EMPTY,
                ["No usable sentiment observations were available."],
            )
        elif current.usable_count < self._settings.sentiment_minimum_mentions:
            status, warnings = (
                AnalysisStatus.PARTIAL,
                ["The current window contains sparse sentiment evidence."],
            )
        if previous.usable_count == 0:
            status = AnalysisStatus.PARTIAL if current.usable_count else status
            warnings.append("The previous window contains no usable baseline.")
        coverage = min(
            Decimal(1),
            Decimal(current.usable_count) / Decimal(self._settings.sentiment_minimum_mentions),
        )
        confidence = (
            None
            if current.agreement is None
            else Decimal("0.4") * coverage
            + Decimal("0.3") * current.agreement
            + Decimal("0.3") * (current.mean_signal_confidence or Decimal())
        )
        volume_change = (
            None
            if previous.mention_count == 0
            else Decimal(current.mention_count - previous.mention_count)
            / Decimal(previous.mention_count)
        )
        fingerprint = (
            f"{request.target.instrument_id}:{request.current_start.isoformat()}:"
            f"{request.end.isoformat()}"
        )
        return SentimentSnapshot(
            snapshot_id=uuid5(NAMESPACE_URL, f"sentiment-snapshot:{fingerprint}"),
            target=request.target,
            status=status,
            as_of=request.end,
            current=current,
            previous=previous,
            volume_change=volume_change,
            confidence=confidence,
            co_mentions=request.co_mentions,
            warnings=tuple(warnings),
            lexicon_version=self._settings.sentiment_lexicon_version,
        )

    def narratives(self, request: NarrativeExtractionInput) -> NarrativeList:
        items = tuple(
            item
            for item in request.observations
            if request.current_start <= item.discussion.occurred_at < request.end
            and item.discussion.signal.score is not None
        )
        tokens_to_remove = {
            normalize(request.target.symbol),
            *normalize(request.target.name).split(),
            *(normalize(alias) for alias in request.target.aliases),
        } | STOPWORDS
        groups: dict[tuple[str, str], set[UUID]] = defaultdict(set)
        for item in items:
            words = [
                word
                for word in normalize(URL_RE.sub(" ", item.discussion.text_excerpt)).split()
                if word not in tokens_to_remove and not word.startswith(("#", "$"))
            ]
            for topic, terms in TOPICS.items():
                if set(words).intersection(terms):
                    groups[("taxonomy", topic)].add(item.discussion.discussion_id)
            for size in (2, 3):
                for index in range(len(words) - size + 1):
                    groups[("ngram", " ".join(words[index : index + size]))].add(
                        item.discussion.discussion_id
                    )
        by_id = {item.discussion.discussion_id: item for item in items}
        candidates = [
            (key, ids) for key, ids in groups.items() if key[0] == "taxonomy" or len(ids) >= 2
        ]
        total_weight = sum((item.weight for item in items), Decimal()) or Decimal(1)
        narratives = []
        for (method, topic), ids in candidates:
            selected = tuple(by_id[item_id] for item_id in sorted(ids, key=str))
            weight = sum((item.weight for item in selected), Decimal())
            score = (
                sum(
                    (
                        item.weight * (item.discussion.signal.score or Decimal())
                        for item in selected
                    ),
                    Decimal(),
                )
                / weight
            )
            label = (
                SentimentLabel.POSITIVE
                if score > Decimal("0.1")
                else SentimentLabel.NEGATIVE
                if score < Decimal("-0.1")
                else SentimentLabel.NEUTRAL
            )
            confidence = sum(
                (item.discussion.signal.confidence or Decimal() for item in selected), Decimal()
            ) / Decimal(len(selected))
            narratives.append(
                Narrative(
                    narrative_id=uuid5(
                        NAMESPACE_URL,
                        f"narrative:{request.target.instrument_id}:{method}:{topic}:{request.current_start.date()}",
                    ),
                    topic=topic,
                    method=method,
                    sentiment=label,
                    weighted_share=min(Decimal(1), weight / total_weight),
                    mention_count=len(selected),
                    confidence=confidence,
                    discussion_ids=tuple(item.discussion.discussion_id for item in selected),
                    providers=tuple(
                        sorted({item.discussion.evidence.provider for item in selected})
                    ),
                    observation_timestamps=tuple(
                        sorted(item.discussion.occurred_at for item in selected)
                    ),
                )
            )
        ordered = tuple(
            sorted(narratives, key=lambda x: (-x.weighted_share, x.method, x.topic))[
                : self._settings.sentiment_narrative_limit
            ]
        )
        return NarrativeList(
            target=request.target,
            status=AnalysisStatus.COMPLETED if ordered else AnalysisStatus.EMPTY,
            narratives=ordered,
        )

    def trend(self, request: TrendDetectionInput) -> SentimentTrend:
        days: dict[datetime, list[WeightedObservation]] = defaultdict(list)
        for item in request.observations:
            if request.start <= item.discussion.occurred_at < request.end:
                day = item.discussion.occurred_at.astimezone(UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                days[day].append(item)
        buckets = tuple(
            TrendBucket(
                day=day,
                mention_count=len(items),
                mean_score=self._metrics(tuple(items), day, day + timedelta(days=1)).mean_score,
            )
            for day, items in sorted(days.items())
        )
        usable = tuple(bucket for bucket in buckets if bucket.mean_score is not None)
        if len(usable) < 2:
            return SentimentTrend(
                target=request.target,
                status="insufficient",
                direction="insufficient",
                buckets=buckets,
            )
        ys = [float(bucket.mean_score) for bucket in usable if bucket.mean_score is not None]
        xs = list(range(len(ys)))
        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / sum(
            (x - mean_x) ** 2 for x in xs
        )
        threshold = self._settings.sentiment_trend_stability_threshold
        direction = (
            "stable" if abs(slope) <= threshold else "improving" if slope > 0 else "deteriorating"
        )
        acceleration = None if len(ys) < 4 else _decimal((ys[-1] - ys[-2]) - (ys[1] - ys[0]))
        return SentimentTrend(
            target=request.target,
            status="completed",
            direction=direction,
            slope=_decimal(slope),
            acceleration=acceleration,
            buckets=buckets,
        )

    def shift(self, request: ShiftDetectionInput) -> SentimentShift:
        snapshot = request.snapshot
        if (
            snapshot.current.mean_score is None
            or snapshot.previous.mean_score is None
            or snapshot.previous.mention_count == 0
        ):
            return SentimentShift(
                target=snapshot.target,
                status="insufficient",
                description=(
                    "No usable previous window is available; no shift score was calculated."
                ),
            )
        sentiment_component = (
            snapshot.current.mean_score - snapshot.previous.mean_score
        ) / Decimal(2)
        volume_component = _decimal(
            math.tanh(
                math.log(
                    (snapshot.current.mention_count + 1) / (snapshot.previous.mention_count + 1)
                )
            )
        )
        sign = (
            Decimal(1)
            if sentiment_component > 0
            else Decimal(-1)
            if sentiment_component < 0
            else Decimal()
        )
        score = max(
            Decimal(-1),
            min(
                Decimal(1),
                Decimal("0.75") * sentiment_component + Decimal("0.25") * sign * volume_component,
            ),
        )
        return SentimentShift(
            target=snapshot.target,
            status="completed",
            shift_score=score,
            sentiment_component=sentiment_component,
            volume_component=volume_component,
            description=(
                "Descriptive change in observed sentiment and discussion volume; "
                "it is not a prediction."
            ),
        )
