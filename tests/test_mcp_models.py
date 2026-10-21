#!/usr/bin/env python3
"""Benchmark predefined OMERO MCP tools across Academic Cloud models.

Two questions: native OMERO metadata and combined native + KG
metadata. Dynamic SPARQL is excluded. Edit MODELS to choose models.

Run from the repository root:
    python tests/test_mcp_models.py

Print answers, tool calls, elapsed time, and token use. Append one row per
attempt to tests/benchmarking/test_mcp_models_results.csv.
"""

import asyncio
import csv
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import AsyncOpenAI
from agents import (
    Agent,
    Runner,
    set_default_openai_api,
    set_default_openai_client,
    set_tracing_disabled,
)
from agents.mcp import MCPServerStreamableHttp, create_static_tool_filter


# ------------------------------------------------------------
# Academic Cloud
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
# One repository and four models for the controlled benchmark
# ------------------------------------------------------------
MCP_NAME = "Evolomero"
MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"

# For NFDI4BIOIMAGE, also adapt the image IDs and questions.
# MCP_NAME = "NFDI4BIOIMAGE"
# MCP_URL = "https://omero.nfdi4bioimage.de/kg-mcp/mcp"

MODELS = [
    "qwen3.5-397b-a17b",
    "qwen3-coder-next", # Temporarily unavailable
    "qwen3.6-35b-a3b",
    #"qwen3.8-27b", next to test
    "deepseek-v4-flash-0731",
]


# ------------------------------------------------------------
# Keep these questions unchanged for comparison with earlier runs
# ------------------------------------------------------------
TEST_CASES = [
    {
        "id": "native",
        "category": "Native OMERO API",
        "question": (
            "On Evolomero, what are the dimensions (SizeX, SizeY, SizeZ, "
            "SizeC, SizeT) and channel names of image 262?"
        ),
    },
    # 
    {
        "id": "combined",
        "category": "Combined native + KG APIs",
        "question": (
            "On Evolomero, describe image 427: give its dataset, project "
            "(if any), geographic coordinates, and OMERO link, AND its "
            "technical dimensions (SizeX, SizeY, SizeZ, SizeC, SizeT), "
            "pixel type, and channel names. State when a field is unavailable."
        ),
    },
]

# These tool calls distinguish the two benchmark tasks. They are checked
# after an agent completes; this is a tool-use check, NOT answer validation.
REQUIRED_TOOLS = {
    "native": {"get_omero_image_metadata"},
    "combined": {"get_omero_image_metadata", "get_image_details"},
}

# ------------------------------------------------------------
# Agent instructions
# ------------------------------------------------------------
AGENT_INSTRUCTIONS = f"""
You help users discover and inspect images stored in the {MCP_NAME} OMERO
repository. All questions in this benchmark refer to this repository.
TOOL SELECTION:
Use native OMERO metadata tools for technical imaging metadata such as
image dimensions, pixel type, physical pixel sizes, channels, fluorophores,
wavelengths, and acquisition information.
Use specialized Knowledge Graph tools for datasets, projects, geographic
locations, OMERO links, and other semantic or geographic operations.
Prefer specialized tools when they fully answer the question. Use multiple
tools if different information is required from different APIs.
Dynamic SPARQL is disabled for this benchmark. Do not call
query_knowledge_graph. If a requested field is unavailable, say so.

DATA PROVENANCE:

Report only information returned by MCP tools. Do not invent metadata or
infer places or biological classifications. Include OMERO links when returned.
Be concise and factual.
"""


def actual_tool_calls(result):
    """Return actual SDK tool names, preserving order and repeated calls."""
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


def missing_required_tools(test_id, calls):
    """Handle both plain names and MCP server-prefixed tool names."""
    used = {name.rsplit("__", 1)[-1] for name in calls}
    return sorted(REQUIRED_TOOLS[test_id] - used)


