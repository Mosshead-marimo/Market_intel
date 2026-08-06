from tradesentinel.modules.system.capability import SystemPingCapability
from tradesentinel.modules.system.service import SystemService
from tradesentinel.platform.contracts import CommandDescriptor, WorkflowDefinition, WorkflowStep
from tradesentinel.platform.modules import ModuleRegistration


def create_plugin() -> ModuleRegistration:
    capability = SystemPingCapability(SystemService())
    return ModuleRegistration(
        capabilities=(capability,),
        commands=(
            CommandDescriptor(
                name="/ping",
                description="Check the TradeSentinel capability runtime.",
                capability="system.ping",
                examples=("/ping",),
            ),
        ),
        workflows=(
            WorkflowDefinition(
                name="system.health",
                version="1.0.0",
                description="Runs the domain-neutral platform health capability.",
                steps=(WorkflowStep(id="ping", capability="system.ping"),),
            ),
        ),
    )
