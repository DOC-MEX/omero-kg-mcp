import asyncio
import os
from pathlib import Path

from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    set_default_openai_client,
    set_default_openai_api,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStreamableHttp


# ------------------------------------------------------------
# Academic Cloud configuration
# ------------------------------------------------------------

SAIA_API_KEY = os.environ.get("SAIA_API_KEY")

if not SAIA_API_KEY:
    raise RuntimeError(
        "SAIA_API_KEY environment variable is not set."
    )

academic_cloud_client = AsyncOpenAI(
    api_key=SAIA_API_KEY,
    base_url="https://chat-ai.academiccloud.de/v1",
    timeout=60.0,
    max_retries=0,
)

set_default_openai_client(
    academic_cloud_client,
    use_for_tracing=False,
)

set_default_openai_api("chat_completions")
set_tracing_disabled(True)


# ------------------------------------------------------------
# Knowledge Graph schema
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

KG_SCHEMA_FILE = (
    BASE_DIR / "prompts" / "omero_kg_schema.txt"
)

KG_SCHEMA = KG_SCHEMA_FILE.read_text(
    encoding="utf-8"
)

# ------------------------------------------------------------
# ------------------------------------------------------------
# MCP server configuration
# Select ONE repository for this standalone test.
# ------------------------------------------------------------

# Evolomero
MCP_NAME = "Evolomero"
MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"

# NFDI4BIOIMAGE
#MCP_NAME = "NFDI4BIOIMAGE"
#MCP_URL = "https://omero.nfdi4bioimage.de/kg-mcp/mcp"

# Local MCP endpoint
#MCP_NAME = "Local OMERO"
#MCP_URL = "http://127.0.0.1:8001/mcp"

# ------------------------------------------------------------
# Agent configuration
# ------------------------------------------------------------

MODEL = "openai-gpt-oss-120b"

# ------------------------------------------------------------
# Test question
#
# Change only this block to test different questions.
# ------------------------------------------------------------

QUESTION = """
Which geolocated images belong to the Duisburg dataset?
Give me their image IDs and names.
"""


async def main():

    async with MCPServerStreamableHttp(
        name=MCP_NAME,
        params={
            "url": MCP_URL,
            "timeout": 30,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    ) as mcp_server:

        agent = Agent(
            name="OMERO KG Assistant",
            model=MODEL,

            instructions=f"""
You help users discover and inspect images stored in an OMERO repository.

You have access to MCP tools from this repository:

{MCP_NAME}


TOOL SELECTION:

Use native OMERO metadata tools for repository information and technical
imaging metadata such as dimensions, pixel type, physical pixel sizes,
channels, fluorophores, wavelengths, and acquisition information.

Use specialized Knowledge Graph tools for common semantic and geographic
operations when they can fully answer the question.

Prefer specialized MCP tools whenever they can fully answer the user's
question.

Use multiple tools when necessary to answer a question.


DYNAMIC SPARQL:

The repository provides the query_knowledge_graph tool for dynamic
SPARQL queries.

If a question requires Knowledge Graph relationships, filtering,
grouping, aggregation, or metadata that the specialized tools do not
provide, use query_knowledge_graph to execute a SPARQL SELECT query.

Do not use query_knowledge_graph when an existing specialized tool
already fully answers the question.


{KG_SCHEMA}


SPARQL GENERATION RULES:

- Generate only SELECT queries.
- Use only classes and properties described in the Knowledge Graph schema.
- Do not invent predicates or classes.
- Use DISTINCT where appropriate to avoid duplicate OMERO resources.
- For counts of OMERO resources, prefer COUNT(DISTINCT ?resource).
- Include dc:identifier when the user asks for numeric OMERO IDs.
- Include rdfs:label when the user asks for names.
- Use FILTER only with properties represented in the schema.
- Return only the fields needed to answer the question.
- Do not assume that every optional property exists.
- Use OPTIONAL when missing metadata should not exclude an otherwise
  relevant resource.
- Do not infer biological meaning, locations, or classifications that
  are not explicitly represented in the graph.
- Every generated SPARQL query must explicitly include all PREFIX
  declarations required by that query.
- Do not assume that QLever has predefined namespace prefixes.


NAME FILTERING:

- When the user supplies the name of a resource such as a dataset,
  project, image, plate, or screen, match it using its rdfs:label.
- Prefer case-insensitive exact matching when filtering by a
  user-supplied name. For example:

  ?dataset rdfs:label ?dataset_name .
  FILTER(LCASE(STR(?dataset_name)) = LCASE("Duisburg"))

- Do not use partial or fuzzy matching unless the user explicitly asks
  for it or an exact match cannot reasonably answer the request.


RESULT SIZE:

- For queries that return individual resources, use LIMIT 20 by default
  unless the user explicitly asks for all matching results.
- If the user explicitly asks for all results, do not apply the default
  LIMIT 20.
- If the user asks how many resources match a condition, use
  COUNT(DISTINCT ?resource) instead of retrieving every matching
  resource.
- Aggregated queries that naturally return a small number of groups do
  not need the default LIMIT 20.
- When a query uses LIMIT because of this default result-size rule,
  clearly tell the user that only the first 20 matching results are
  being shown.
- Do not claim that a limited result set contains all matching resources.


DATA PROVENANCE:

Report only metadata returned by the MCP tools.

Do not enrich tool results with information from your own knowledge.

Do not infer place names from coordinates, image or experiment types
from technical metadata, or biological meaning from filenames or
channel names.

If requested metadata is not returned by a tool, say that it is not
available in the retrieved metadata.

You may organize and summarize returned metadata without changing its
meaning.

When writing summaries or conclusions, follow the same provenance rules.
Do not introduce interpretations or classifications that were not explicitly
returned by the tools. A summary should only restate or combine retrieved
facts.

When an OMERO URL is returned by a tool, include it in the answer.

Be concise and factual.
""",

            mcp_servers=[
                mcp_server,
            ],
        )

        print(f"MCP repository: {MCP_NAME}")
        print(f"MCP endpoint: {MCP_URL}")

        print("\nQuestion:")
        print(QUESTION.strip())

        try:
            result = await asyncio.wait_for(
                Runner.run(
                    agent,
                    QUESTION,
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            print("\nERROR: Agent run exceeded 90 seconds.")
            return
        except Exception as exc:
            print(
                f"\nERROR during agent run: "
                f"{type(exc).__name__}: {exc}"
            )
            return

        print("\nAnswer:")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())