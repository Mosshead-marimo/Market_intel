from __future__ import annotations

from datetime import UTC, datetime

from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    RenderedResponse,
    WorkflowResult,
)


class ResponseRenderer:
    def render(self, result: CapabilityResult | WorkflowResult) -> RenderedResponse:
        capability_results = (
            (result,) if isinstance(result, CapabilityResult) else tuple(result.steps.values())
        )
        summaries = [item.summary.strip() for item in capability_results if item.summary]
        warnings: list[CapabilityWarning] = []
        if isinstance(result, WorkflowResult):
            warnings.extend(result.warnings)
        for item in capability_results:
            warnings.extend(item.warnings)
        text_parts = summaries or [f"Execution completed with status {result.status.value}."]
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
        return RenderedResponse(
            status=result.status,
            text="\n".join(text_parts),
            components=tuple(
                component for item in capability_results for component in item.components
            ),
            sources=tuple(sources),
            warnings=tuple(warnings),
            run_id=run_id,
            generated_at=datetime.now(UTC),
            trace=tuple(item.capability for item in capability_results),
        )
