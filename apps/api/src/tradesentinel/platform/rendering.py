from __future__ import annotations

from datetime import UTC, datetime

from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ComponentStatus,
    LeafResponseComponent,
    RenderedResponse,
    ResponseComponent,
    ResponseSection,
    RunStatus,
    WarningBanner,
    WorkflowResult,
)


class ResponseRenderer:
    def render(self, result: CapabilityResult | WorkflowResult) -> RenderedResponse:
        all_results = (
            (result,) if isinstance(result, CapabilityResult) else tuple(result.steps.values())
        )
        capability_results = self._presented_results(result, all_results)
        summaries = [item.summary.strip() for item in capability_results if item.summary]
        warnings: list[CapabilityWarning] = []
        if isinstance(result, WorkflowResult):
            warnings.extend(result.warnings)
        for item in capability_results:
            warnings.extend(item.warnings)
        title = (
            result.presentation.title
            if isinstance(result, WorkflowResult) and result.presentation is not None
            else None
        )
        text_parts = ([title] if title else []) + summaries
        if not text_parts:
            text_parts = [f"Execution completed with status {result.status.value}."]
        if warnings:
            text_parts.append("Warnings: " + "; ".join(warning.message for warning in warnings))

        seen_sources: set[str] = set()
        sources = []
        for item in capability_results:
            for source in item.sources:
                if source.source_id not in seen_sources:
                    sources.append(source)
                    seen_sources.add(source.source_id)

        run_id = result.metadata.run_id if isinstance(result, CapabilityResult) else result.run_id
        components = (
            self._sections(result)
            if isinstance(result, WorkflowResult) and result.presentation is not None
            else tuple(component for item in capability_results for component in item.components)
        )
        return RenderedResponse(
            status=result.status,
            text="\n".join(text_parts),
            components=components,
            sources=tuple(sources),
            warnings=tuple(warnings),
            run_id=run_id,
            generated_at=datetime.now(UTC),
            trace=tuple(item.capability for item in all_results),
        )

    @staticmethod
    def _presented_results(
        result: CapabilityResult | WorkflowResult,
        all_results: tuple[CapabilityResult, ...],
    ) -> tuple[CapabilityResult, ...]:
        if not isinstance(result, WorkflowResult) or result.presentation is None:
            return all_results
        step_ids = tuple(
            step_id for section in result.presentation.sections for step_id in section.steps
        )
        return tuple(result.steps[step_id] for step_id in step_ids)

    @staticmethod
    def _sections(result: WorkflowResult) -> tuple[ResponseComponent, ...]:
        if result.presentation is None:
            return ()
        output: list[ResponseComponent] = []
        for section in result.presentation.sections:
            results = tuple(result.steps[step_id] for step_id in section.steps)
            items: list[LeafResponseComponent] = []
            for capability_result in results:
                for component in capability_result.components:
                    if isinstance(component, ResponseSection):
                        items.extend(component.items)
                    else:
                        items.append(component)
            failed = tuple(
                item for item in results if item.status in {RunStatus.FAILED, RunStatus.SKIPPED}
            )
            if failed:
                status = ComponentStatus.PARTIAL if items else ComponentStatus.ERROR
                message = section.error_message or next(
                    (warning.message for item in failed for warning in item.warnings),
                    f"{section.title} is unavailable.",
                )
                items.append(
                    WarningBanner(
                        id=f"{section.id}-unavailable",
                        status=ComponentStatus.ERROR,
                        code="SECTION_UNAVAILABLE",
                        message=message,
                    )
                )
            elif any(item.status == RunStatus.PARTIAL for item in results):
                status = ComponentStatus.PARTIAL
            elif not items:
                status = ComponentStatus.EMPTY
            else:
                status = ComponentStatus.READY
            output.append(
                ResponseSection(
                    id=section.id,
                    title=section.title,
                    status=status,
                    description=(
                        section.empty_message if status == ComponentStatus.EMPTY else None
                    ),
                    source_ids=tuple(
                        dict.fromkeys(
                            source.source_id for item in results for source in item.sources
                        )
                    ),
                    items=tuple(items),
                )
            )
        return tuple(output)
