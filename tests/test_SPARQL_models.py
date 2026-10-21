#!/usr/bin/env python3
"""Benchmark dynamic SPARQL queries across Academic Cloud LLMs.

Tests two questions that require generating and executing SPARQL via the
query_knowledge_graph MCP tool. All other MCP tools are hidden by a filter.

Usage:
    python tests/test_sparql_models.py
    
# Edit MODELS below to select the models to test.
"""

import asyncio
import csv
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from agents import (
    Agent,
    Runner,
    set_default_openai_client,
    set_default_openai_api,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter


# ------------------------------------------------------------
# Academic Cloud configuration
# ------------------------------------------------------------

SAIA_API_KEY = os.environ.get("SAIA_API_KEY")
if not SAIA_API_KEY:
    raise RuntimeError("SAIA_API_KEY environment variable is not set.")

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
# Knowledge Graph schema (same file used by the existing tests)
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
KG_SCHEMA_FILE = BASE_DIR / "prompts" / "omero_kg_schema.txt"
# Support placing this script either in the repository root or in tests/.
if not KG_SCHEMA_FILE.exists():
    KG_SCHEMA_FILE = BASE_DIR.parent / "prompts" / "omero_kg_schema.txt"
KG_SCHEMA = KG_SCHEMA_FILE.read_text(encoding="utf-8")


# ------------------------------------------------------------
# MCP server configuration: ONE repository for controlled tests
# ------------------------------------------------------------

# The Duisburg dataset on Evolomero contains geolocated images.
MCP_NAME = "Evolomero"
MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"

# To test another repository, adapt the questions accordingly.
# MCP_NAME = "NFDI4BIOIMAGE"
# MCP_URL = "https://omero.nfdi4bioimage.de/kg-mcp/mcp"

# Local alternative:
# MCP_NAME = "Local OMERO"
# MCP_URL = "http://127.0.0.1:8001/mcp"


# ------------------------------------------------------------
# Models to test (comment out models you do not want to run)
# ------------------------------------------------------------

MODELS = [
    "qwen3.5-397b-a17b",
    "qwen3-coder-next",
    "qwen3.6-35b-a3b",
    # "deepseek-v4-flash-0731",  # timeouts frequently
    # "openai-gpt-oss-120b",     # now unavailable
]

# ------------------------------------------------------------
# Two dynamic SPARQL questions
# ------------------------------------------------------------

TEST_CASES = [
    {
        "id": "geolocated_images",
        "category": "Relationships and label filtering",
        "question": (
            "Which geolocated images belong to the Duisburg dataset? "
            "Give me their image IDs and names."
        ),
    },
    {
        "id": "geolocated_counts",
        "category": "Grouping and aggregation",
        "question": (
            "Which datasets contain geolocated images, and how many "
            "geolocated images does each dataset contain?"
        ),
    },
]


# ------------------------------------------------------------
# Agent instructions
# ------------------------------------------------------------

AGENT_INSTRUCTIONS = f"""
You help users discover and inspect images stored in the {MCP_NAME} OMERO
repository. All questions in this benchmark refer to this repository.

DYNAMIC SPARQL BENCHMARK:
You MUST use query_knowledge_graph for each question. Generate a SPARQL
SELECT query using the schema below, execute it, and answer using the
returned results. Do not answer from memory or from inferred data.

All other MCP tools are disabled for this benchmark.

KNOWLEDGE GRAPH SCHEMA:
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
  relevant resource. Require a property when the user asks only for
  resources that have that property.
- Do not infer biological meaning, locations, or classifications that
  are not explicitly represented in the graph.
- Explicitly include every PREFIX declaration needed by the query.
  QLever does not necessarily predefine namespace prefixes.

SPARQL ERROR RECOVERY:
- If query_knowledge_graph returns an error, inspect its message and
  try to repair the same query rather than generating an unrelated query.
- Check PREFIX declarations, class and property names, syntax, and joins
  against the supplied schema.
- Do not repeatedly submit the same failing query without modification.

NAME FILTERING:
- Match user-supplied resource names with rdfs:label.
- Prefer case-insensitive exact matches, e.g.:
  ?dataset rdfs:label ?dataset_name .
  FILTER(LCASE(STR(?dataset_name)) = LCASE("Duisburg"))
- Do not use partial or fuzzy matching unless necessary or requested.

RESULT SIZE:
- For queries returning individual resources, use LIMIT 20 by default
  unless the user explicitly asks for all matching results.
- If asked for a count, use COUNT(DISTINCT ?resource) instead of listing
  all matching resources.
- Aggregated queries with a naturally small number of groups do not
  need the default LIMIT 20.
- If LIMIT 20 is applied, clearly state that only the first 20 matching
  results are shown; do not claim a limited result is complete.

DATA PROVENANCE:
- Report only metadata returned by query_knowledge_graph.
- Do not enrich results with external knowledge or infer place names,
  image types, or biological classifications.
- If requested metadata is missing, state that it is not available.
- You may reorganize or summarize facts without adding interpretations.
- Be concise and factual.
"""

# ------------------------------------------------------------
# Read actual SPARQL tool calls from the SDK result
# ------------------------------------------------------------

def field(obj, key, default=None):
    """Access a value on either an SDK object or a dictionary."""
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def extract_query(raw):
    """Extract query argument from a function call (string or dict)."""
    arguments = field(raw, "arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
    if isinstance(arguments, dict):
        for key in ("query", "sparql_query", "sparql", "sparql_query_string"):
            if key in arguments and isinstance(arguments[key], str):
                return arguments[key]
        return json.dumps(arguments, ensure_ascii=False)
    return ""  # The provider did not expose arguments in an expected shape.


def sparql_activity(result):
    """Extract SPARQL queries and tool names from a completed agent run."""
    tools = []
    queries = []
    for item in result.new_items:
        if field(item, "type") != "tool_call_item":
            continue
        name = field(item, "tool_name") or field(field(item, "raw_item"), "name")
        name = str(name or "<unknown>")
        tools.append(name)
        if name == "query_knowledge_graph" or name.endswith("__query_knowledge_graph"):
            queries.append(extract_query(field(item, "raw_item")))
    return tools, queries


# ------------------------------------------------------------
# Run one model/question combination
# ------------------------------------------------------------

async def run_test(mcp_server, model, test_case):
    agent = Agent(
        name="OMERO SPARQL Benchmark Assistant",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        mcp_servers=[mcp_server],
        mcp_config={"include_server_in_tool_names": True},
    )

    question = test_case["question"]
    print("\n" + "=" * 72, flush=True)
    print(f"{test_case['id']} | {model}", flush=True)
    print(f"Question: {question}", flush=True)

    start_time = time.perf_counter()
    record = {
        "repository": MCP_NAME,
        "model": model,
        "test_id": test_case["id"],
        "category": test_case["category"],
        "question": question,
        "status": "FAILED",
        "elapsed_seconds": None,
        "llm_requests": None,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "tool_calls": [],
        "tool_count": None,
        "sparql_queries": [],
        "answer": None,
        "error": None,
    }

    try:
        result = await Runner.run(agent, question, max_turns=10)
        record["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
        record["answer"] = str(result.final_output)

        usage = result.context_wrapper.usage
        record["llm_requests"] = usage.requests
        record["input_tokens"] = usage.input_tokens
        record["output_tokens"] = usage.output_tokens
        record["total_tokens"] = usage.total_tokens

        tools, queries = sparql_activity(result)
        record["tool_calls"] = tools
        record["tool_count"] = len(tools)
        record["sparql_queries"] = queries

        # OK means a completed agent run with at least one SPARQL tool call.
        # It does NOT verify the query results or the final answer.
        if queries:
            record["status"] = "OK"
        else:
            record["error"] = "Agent completed without calling query_knowledge_graph"

        print("\nAnswer:\n" + record["answer"])
        print(f"\nElapsed: {record['elapsed_seconds']:.1f} s")
        print(
            f"LLM usage: {usage.requests} requests; "
            f"{usage.input_tokens} input, {usage.output_tokens} output, "
            f"{usage.total_tokens} total tokens"
        )
        print("Actual MCP tool calls: " + (", ".join(tools) or "(none)"))
        for i, query in enumerate(queries, start=1):
            print(f"\nGenerated SPARQL #{i}:\n{query or '(arguments unavailable)'}")
        if not queries:
            print("WARNING: No SPARQL tool call was recorded.")
        print(f"Status: {record['status']}")
    except Exception as exc:
        record["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(f"\nFAILED after {record['elapsed_seconds']:.1f} s: {record['error']}", flush=True)

    return record


# ------------------------------------------------------------
# Save measurements to CSV (append runs; preserve existing columns)
# ------------------------------------------------------------

RESULTS_DIR = BASE_DIR / "benchmarking"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = RESULTS_DIR / "test_sparql_models_results.csv"
# Keep the original CSV columns so existing data and plotting scripts still work.
# query_error_count is a legacy field; leave it empty rather than inventing zero.
CSV_FIELDS = [
    "run_utc", "repository", "test_id", "model", "status",
    "elapsed_seconds", "llm_requests", "input_tokens", "output_tokens",
    "total_tokens", "tool_count", "tools", "sparql_calls", "query_error_count",
    "sparql_queries", "answer", "error",
]


def save_result(record, run_utc):
    """Append the result now, without overwriting previous runs."""
    row = {
        "run_utc": run_utc,
        "repository": record["repository"],
        "test_id": record["test_id"],
        "model": record["model"],
        "status": record["status"],
        "elapsed_seconds": record["elapsed_seconds"],
        "llm_requests": record["llm_requests"],
        "input_tokens": record["input_tokens"],
        "output_tokens": record["output_tokens"],
        "total_tokens": record["total_tokens"],
        "tool_count": record["tool_count"],
        "tools": "; ".join(record["tool_calls"]),
        # On exceptions, partial tool activity is unknown, not necessarily zero.
        "sparql_calls": len(record["sparql_queries"]) if record["status"] == "OK" else "",
        "query_error_count": "",
        "sparql_queries": " || ".join(" ".join(q.split()) for q in record["sparql_queries"]),
        "answer": record["answer"],
        "error": record["error"],
    }
    with RESULTS_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        writer.writerow(row)


# ------------------------------------------------------------
# Main benchmark
# ------------------------------------------------------------

async def main():
    print(f"Repository: {MCP_NAME} ({MCP_URL})")
    print(f"Models: {', '.join(MODELS)}")
    print(f"Categories: {', '.join(test['id'] for test in TEST_CASES)}")
    print("Dynamic SPARQL: only query_knowledge_graph is available")

    results = []
    run_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    async with MCPServerStreamableHttp(
        name=MCP_NAME,
        params={"url": MCP_URL, "timeout": 30},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        tool_filter=create_static_tool_filter(
            allowed_tool_names=["query_knowledge_graph"]
        ),
    ) as mcp_server:
        for test_case in TEST_CASES:
            for model in MODELS:
                record = await run_test(mcp_server, model, test_case)
                results.append(record)
                save_result(record, run_utc)

    print("\n" + "=" * 101)
    print("DYNAMIC SPARQL BENCHMARK SUMMARY")
    print("=" * 101)
    print(
        f"{'TEST':<20} {'MODEL':<27} {'STATUS':<8} "
        f"{'SEC':>8} {'TOKENS':>9} {'QUERIES':>7}"
    )
    for record in results:
        status = record["status"]
        print(
            f"{record['test_id']:<20} {record['model']:<27} "
            f"{status:<8} {record['elapsed_seconds']:>8.1f} "
            f"{str(record['total_tokens']) if record['total_tokens'] is not None else '-':>9} "
            f"{len(record['sparql_queries']) if record['status'] == 'OK' else '-':>7}"
        )
        if record["error"]:
            print(f"    Error: {record['error']}")
    print(f"\nCSV results (appended): {RESULTS_FILE}")
    print("Note: OK = completed and called SPARQL; FAILED = exception or missing SPARQL call.")
    print("OK does not verify query or answer correctness.")


if __name__ == "__main__":
    asyncio.run(main())
