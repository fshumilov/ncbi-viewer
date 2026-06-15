import re
from dataclasses import dataclass
from enum import StrEnum

from geo_expression_service.domain.validation import (
    MAX_GENE_COUNT,
    MIN_GENE_COUNT,
    normalize_gene_symbols,
)

GSE_PATTERN = re.compile(r"GSE\d+", re.IGNORECASE)
GENE_TOKEN_PATTERN = re.compile(r"\b[A-Z][A-Z0-9-]{0,14}\b")

CHAT_STOPWORDS = frozenset(
    {
        "A",
        "AN",
        "AND",
        "ARE",
        "AT",
        "BOXPLOT",
        "DATA",
        "EXPRESSION",
        "FOR",
        "FROM",
        "GENE",
        "GENES",
        "GET",
        "IN",
        "IS",
        "LOOK",
        "ME",
        "MY",
        "OF",
        "PLOT",
        "PLEASE",
        "SHOW",
        "THE",
        "WHAT",
        "WITH",
    }
)


class ChatParseStatus(StrEnum):
    OK = "ok"
    MISSING_GSE = "missing_gse"
    MISSING_GENES = "missing_genes"
    INVALID_GENE_COUNT = "invalid_gene_count"


@dataclass(frozen=True)
class ParsedChatIntent:
    status: ChatParseStatus
    gse_id: str | None = None
    gene_symbols: list[str] | None = None


def parse_chat_intent(message: str) -> ParsedChatIntent:
    gse_match = GSE_PATTERN.search(message)
    if gse_match is None:
        return ParsedChatIntent(status=ChatParseStatus.MISSING_GSE)

    gse_id = gse_match.group(0).upper()
    text_without_gse = f"{message[: gse_match.start()]} {message[gse_match.end() :]}"

    gene_symbols: list[str] = []
    seen_symbols: set[str] = set()
    for token_match in GENE_TOKEN_PATTERN.finditer(text_without_gse.upper()):
        token = token_match.group(0)
        if token in CHAT_STOPWORDS or token in seen_symbols:
            continue
        seen_symbols.add(token)
        gene_symbols.append(token)

    normalized_genes = normalize_gene_symbols(gene_symbols)
    if not normalized_genes:
        return ParsedChatIntent(status=ChatParseStatus.MISSING_GENES, gse_id=gse_id)

    unique_count = len(normalized_genes)
    if unique_count < MIN_GENE_COUNT or unique_count > MAX_GENE_COUNT:
        return ParsedChatIntent(
            status=ChatParseStatus.INVALID_GENE_COUNT,
            gse_id=gse_id,
            gene_symbols=normalized_genes,
        )

    return ParsedChatIntent(
        status=ChatParseStatus.OK,
        gse_id=gse_id,
        gene_symbols=normalized_genes,
    )


def build_clarification_message(intent: ParsedChatIntent) -> str:
    if intent.status == ChatParseStatus.MISSING_GSE:
        return (
            "Please include a GEO series accession (for example GSE2034) and "
            "2-5 gene symbols (for example TP53 and BRCA1)."
        )
    if intent.status == ChatParseStatus.MISSING_GENES:
        return (
            f"I found series {intent.gse_id}, but I need 2-5 gene symbols "
            "(for example TP53 and BRCA1)."
        )
    if intent.status == ChatParseStatus.INVALID_GENE_COUNT:
        gene_count = len(intent.gene_symbols or [])
        return (
            f"I found series {intent.gse_id} with {gene_count} gene symbol(s), "
            f"but each request must include between {MIN_GENE_COUNT} and "
            f"{MAX_GENE_COUNT} unique genes."
        )
    return (
        "Please include a GEO series accession (for example GSE2034) and "
        "2-5 gene symbols (for example TP53 and BRCA1)."
    )
