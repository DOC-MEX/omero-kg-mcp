import logging
import os
import time
from pathlib import Path

from agents import (
    Agent,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from openai import AsyncOpenAI

logger = logging.getLogger("ai-omero")

# ------------------------------------------------------------
# Academic Cloud / SAIA configuration
# ------------------------------------------------------------

SAIA_API_KEY = os.environ.get("SAIA_API_KEY")
if not SAIA_API_KEY:
    raise RuntimeError("SAIA_API_KEY environment variable is not set.")

# Change models directly here. The same instructions and tools are used
# for every selection so response time, tokens and answers are comparable.
MODELS = (
    "qwen3-coder-next",
    "qwen3.6-35b-a3b",
    "qwen3.5-397b-a17b",  # Original web app baseline
)
DEFAULT_MODEL = MODELS[0]

# NEW: Explicit agent mode
MODES = ("standard", "sparql")
DEFAULT_MODE = MODES[0]

academic_cloud_client = AsyncOpenAI(
    api_key=SAIA_API_KEY,
    base_url="https://chat-ai.academiccloud.de/v1",
    timeout=300.0,
    max_retries=0,
)
set_default_openai_client(academic_cloud_client, use_for_tracing=False)
set_default_openai_api("chat_completions")
set_tracing_disabled(True)

# ------------------------------------------------------------
# Web application and repository MCP endpoints
# ------------------------------------------------------------

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

EVOLOMERO_MCP_URL = os.getenv(
    "EVOLOMERO_MCP_URL", "https://evolomero.evolbio.mpg.de/mcp"
)
NFDI4BIOIMAGE_MCP_URL = os.getenv(
    "NFDI4BIOIMAGE_MCP_URL", "https://omero.nfdi4bioimage.de/kg-mcp/mcp"
)

# NEW: Standard mode hides SPARQL. In SPARQL mode, no filter is applied.
# The KG schema is read only when SPARQL mode is selected.
STANDARD_TOOL_FILTER = create_static_tool_filter(
    blocked_tool_names=["query_knowledge_graph"]
)

STANDARD_INSTRUCTIONS = """
You help users discover and inspect images in two OMERO repositories:
- Evolomero: https://evolomero.evolbio.mpg.de/
- NFDI4BIOIMAGE: https://omero.nfdi4bioimage.de/

REPOSITORY SELECTION:
OMERO object IDs are local to each repository, not globally unique.
When a repository is specified, use only its tools.
If an image ID is given without a repository, look it up in BOTH repositories.
Report each repository separately, including missing images when appropriate.
For location searches without a repository, consult both repositories.
If the user asks for the closest N images overall, compare distances returned
by the tools and report at most N results across both repositories, naming the
repository of each image. Do not invent distances or conflate image IDs.

TOOL SELECTION:
Use native OMERO tools for dimensions, pixel types, channels and other
technical metadata. Use specialized Knowledge Graph tools for datasets,
projects, geolocation, geographic searches and OMERO resource links.
Prefer the specialized tool when it fully answers the question; call both
kinds only when the requested data require them.
Dynamic SPARQL is not available in this mode. Do not invent information
when the predefined tools cannot answer a question; state the limitation.

ACCURACY AND FORMAT:
Report only facts returned by MCP tools. Do not infer places from coordinates,
biological classifications from filenames or meanings from channel names.
Report unavailable requested fields as unavailable. Include returned OMERO URLs.
Keep the answer concise, factual and organized by repository when appropriate.
Answer the question and STOP. Do not add unsolicited follow-up questions,
recommendations, invitations, or offers for further information.
""".strip()

# Detailed SPARQL instructions.
# The schema is loaded only for requests explicitly using SPARQL mode.
KG_SCHEMA_FILE = Path(__file__).resolve().parent / "prompts" / "omero_kg_schema.txt"
SPARQL_INSTRUCTIONS_TEMPLATE = """

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
                - When the user asks specifically for resources that have a property,
                  require that property in the graph pattern. Do not make that property
                  OPTIONAL.
                - Do not infer biological meaning, locations, or classifications that
                  are not explicitly represented in the graph.
                - Every generated SPARQL query must explicitly include all PREFIX
                  declarations required by that query.
                - Do not assume that QLever has predefined namespace prefixes.


                SPARQL ERROR RECOVERY:
                - Prefer repairing the failed query rather than generating unrelated
                  alternative queries.
                - Check missing PREFIX declarations, invalid properties, classes, syntax,
                  and graph patterns against the provided Knowledge Graph schema.
                - Do not repeatedly submit the same failing query without modification.

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
                """


def instructions_for_mode(mode):
    if mode == "standard":
        return STANDARD_INSTRUCTIONS
    schema = KG_SCHEMA_FILE.read_text(encoding="utf-8")
    return (
        SPARQL_INSTRUCTIONS_TEMPLATE.replace("{KG_SCHEMA}", schema)
        + "\n\nAnswer the question and STOP. Do not add unsolicited "
          "follow-up questions or offers of further information."
    )


def actual_tool_calls(result):
    """Return ordered MCP tool names, retaining repeated calls."""
    calls = []
    for item in result.new_items:
        if getattr(item, "type", None) != "tool_call_item":
            continue
        name = getattr(item, "tool_name", None)
        if not name:
            raw = getattr(item, "raw_item", None)
            name = raw.get("name") if isinstance(raw, dict) else getattr(raw, "name", None)
        calls.append(str(name or "<unknown>"))
    return calls


def page_context(question="", model=DEFAULT_MODEL, mode=DEFAULT_MODE,
                 answer=None, error=None,
                 elapsed_seconds=None, total_tokens=None, tool_calls=None):
    return {
        "question": question,
        "model": model,
        "mode": mode,
        "answer": answer,
        "error": error,
        "elapsed_seconds": elapsed_seconds,
        "total_tokens": total_tokens,
        "tool_calls": tool_calls,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request, name="index.html", context=page_context()
    )


@app.post("/", response_class=HTMLResponse)
async def ask(request: Request, question: str = Form(...),
              model: str = Form(DEFAULT_MODEL),
              mode: str = Form(DEFAULT_MODE)):
    # Limit SAIA model selection to the models offered in the interface.
    if model not in MODELS:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(question=question, error="Unknown model selected."),
            status_code=400,
        )

    # NEW: Validate selected mode, independently of model selection.
    if mode not in MODES:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(question=question, model=model,
                                 error="Unknown agent mode selected."),
            status_code=400,
        )

    try:
        instructions = instructions_for_mode(mode)
        # None allows all MCP tools; standard mode hides dynamic SPARQL.
        tool_filter = STANDARD_TOOL_FILTER if mode == "standard" else None
        async with MCPServerStreamableHttp(
            name="Evolomero",
            params={"url": EVOLOMERO_MCP_URL, "timeout": 30},
            cache_tools_list=True,
            client_session_timeout_seconds=30,
            tool_filter=tool_filter,
        ) as evolomero_mcp, MCPServerStreamableHttp(
            name="NFDI4BIOIMAGE",
            params={"url": NFDI4BIOIMAGE_MCP_URL, "timeout": 30},
            cache_tools_list=True,
            client_session_timeout_seconds=30,
            tool_filter=tool_filter,
        ) as nfdi4bioimage_mcp:
            agent = Agent(
                name="OMERO KG Assistant",
                model=model,
                instructions=instructions,
                mcp_servers=[evolomero_mcp, nfdi4bioimage_mcp],
                mcp_config={"include_server_in_tool_names": True},
            )

            print(
                f"Starting agent run. Mode: {mode}. Model: {model}. Question: {question!r}",
                flush=True,
            )
            start = time.perf_counter()
            result = await Runner.run(agent, question, max_turns=10)
            elapsed_seconds = time.perf_counter() - start
            print(
                f"Agent run completed. Mode: {mode}. Model: {model}. "
                f"Elapsed time: {elapsed_seconds:.1f} seconds",
                flush=True,
            )

        usage = result.context_wrapper.usage
        calls = actual_tool_calls(result)
        logger.info(
            "Agent completed: mode=%s model=%s elapsed=%.1fs requests=%s "
            "input=%s output=%s total=%s calls=%s",
            mode, model, elapsed_seconds, usage.requests, usage.input_tokens,
            usage.output_tokens, usage.total_tokens, calls,
        )
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(
                question=question,
                model=model,
                mode=mode,
                answer=result.final_output,
                elapsed_seconds=round(elapsed_seconds, 1),
                total_tokens=usage.total_tokens,
                tool_calls=calls,
            ),
        )

    except Exception:
        logger.exception("AI-OMERO request failed: mode=%s model=%s question=%r", mode, model, question)
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context=page_context(
                question=question,
                model=model,
                mode=mode,
                error="AI-OMERO could not complete the request. Please try again.",
            ),
            status_code=503,
        )