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

EVOLOMERO_MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"

NFDI4BIOIMAGE_MCP_URL = (
    "https://omero.nfdi4bioimage.de/kg-mcp/mcp"
)

# ------------------------------------------------------------
# Agent configuration
# ------------------------------------------------------------

MODEL = "openai-gpt-oss-120b"

# ------------------------------------------------------------
# Test question
# ------------------------------------------------------------

EVOLOMERO_IMAGE_ID = 427
NFDI4BIOIMAGE_IMAGE_ID = 35751

QUESTION = f"""
Retrieve information about these two OMERO images:

- Evolomero image {EVOLOMERO_IMAGE_ID}
- NFDI4BIOIMAGE image {NFDI4BIOIMAGE_IMAGE_ID}

For each image, report:

- image name
- dataset and project, if available
- geographic location, if available
- image dimensions
- channels, if available
- OMERO URL

Use both Knowledge Graph and native OMERO metadata tools when necessary.
Keep the results for the two repositories clearly separated.
"""


async def main():

    # Connect to the MCP servers for both OMERO repositories.
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

        # Create an agent with access to both repositories.
        agent = Agent(
            name="OMERO KG Assistant",
            model=MODEL,

            instructions="""
You help users discover and inspect images stored in multiple
OMERO repositories.

You have access to MCP tools from two repositories:

1. Evolomero
   https://evolomero.evolbio.mpg.de/

2. NFDI4BIOIMAGE OMERO
   https://omero.nfdi4bioimage.de/

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

OMERO image IDs are local to each repository and are not globally unique.

If the user specifies a repository, use that repository's tools.
If the user gives an image ID without specifying a repository, check both
repositories. If the ID exists in both, report both results separately
and clearly identify their repositories.

When writing summaries or conclusions, follow the same provenance rules.
Do not introduce interpretations or classifications that were not explicitly
returned by the tools.

When an OMERO URL is returned by a tool, include it in the answer.

Be concise and factual.
""",
            mcp_servers=[
                evolomero_mcp,
                nfdi4bioimage_mcp,
            ],

            # Both repositories expose tools with the same names.
            # Including the server name prevents tool-name collisions.
            mcp_config={
                "include_server_in_tool_names": True
            },
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
