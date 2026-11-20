"""Explainer agent (Microsoft Agent Framework): why was a sales line matched, or not?

Run: python -m reconlens.agent "DIPIR 500 CPR"
Without Azure chat env it prints the raw search_catalog output instead (offline).
"""

import asyncio
import json
import os
import sys
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient

from reconlens import config, db, matching
from reconlens.embeddings import get_embedder

INSTRUCTIONS = """You explain why a pharmacy sales line was or was not matched to a catalog product.
Always call search_catalog with the line text first. Cite the candidate SKUs, names and cosine scores,
and compare the best score with the threshold returned by the tool: at or above it the line is matched,
below it the line stays unmatched. Point out differing dosage or pack size between close candidates.
Never compute, estimate or change money, prices or totals; you do not have prices and must not invent them."""


@tool(approval_mode="never_require")
def search_catalog(
    text: Annotated[str, "Raw sales line text, e.g. 'DIPIR 500 CPR'"],
    top_k: Annotated[int, "Number of candidates to return"] = 5,
) -> str:
    """Search the product catalog for a messy sales line; returns candidates with scores and the match threshold."""
    with db.connect() as conn:
        return json.dumps(matching.match(conn, get_embedder(), text, top_k), ensure_ascii=False, indent=2)


async def explain(text: str) -> str:
    client = OpenAIChatCompletionClient(
        model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION"),
    )
    agent = Agent(client, INSTRUCTIONS, name="ReconLensExplainer", tools=[search_catalog])
    return (await agent.run(f"Explain the match for this sales line: {text}")).text


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit('usage: python -m reconlens.agent "DIPIR 500 CPR"')
    text = " ".join(sys.argv[1:])
    if config.azure_chat_configured():
        print(asyncio.run(explain(text)))
    else:
        print("Azure OpenAI chat is not configured (AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / "
              "AZURE_OPENAI_CHAT_DEPLOYMENT). Showing the raw search_catalog output instead:\n")
        print(search_catalog.func(text))


if __name__ == "__main__":
    main()