async def run_test(mcp_server, model, test_case):
    agent = Agent(
        name="OMERO KG Benchmark Assistant",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        mcp_servers=[mcp_server],
        mcp_config={"include_server_in_tool_names": True},
    )
    question = test_case["question"]
    print("\n" + "=" * 72, flush=True)
    print(f"{test_case['id']} | {model}", flush=True)
    print(f"Question: {question}", flush=True)

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
        "answer": None,
        "error": None,
    }

    start_time = time.perf_counter()
    try:
        result = await Runner.run(agent, question, max_turns=10)
        record["answer"] = str(result.final_output)
        record["tool_calls"] = actual_tool_calls(result)

        usage = result.context_wrapper.usage
        record["llm_requests"] = usage.requests
        record["input_tokens"] = usage.input_tokens
        record["output_tokens"] = usage.output_tokens
        record["total_tokens"] = usage.total_tokens

        missing = missing_required_tools(test_case["id"], record["tool_calls"])
        if missing:
            record["error"] = "Missing required MCP tools: " + ", ".join(missing)
        else:
            record["status"] = "OK"

        print("\nAnswer:\n" + record["answer"])
        print("Actual MCP tools: " + (", ".join(record["tool_calls"]) or "(none)"))
        print(
            f"LLM usage: {usage.requests} requests; "
            f"{usage.input_tokens} input, {usage.output_tokens} output, "
            f"{usage.total_tokens} total tokens"
        )
        if missing:
            print("FAILED tool-use check: " + record["error"])

    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED: {record['error']}", flush=True)
    finally:
        record["elapsed_seconds"] = round(time.perf_counter() - start_time, 3)
        print(f"Elapsed: {record['elapsed_seconds']:.1f} s", flush=True)

    # Partial SDK activity may be unavailable if Runner.run raises an error.
    return record


# ------------------------------------------------------------
# CSV output (same column names as the previous script)
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BASE_DIR / "benchmarking"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = RESULTS_DIR / "test_mcp_models_results.csv"
CSV_FIELDS = [
    "run_utc", "repository", "test_id", "model", "status",
    "elapsed_seconds", "llm_requests", "input_tokens", "output_tokens",
    "total_tokens", "tool_count", "tools", "error",
]


def save_result(record, run_utc):
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
        "tool_count": len(record["tool_calls"]) if record["answer"] is not None else None,
        "tools": "; ".join(record["tool_calls"]),
        "error": record["error"],
    }
    with RESULTS_FILE.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        if handle.tell() == 0:
            writer.writeheader()
        writer.writerow(row)


async def main():
    print(f"Repository: {MCP_NAME} ({MCP_URL})")
    print(f"Models: {', '.join(MODELS)}")
    print(f"Questions: {', '.join(test['id'] for test in TEST_CASES)}")
    print("Dynamic SPARQL: excluded by MCP tool filter")

    results = []
    run_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    async with MCPServerStreamableHttp(
        name=MCP_NAME,
        params={"url": MCP_URL, "timeout": 30},
        cache_tools_list=True,
        client_session_timeout_seconds=30,
        tool_filter=create_static_tool_filter(blocked_tool_names=["query_knowledge_graph"]),
    ) as mcp_server:
        for test_case in TEST_CASES:
            for model in MODELS:
                record = await run_test(mcp_server, model, test_case)
                results.append(record)
                save_result(record, run_utc)

    print("\n" + "=" * 84)
    print("PREDEFINED MCP BENCHMARK SUMMARY")
    print("=" * 84)
    print(f"{'TEST':<13} {'MODEL':<27} {'STATUS':<8} {'SEC':>8} {'TOKENS':>9} {'TOOLS':>5}")
    for record in results:
        count = str(len(record["tool_calls"])) if record["answer"] is not None else "-"
        tokens = str(record["total_tokens"]) if record["total_tokens"] is not None else "-"
        print(
            f"{record['test_id']:<13} {record['model']:<27} "
            f"{record['status']:<8} {record['elapsed_seconds']:>8.1f} "
            f"{tokens:>9} {count:>5}"
        )
        if record["error"]:
            print(f"    Error: {record['error']}")
    print(f"\nCSV results (appended): {RESULTS_FILE}")
    print("OK = completed with required tool calls; not validated answer correctness.")
    print("FAILED = exception or missing required tools; partial tool activity may be unknown.")


if __name__ == "__main__":
    asyncio.run(main())
