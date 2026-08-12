from tradesentinel.platform.errors import PredictionError


class PredictionDataError(PredictionError):
    def __init__(self, message: str, **details: object) -> None:
        super().__init__("PREDICTION_DATA_INVALID", message, details=details)


class PredictionModelNotAvailableError(PredictionError):
    def __init__(self) -> None:
        super().__init__(
            "PREDICTION_MODEL_NOT_AVAILABLE",
            "No active model matches the requested horizon and feature profile.",
            status_code=409,
        )


class PredictionQualityGateError(PredictionError):
    def __init__(self, failures: list[str]) -> None:
        super().__init__(
            "PREDICTION_QUALITY_GATE_FAILED",
            "The model does not satisfy the activation quality gates.",
            status_code=409,
            details={"failures": failures},
        )


class PredictionArtifactError(PredictionError):
    def __init__(self) -> None:
        super().__init__(
            "PREDICTION_ARTIFACT_INVALID",
            "The model artifact failed integrity or compatibility validation.",
            status_code=500,
        )
