from __future__ import annotations

import asyncio
from uuid import uuid4

from tradesentinel.modules.prediction_engine.evaluation import PredictionEvaluationService
from tradesentinel.modules.prediction_engine.service import PredictionService
from tradesentinel.platform.background import BackgroundWorker
from tradesentinel.platform.contracts import EventEnvelope
from tradesentinel.platform.events import EventBus


class PredictionBackgroundWorker(BackgroundWorker):
    def __init__(
        self,
        service: PredictionService,
        evaluation_service: PredictionEvaluationService,
        events: EventBus,
    ) -> None:
        self.service = service
        self.evaluation_service = evaluation_service
        self.events = events

    async def run_once(self) -> int:
        outbox = await self.service.repository.pending_outbox()
        for event in outbox:
            await self.events.publish(
                EventEnvelope(
                    event_id=event.event_id,
                    name=event.event_name,
                    correlation_id=event.job_id,
                    producer="prediction_engine.outbox",
                    payload=event.payload,
                )
            )
            await self.service.repository.mark_outbox_published(event.event_id)
        jobs = await self.service.repository.queued_jobs()
        for job in jobs:
            try:
                await self.service.execute_job(job.job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                continue
        evaluations = await self.evaluation_service.evaluate_due()
        if evaluations:
            await self.events.publish(
                EventEnvelope(
                    name="prediction.evaluations.collected",
                    correlation_id=uuid4(),
                    producer="prediction_engine.worker",
                    payload={"processed": evaluations},
                )
            )
        return len(outbox) + len(jobs) + evaluations

    async def run_forever(self) -> None:
        while True:
            processed = await self.run_once()
            await asyncio.sleep(0.1 if processed else 1.0)
