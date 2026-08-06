from tradesentinel import __version__
from tradesentinel.modules.system.schemas import PingInput, PingOutput


class SystemService:
    async def ping(self, request: PingInput) -> PingOutput:
        return PingOutput(
            reply="pong" if request.message == "ping" else request.message,
            service="api",
            version=__version__,
        )
