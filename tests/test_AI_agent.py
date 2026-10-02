import asyncio
import os

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
)
set_default_openai_client(
    academic_cloud_client,
    use_for_tracing=False,
)

set_default_openai_api("chat_completions")
set_tracing_disabled(True)


# ------------------------------------------------------------
# MCP server configuration
# ------------------------------------------------------------

# Local MCP endpoint:
# MCP_URL = "http://127.0.0.1:8001/mcp"

# Public Evolomero MCP endpoint:
MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"

# ------------------------------------------------------------
# Agent configuration
# ------------------------------------------------------------
MODEL = "openai-gpt-oss-120b"

# ------------------------------------------------------------
# Test question
# ------------------------------------------------------------

IMAGE_ID = 427

QUESTION = f"""
Tell me what you know about OMERO image {IMAGE_ID}.

Include its name, dataset, project if available, geographic
location, and a link to open the image in OMERO.
"""


async def main():

    # Connect to the MCP server that provides the OMERO tools.
    async with MCPServerStreamableHttp(
        name="Evolomero",
        params={
            "url": MCP_URL,
            "timeout": 30,
        },
        cache_tools_list=True,
        client_session_timeout_seconds=30,
    ) as mcp_server:

        # Create the same type of agent used by the web application.
        agent = Agent(
            name="OMERO KG Assistant",
            model=MODEL,

            instructions="""
You help users discover and inspect images stored in an OMERO repository.

Use Knowledge Graph tools for datasets, projects, repository context,
geographic metadata, and geographic searches.

Use native OMERO metadata tools for technical imaging metadata such as
dimensions, pixel type, physical pixel sizes, channels, fluorophores,
wavelengths, and acquisition information.

Use multiple tools when necessary to answer a question.

DATA PROVENANCE:
Report only metadata returned by the MCP tools. Do not enrich tool results
with information from your own knowledge. Do not infer place names from
coordinates, image or experiment types from technical metadata, or
biological meaning from filenames or channel names. If requested metadata
is not returned by a tool, say that it is not available in the retrieved
metadata.

When an OMERO URL is returned by a tool, include it in the answer.

Be concise and factual.
""",
            mcp_servers=[
                mcp_server,
            ],
        )

        # Run the test question through the agent.
        print("Question:")
        print(QUESTION.strip())

        result = await Runner.run(
            agent,
            QUESTION,
        )

        print("\nAnswer:")
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
