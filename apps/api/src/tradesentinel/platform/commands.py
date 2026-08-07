from __future__ import annotations

import shlex
from dataclasses import dataclass

from pydantic import JsonValue

from tradesentinel.platform.contracts import CommandDescriptor, ExecutionTarget
from tradesentinel.platform.errors import CommandSyntaxError, RegistryError
from tradesentinel.platform.registries import CommandRegistry


@dataclass(frozen=True)
class ParsedCommand:
    target: ExecutionTarget
    payload: dict[str, JsonValue]


class CommandParser:
    def __init__(self, registry: CommandRegistry) -> None:
        self._registry = registry

    def parse(self, value: str) -> ParsedCommand:
        try:
            tokens = shlex.split(value)
        except ValueError as exc:
            raise CommandSyntaxError("The command contains invalid quoting.") from exc
        if not tokens or not tokens[0].startswith("/"):
            raise CommandSyntaxError("Commands must start with '/'.")
        try:
            descriptor = self._registry.get(tokens[0])
        except RegistryError as exc:
            raise CommandSyntaxError(
                f"Unknown command '{tokens[0]}'.", {"command": tokens[0]}
            ) from exc
        payload = self._parse_tokens(descriptor, tokens[1:])
        return ParsedCommand(target=descriptor.target, payload=payload)

    def _parse_tokens(
        self, descriptor: CommandDescriptor, tokens: list[str]
    ) -> dict[str, JsonValue]:
        positionals: list[str] = []
        options: dict[str, JsonValue] = {}
        declared = {option.name: option for option in descriptor.options}
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if not token.startswith("--"):
                positionals.append(token)
                index += 1
                continue
            option_name = token[2:]
            option = declared.get(option_name)
            if option is None:
                raise CommandSyntaxError(
                    f"Unknown option '--{option_name}'.", {"command": descriptor.name}
                )
            if option.destination in options:
                raise CommandSyntaxError(f"Option '--{option_name}' was supplied more than once.")
            if option.flag:
                options[option.destination] = True
                index += 1
            else:
                if index + 1 >= len(tokens) or tokens[index + 1].startswith("--"):
                    raise CommandSyntaxError(f"Option '--{option_name}' requires a value.")
                options[option.destination] = tokens[index + 1]
                index += 2

        if len(positionals) > len(descriptor.arguments):
            raise CommandSyntaxError("Too many positional arguments were supplied.")
        payload = dict(options)
        for argument, value in zip(descriptor.arguments, positionals, strict=False):
            payload[argument.name] = value
        missing_arguments = [
            argument.name
            for argument in descriptor.arguments[len(positionals) :]
            if argument.required
        ]
        missing_options = [
            option.name
            for option in descriptor.options
            if option.required and option.destination not in payload
        ]
        if missing_arguments or missing_options:
            raise CommandSyntaxError(
                "Required command values are missing.",
                {"arguments": missing_arguments, "options": missing_options},
            )
        return payload
