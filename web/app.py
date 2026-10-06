import os
from pathlib import Path

import markdown
import bleach

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
# Academic Cloud / SAIA configuration
# ------------------------------------------------------------

# The API key is provided through the environment rather than stored
# directly in the source code.
SAIA_API_KEY = os.environ.get("SAIA_API_KEY")

if not SAIA_API_KEY:
    raise RuntimeError(
        "SAIA_API_KEY environment variable is not set."
    )

# Academic Cloud provides an OpenAI-compatible API, so it can be used
# through the standard AsyncOpenAI client.
academic_cloud_client = AsyncOpenAI(
    api_key=SAIA_API_KEY,
    base_url="https://chat-ai.academiccloud.de/v1",
)

# Configure the Agents SDK to use Academic Cloud for model requests.
set_default_openai_client(
    academic_cloud_client,
    use_for_tracing=False,
)

set_default_openai_api("chat_completions")
set_tracing_disabled(True)


# ------------------------------------------------------------
# Web application
# ------------------------------------------------------------

app = FastAPI()

# Static files (CSS, images, etc.) and HTML templates used by the
# lightweight web interface.
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ------------------------------------------------------------
# MCP servers
# ------------------------------------------------------------

# Each OMERO repository exposes its own MCP endpoint. The URLs can be
# overridden through environment variables if necessary.
EVOLOMERO_MCP_URL = os.getenv(
    "EVOLOMERO_MCP_URL",
    "https://evolomero.evolbio.mpg.de/mcp",
)

NFDI4BIOIMAGE_MCP_URL = os.getenv(
    "NFDI4BIOIMAGE_MCP_URL",
    "https://omero.nfdi4bioimage.de/kg-mcp/mcp",
)


# ------------------------------------------------------------
# Web routes
# ------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Display the initial question form."""

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "question": "",
            "answer": None,
        },
    )


@app.post("/", response_class=HTMLResponse)
async def ask(
    request: Request,
    question: str = Form(...),
):
    """Send a user question to the OMERO agent and display its answer."""

    # Connect to both repository-specific MCP servers.
    # The connections provide the tools that the agent can use to inspect
    # native OMERO metadata and query the corresponding Knowledge Graphs.
    async with MCPServerStreamableHttp(
        name="Evolomero",
        params={
            "url": EVOLOMERO_MCP_URL,
            "timeout": 30,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    ) as evolomero_mcp, MCPServerStreamableHttp(
        name="NFDI4BIOIMAGE",
        params={
            "url": NFDI4BIOIMAGE_MCP_URL,
            "timeout": 30,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    ) as nfdi4bioimage_mcp:

        # Create an agent with access to the tools from both repositories.
        agent = Agent(
            name="OMERO KG Assistant",
            model="openai-gpt-oss-120b",

            instructions=f"""
You help users discover and inspect images stored in multiple
OMERO repositories.

You have access to MCP tools from two repositories:

1. Evolomero
   https://evolomero.evolbio.mpg.de/

2. NFDI4BIOIMAGE OMERO
   https://omero.nfdi4bioimage.de/


REPOSITORY SELECTION:

OMERO object IDs are local to each repository and are not globally unique.

If the user specifies a repository, use that repository's tools.

If the user gives an image ID without specifying a repository, check both
repositories. If the ID exists in both repositories, report both results
separately and clearly identify their repositories.

Never silently treat data returned by one repository as data from the
other repository.


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

Both repositories provide their own query_knowledge_graph tool for
dynamic SPARQL queries.

If a question requires Knowledge Graph relationships, filtering,
grouping, aggregation, or metadata that the specialized tools do not
provide, use query_knowledge_graph from the appropriate repository.

If the user explicitly specifies a repository, use that repository's
query_knowledge_graph tool.

If the user does not specify a repository and the question can apply to
both repositories, query both repositories when appropriate and report
the results separately.

Do not combine repository-local OMERO identifiers as if they belonged
to the same repository.

Do not use query_knowledge_graph when an existing specialized tool
already fully answers the question.

Do not assume that dynamic SPARQL is available for another repository
unless that repository exposes its own query_knowledge_graph tool.


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
                evolomero_mcp,
                nfdi4bioimage_mcp,
            ],

            # Both repositories expose tools with the same names.
            # Prefixing tool names with the MCP server name prevents
            # collisions and lets the agent distinguish the repositories.
            mcp_config={
                "include_server_in_tool_names": True
            },
        )

        # Let the agent decide which repository and MCP tools are required
        # to answer the user's question.
        result = await Runner.run(
            agent,
            question,
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "question": question,
            "answer": result.final_output,
        },
    )