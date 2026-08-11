from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, JsonValue, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class ComponentStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    EMPTY = "empty"
    STALE = "stale"
    ERROR = "error"


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageStatus(StrEnum):
    ACCEPTED = "accepted"
    STREAMING = "streaming"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ChatTurnStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    EXECUTING = "executing"
    RENDERING = "rendering"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ChatSessionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ConversationContextMessage(ContractModel):
    id: UUID
    role: ChatRole
    content: str
    created_at: datetime


class ConversationContext(ContractModel):
    session_id: UUID
    turn_id: UUID
    messages: tuple[ConversationContextMessage, ...] = ()


class ExecutionContext(ContractModel):
    request_id: UUID = Field(default_factory=uuid4)
    session_id: UUID | None = None
    principal_id: str = "anonymous"
    workflow_run_id: UUID | None = None
    capability_run_id: UUID | None = None
    permissions: tuple[str, ...] = ()
    locale: str = "en-IN"
    timezone: str = "Asia/Calcutta"
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    conversation: ConversationContext | None = None


class EvidenceSource(ContractModel):
    source_id: str
    provider: str
    title: str
    url: AnyHttpUrl
    published_at: datetime | None = None
    retrieved_at: datetime
    source_type: str
    reliability_weight: float | None = Field(default=None, ge=0, le=1)


class EvidenceKind(StrEnum):
    PROVIDER_OBSERVATION = "provider_observation"
    CALCULATED_METRIC = "calculated_metric"
    RESEARCH_CLAIM = "research_claim"
    METHODOLOGY = "methodology"
    COMMAND_CATALOG = "command_catalog"
    USER_ASSERTION = "user_assertion"


class EvidenceRecord(ContractModel):
    evidence_id: str = Field(pattern=r"^ev_[a-f0-9]{16}$")
    kind: EvidenceKind
    title: str = Field(min_length=1, max_length=240)
    value: str = Field(min_length=1, max_length=2_000)
    producer: str = Field(min_length=1, max_length=160)
    timestamp: datetime
    provider: str | None = Field(default=None, max_length=160)
    source_ids: tuple[str, ...] = ()
    run_id: UUID | None = None
    capability: str | None = None
    json_path: str | None = None
    data_cutoff: datetime | None = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    untrusted: bool = False


class GroundedClaim(ContractModel):
    claim_id: str = Field(pattern=r"^claim_[a-z0-9_-]+$")
    text: str = Field(min_length=1, max_length=1_200)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class FollowUpQuestion(ContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=500)


class CapabilityWarning(ContractModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)


class RunMetadata(ContractModel):
    run_id: UUID | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    attempts: int = Field(default=1, ge=1)
    data_cutoff: datetime | None = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"


class ComponentBase(ContractModel):
    id: str
    title: str | None = None
    status: ComponentStatus = ComponentStatus.READY
    source_ids: tuple[str, ...] = ()


class SummaryCard(ComponentBase):
    type: Literal["summary_card"] = "summary_card"
    heading: str
    body: str


class MetricItem(ContractModel):
    label: str
    value: str
    detail: str | None = None


class MetricGrid(ComponentBase):
    type: Literal["metric_grid"] = "metric_grid"
    metrics: tuple[MetricItem, ...]


class ChartPoint(ContractModel):
    timestamp: datetime
    value: float


class ChartSeries(ContractModel):
    name: str
    points: tuple[ChartPoint, ...]


class PriceChart(ComponentBase):
    type: Literal["price_chart"] = "price_chart"
    series: tuple[ChartSeries, ...]


class SentimentChart(ComponentBase):
    type: Literal["sentiment_chart"] = "sentiment_chart"
    series: tuple[ChartSeries, ...]


class TimelineItem(ContractModel):
    occurred_at: datetime
    headline: str
    description: str | None = None
    source_id: str | None = None


class NewsTimeline(ComponentBase):
    type: Literal["news_timeline"] = "news_timeline"
    items: tuple[TimelineItem, ...]


class EventTimelineItem(ContractModel):
    occurred_at: datetime
    label: str
    description: str | None = None
    category: str | None = None
    source_id: str | None = None


class EventTimeline(ComponentBase):
    type: Literal["event_timeline"] = "event_timeline"
    items: tuple[EventTimelineItem, ...]


