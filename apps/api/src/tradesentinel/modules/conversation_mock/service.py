from tradesentinel.modules.conversation_mock.schemas import MockReply, MockUnderstanding


class MockConversationService:
    async def understand(self, message: str) -> MockUnderstanding:
        normalized = " ".join(message.split())
        return MockUnderstanding(
            normalized_message=normalized,
            word_count=len(normalized.split()),
        )

    async def reply(self, message: str) -> MockReply:
        normalized = " ".join(message.split())
        return MockReply(
            reply=(
                f"You said: {normalized}\n\n"
                "This deterministic mock response confirms that chat planning, "
                "capability execution, persistence, and streaming are working."
            )
        )
