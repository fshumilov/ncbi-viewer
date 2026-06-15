import logging
from dataclasses import dataclass

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ToolReturnPart

from geo_expression_service.config import Settings
from geo_expression_service.domain.chat_parser import (
    ChatParseStatus,
    build_clarification_message,
    parse_chat_intent,
)
from geo_expression_service.domain.models import (
    ChatResponse,
    ExpressionRequest,
    ExpressionResult,
)
from geo_expression_service.domain.validation import normalize_gse_id, validate_gene_count
from geo_expression_service.logging import get_request_id
from geo_expression_service.services.expression_service import ExpressionService

logger = logging.getLogger(__name__)

EXPRESSION_TOOL_NAME = "get_gene_expression"

SYSTEM_PROMPT = """\
You are a GEO expression assistant. When the user asks for gene expression in a GEO series,
call the get_gene_expression tool with the GSE accession and 2-5 gene symbols.
Ground your reply in the tool output only — do not invent expression values.
If GSE or genes are missing, ask for clarification without calling the tool.
"""


@dataclass
class ChatAgentDeps:
    expression_service: ExpressionService


def _build_expression_agent(settings: Settings) -> Agent[ChatAgentDeps, str]:
    model_name = f"openai:{settings.openai_model}"
    agent: Agent[ChatAgentDeps, str] = Agent(
        model_name,
        deps_type=ChatAgentDeps,
        system_prompt=SYSTEM_PROMPT,
    )

    @agent.tool
    async def get_gene_expression(
        ctx: RunContext[ChatAgentDeps],
        gse_id: str,
        gene_symbols: list[str],
    ) -> ExpressionResult:
        """Fetch a combined boxplot and mapping stats for a GEO series and 2-5 genes."""
        normalized_gse = normalize_gse_id(gse_id)
        validated_genes = validate_gene_count(gene_symbols)
        request = ExpressionRequest(gse_id=normalized_gse, gene_symbols=validated_genes)
        request_id = get_request_id()
        logger.info(
            "ExpressionTool invoked: gse_id=%s genes=%s request_id=%s",
            normalized_gse,
            validated_genes,
            request_id,
        )
        return await ctx.deps.expression_service.get_expression(request)

    return agent


def _build_stub_reply(result: ExpressionResult) -> str:
    gene_details = ", ".join(
        f"{stat.gene_symbol} ({stat.probes_mapped} probes mapped"
        + (f", {stat.skip_reason}" if stat.skip_reason else "")
        + ")"
        for stat in result.mapping.per_gene
    )
    return (
        f"Here is expression for {', '.join(result.genes)} in {result.gse_id} "
        f"(platform {result.mapping.gpl_id}). {gene_details}. "
        f"The combined boxplot is attached (cached={result.cached}, "
        f"duration_ms={result.duration_ms})."
    )


def _extract_expression_from_tool_returns(messages: list[object]) -> ExpressionResult | None:
    for message in messages:
        parts = getattr(message, "parts", ())
        for part in parts:
            if not isinstance(part, ToolReturnPart):
                continue
            if part.tool_name != EXPRESSION_TOOL_NAME:
                continue
            if isinstance(part.content, ExpressionResult):
                return part.content
    return None


def _has_expression_tool_call(messages: list[object]) -> bool:
    for message in messages:
        parts = getattr(message, "parts", ())
        for part in parts:
            if (
                isinstance(part, ToolReturnPart)
                and part.tool_name == EXPRESSION_TOOL_NAME
            ):
                return True
    return False


class ChatAgent:
    def __init__(
        self,
        expression_service: ExpressionService,
        settings: Settings,
    ) -> None:
        self._expression_service = expression_service
        self._settings = settings
        self._llm_agent = (
            None if settings.should_use_stub_llm() else _build_expression_agent(settings)
        )

    async def handle(self, message: str) -> ChatResponse:
        if self._settings.should_use_stub_llm():
            return await self._handle_stub(message)
        return await self._handle_llm(message)

    async def _handle_stub(self, message: str) -> ChatResponse:
        parsed = parse_chat_intent(message)
        if parsed.status != ChatParseStatus.OK:
            return ChatResponse(
                message=build_clarification_message(parsed),
                expression=None,
                tool_invoked=False,
            )

        assert parsed.gse_id is not None
        assert parsed.gene_symbols is not None
        request_id = get_request_id()
        logger.info(
            "ExpressionTool invoked: gse_id=%s genes=%s request_id=%s",
            parsed.gse_id,
            parsed.gene_symbols,
            request_id,
        )
        expression_result = await self._expression_service.get_expression(
            ExpressionRequest(gse_id=parsed.gse_id, gene_symbols=parsed.gene_symbols)
        )
        return ChatResponse(
            message=_build_stub_reply(expression_result),
            expression=expression_result,
            tool_invoked=True,
        )

    async def _handle_llm(self, message: str) -> ChatResponse:
        assert self._llm_agent is not None
        deps = ChatAgentDeps(expression_service=self._expression_service)
        result = await self._llm_agent.run(message, deps=deps)
        all_messages = result.all_messages()
        expression_result = _extract_expression_from_tool_returns(all_messages)
        tool_invoked = _has_expression_tool_call(all_messages)

        if not tool_invoked:
            parsed = parse_chat_intent(message)
            if parsed.status != ChatParseStatus.OK:
                return ChatResponse(
                    message=build_clarification_message(parsed),
                    expression=None,
                    tool_invoked=False,
                )

        return ChatResponse(
            message=str(result.output),
            expression=expression_result,
            tool_invoked=tool_invoked,
        )
