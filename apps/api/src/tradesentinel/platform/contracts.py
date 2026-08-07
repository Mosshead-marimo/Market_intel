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


class EvidenceSource(ContractModel):
    source_id: str
    provider: str
    title: str
    url: AnyHttpUrl
    published_at: datetime | None = None
    retrieved_at: datetime
    source_type: str
    reliability_weight: float | None = Field(default=None, ge=0, le=1)


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


ResponseComponent = Annotated[
    SummaryCard
    | MetricGrid
    | PriceChart
    | SentimentChart
    | NewsTimeline
    | PredictionCard
    | ScenarioTable
    | ComparisonTable
    | RiskCard
    | SourceList
    | WarningBanner,
    Field(discriminator="type"),
]


class CapabilityResult(ContractModel):
    capability: str
    status: RunStatus
    data: dict[str, JsonValue] = Field(default_factory=dict)
    summary: str | None = None
    sources: tuple[EvidenceSource, ...] = ()
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


class IntentDescriptor(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    description: str
    examples: tuple[str, ...] = Field(min_length=1)
    priority: int = 0
    target: ExecutionTarget


class IntentMatch(ContractModel):
    intent: str
    target: ExecutionTarget
    confidence: float = Field(ge=0, le=1)


class WorkflowStep(ContractModel):
    id: str
    capability: str
    depends_on: tuple[str, ...] = ()
    required: bool = True


class WorkflowDefinition(ContractModel):
    name: str
    version: str
    description: str
    steps: tuple[WorkflowStep, ...]

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
        return self


class WorkflowResult(ContractModel):
    workflow: str
    run_id: UUID
    status: RunStatus
    steps: dict[str, CapabilityResult]
    warnings: tuple[CapabilityWarning, ...] = ()
    started_at: datetime
    completed_at: datetime


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
    warnings: tuple[CapabilityWarning, ...] = ()
    run_id: UUID | None = None
    generated_at: datetime
    trace: tuple[str, ...] = ()


class ExecutionOutcome(ContractModel):
    target: ExecutionTarget
    result: CapabilityResult | WorkflowResult
    response: RenderedResponse


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


class ApiErrorDetail(ContractModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)


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