class PredictionCard(ComponentBase):
    type: Literal["prediction_card"] = "prediction_card"
    direction: Literal["rise", "sideways", "decline", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    horizon: str
    generated_at: datetime
    data_cutoff: datetime
    model_version: str


class TableRow(ContractModel):
    cells: tuple[str, ...]


class ScenarioTable(ComponentBase):
    type: Literal["scenario_table"] = "scenario_table"
    columns: tuple[str, ...]
    rows: tuple[TableRow, ...]


class ComparisonTable(ComponentBase):
    type: Literal["comparison_table"] = "comparison_table"
    columns: tuple[str, ...]
    rows: tuple[TableRow, ...]


class RiskItem(ContractModel):
    label: str
    severity: Literal["low", "medium", "high", "unknown"]
    description: str


class RiskCard(ComponentBase):
    type: Literal["risk_card"] = "risk_card"
    risks: tuple[RiskItem, ...]


class SourceList(ComponentBase):
    type: Literal["source_list"] = "source_list"
    sources: tuple[EvidenceSource, ...]


class WarningBanner(ComponentBase):
    type: Literal["warning_banner"] = "warning_banner"
    code: str
    message: str


class CitedNarrative(ComponentBase):
    type: Literal["cited_narrative"] = "cited_narrative"
    claims: tuple[GroundedClaim, ...]


class MarketThesisComponent(ComponentBase):
    type: Literal["market_thesis"] = "market_thesis"
    supportive: tuple[GroundedClaim, ...] = ()
    contradictory: tuple[GroundedClaim, ...] = ()
    uncertainties: tuple[GroundedClaim, ...] = ()


class FollowUpQuestions(ComponentBase):
    type: Literal["follow_up_questions"] = "follow_up_questions"
    questions: tuple[FollowUpQuestion, ...] = Field(max_length=3)


LeafResponseComponent = Annotated[
    SummaryCard
    | MetricGrid
    | PriceChart
    | SentimentChart
    | NewsTimeline
    | EventTimeline
    | PredictionCard
    | ScenarioTable
    | ComparisonTable
    | RiskCard
    | SourceList
    | WarningBanner
    | CitedNarrative
    | MarketThesisComponent
    | FollowUpQuestions,
    Field(discriminator="type"),
]


class ResponseSection(ComponentBase):
    type: Literal["response_section"] = "response_section"
    description: str | None = None
    items: tuple[LeafResponseComponent, ...] = ()


ResponseComponent = Annotated[
    SummaryCard
    | MetricGrid
    | PriceChart
    | SentimentChart
    | NewsTimeline
    | EventTimeline
    | PredictionCard
    | ScenarioTable
    | ComparisonTable
    | RiskCard
    | SourceList
    | WarningBanner
    | CitedNarrative
    | MarketThesisComponent
    | FollowUpQuestions
    | ResponseSection,
    Field(discriminator="type"),
]


class CapabilityResult(ContractModel):
    capability: str
    status: RunStatus
    data: dict[str, JsonValue] = Field(default_factory=dict)
    summary: str | None = None
    sources: tuple[EvidenceSource, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    warnings: tuple[CapabilityWarning, ...] = ()
    components: tuple[ResponseComponent, ...] = ()
    metadata: RunMetadata


class CapabilityDescriptor(ContractModel):
    name: str
    version: str
    description: str
    dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    idempotent: bool = False


class RetryPolicy(ContractModel):
    max_attempts: int = Field(default=3, ge=1, le=10)
    initial_delay_ms: int = Field(default=100, ge=0, le=60_000)
    multiplier: float = Field(default=2.0, ge=1, le=10)
    max_delay_ms: int = Field(default=2_000, ge=0, le=300_000)
    jitter_ratio: float = Field(default=0.2, ge=0, le=1)


class TargetKind(StrEnum):
    CAPABILITY = "capability"
    WORKFLOW = "workflow"


class ExecutionTarget(ContractModel):
    kind: TargetKind
    name: str


class CommandArgument(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    required: bool = True


class CommandOption(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    destination: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    flag: bool = False
    required: bool = False


class CommandDescriptor(ContractModel):
    name: str = Field(pattern=r"^/[a-z][a-z0-9-]*$")
    description: str
    target: ExecutionTarget
    arguments: tuple[CommandArgument, ...] = ()
    options: tuple[CommandOption, ...] = ()
    examples: tuple[str, ...] = ()
    planner_enabled: bool = True
    side_effect: Literal["read", "write"] = "read"


class IntentDescriptor(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str
    examples: tuple[str, ...] = ()
    priority: int = 0
    target: ExecutionTarget
    match: Literal["exact", "fallback"] = "exact"
    input_field: str = Field(default="message", pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def validate_matching(self) -> IntentDescriptor:
        if self.match == "exact" and not self.examples:
            raise ValueError("exact intents require at least one example")
        if self.match == "fallback" and self.examples:
            raise ValueError("fallback intents cannot declare examples")
        return self


class IntentMatch(ContractModel):
    intent: str
    target: ExecutionTarget
    confidence: float = Field(ge=0, le=1)
    input_field: str


class WorkflowInputBinding(ContractModel):
    source: str = Field(
        pattern=(
            r"^(?:input(?:\.[a-zA-Z0-9_-]+)+|"
            r"steps\.[a-zA-Z0-9_-]+\.data(?:\.[a-zA-Z0-9_-]+)*)$"
        )
    )
    required: bool = True


class WorkflowStep(ContractModel):
    id: str
    capability: str
    depends_on: tuple[str, ...] = ()
    required: bool = True
    input_bindings: dict[str, WorkflowInputBinding] = Field(default_factory=dict)


class WorkflowPresentationSection(ContractModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=120)
    steps: tuple[str, ...] = Field(min_length=1)
    empty_message: str | None = Field(default=None, min_length=1, max_length=500)
    error_message: str | None = Field(default=None, min_length=1, max_length=500)


class WorkflowPresentation(ContractModel):
    title: str = Field(min_length=1, max_length=160)
    completion_event: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_.-]*$")
    sections: tuple[WorkflowPresentationSection, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_sections(self) -> WorkflowPresentation:
        identifiers = [section.id for section in self.sections]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("workflow presentation section IDs must be unique")
        steps = [step for section in self.sections for step in section.steps]
        if len(steps) != len(set(steps)):
            raise ValueError("workflow presentation steps may appear in only one section")
        return self


class WorkflowDefinition(ContractModel):
    name: str
    version: str
    description: str
    steps: tuple[WorkflowStep, ...]
    presentation: WorkflowPresentation | None = None

    @model_validator(mode="after")
    def validate_steps(self) -> WorkflowDefinition:
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("workflow step IDs must be unique")
        known = set(ids)
        for step in self.steps:
            missing = set(step.depends_on) - known
            if missing:
                raise ValueError(f"step {step.id} has unknown dependencies: {sorted(missing)}")
            if step.id in step.depends_on:
                raise ValueError(f"step {step.id} cannot depend on itself")
            for binding in step.input_bindings.values():
                parts = binding.source.split(".")
                if parts[0] == "steps" and parts[1] not in step.depends_on:
                    raise ValueError(
                        f"step {step.id} binding references undeclared dependency {parts[1]}"
                    )
        if self.presentation is not None:
            presented = {
                step_id for section in self.presentation.sections for step_id in section.steps
            }
            missing = presented - known
            if missing:
                raise ValueError(
                    f"workflow presentation references unknown steps: {sorted(missing)}"
                )
        return self


class WorkflowResult(ContractModel):
    workflow: str
    run_id: UUID
    status: RunStatus
    steps: dict[str, CapabilityResult]
    warnings: tuple[CapabilityWarning, ...] = ()
    started_at: datetime
    completed_at: datetime
    presentation: WorkflowPresentation | None = None


class CommandExecutionRequest(ContractModel):
    type: Literal["command"] = "command"
    command: str


class IntentExecutionRequest(ContractModel):
    type: Literal["intent"] = "intent"
    text: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class CapabilityExecutionRequest(ContractModel):
    type: Literal["capability"] = "capability"
    capability: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class WorkflowExecutionRequest(ContractModel):
    type: Literal["workflow"] = "workflow"
    workflow: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)


ExecutionRequest = Annotated[
    CommandExecutionRequest
    | IntentExecutionRequest
    | CapabilityExecutionRequest
    | WorkflowExecutionRequest,
    Field(discriminator="type"),
]


class RenderedResponse(ContractModel):
    status: RunStatus
    text: str
    components: tuple[ResponseComponent, ...] = ()
    sources: tuple[EvidenceSource, ...] = ()
    evidence: tuple[EvidenceRecord, ...] = ()
    warnings: tuple[CapabilityWarning, ...] = ()
    run_id: UUID | None = None
    generated_at: datetime
    trace: tuple[str, ...] = ()


class ExecutionOutcome(ContractModel):
    target: ExecutionTarget
    result: CapabilityResult | WorkflowResult
    response: RenderedResponse


class ExecutionPlan(ContractModel):
    request: ExecutionRequest
    target: ExecutionTarget
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    intent: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class ApiErrorDetail(ContractModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ChatSession(ContractModel):
    id: UUID
    title: str
    status: ChatSessionStatus
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ChatMessage(ContractModel):
    id: UUID
    session_id: UUID
    turn_id: UUID
    role: ChatRole
    content: str
    status: ChatMessageStatus
    response: RenderedResponse | None = None
    error: ApiErrorDetail | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ChatTurn(ContractModel):
    id: UUID
    session_id: UUID
    client_message_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID | None = None
    status: ChatTurnStatus
    request_id: UUID
    correlation_id: UUID
    run_id: UUID | None = None
    attempt: int = Field(default=0, ge=0)
    lease_expires_at: datetime | None = None
    error: ApiErrorDetail | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ChatSessionDetail(ContractModel):
    session: ChatSession
    messages: tuple[ChatMessage, ...] = ()
    active_turn: ChatTurn | None = None


class ChatSessionPage(ContractModel):
    items: tuple[ChatSession, ...] = ()
    next_cursor: str | None = None


class ChatTurnAccepted(ContractModel):
    session_id: UUID
    turn_id: UUID
    user_message_id: UUID
    status: ChatTurnStatus
    stream_url: str


class ChatStreamBase(ContractModel):
    version: str = "1.0.0"
    event_id: UUID = Field(default_factory=uuid4)
    sequence: int = Field(ge=1)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    session_id: UUID
    turn_id: UUID
    request_id: UUID
    correlation_id: UUID
    run_id: UUID | None = None


class ChatStatusEvent(ChatStreamBase):
    type: Literal["status"] = "status"
    status: ChatTurnStatus
    message: str


class ChatTypingEvent(ChatStreamBase):
    type: Literal["typing"] = "typing"
    active: bool


class ChatProgressEvent(ChatStreamBase):
    type: Literal["progress"] = "progress"
    stage: str
    label: str
    current: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)


class ChatResponseEvent(ChatStreamBase):
    type: Literal["response"] = "response"
    delta: str


class ChatComponentEvent(ChatStreamBase):
    type: Literal["component"] = "component"
    component: ResponseComponent


class ChatWarningEvent(ChatStreamBase):
    type: Literal["warning"] = "warning"
    warning: CapabilityWarning


class ChatCompleteEvent(ChatStreamBase):
    type: Literal["complete"] = "complete"
    turn: ChatTurn
    message: ChatMessage


class ChatErrorEvent(ChatStreamBase):
    type: Literal["error"] = "error"
    error: ApiErrorDetail


ChatStreamEvent = Annotated[
    ChatStatusEvent
    | ChatTypingEvent
    | ChatProgressEvent
    | ChatResponseEvent
    | ChatComponentEvent
    | ChatWarningEvent
    | ChatCompleteEvent
    | ChatErrorEvent,
    Field(discriminator="type"),
]


class EventEnvelope(ContractModel):
    event_id: UUID = Field(default_factory=uuid4)
    name: str
    version: str = "1.0.0"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID
    causation_id: UUID | None = None
    producer: str
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    attempt: int = Field(default=0, ge=0)


class ApiErrorResponse(ContractModel):
    error: ApiErrorDetail
    request_id: UUID


class Pagination(ContractModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    total: int = Field(ge=0)


class DependencyHealth(ContractModel):
    name: str
    status: Literal["healthy", "unhealthy", "disabled"]
    latency_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class HealthResult(ContractModel):
    service: str = "tradesentinel-api"
    version: str
    status: Literal["healthy", "degraded", "unhealthy"]
    checked_at: datetime
    dependencies: tuple[DependencyHealth, ...] = ()
