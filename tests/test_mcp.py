import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


MCP_URL = "http://127.0.0.1:8001/mcp"

# Example IDs from the Evolomero server.
IMAGE_ID = 427
DATASET_ID = 151


async def main():
    async with streamable_http_client(MCP_URL) as (
        read_stream,
        write_stream,
    ):
        async with ClientSession(
            read_stream,
            write_stream,
        ) as session:

            # Initialize the MCP session.
            await session.initialize()

            # List available MCP tools.
            tools = await session.list_tools()

            print("Available tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}")

            # Test repository statistics.
            print("\nRepository statistics:")
            result = await session.call_tool(
                "get_omero_repository_statistics",
                arguments={},
            )
            print(result)

            # Test image metadata.
            print(f"\nImage metadata for image {IMAGE_ID}:")
            result = await session.call_tool(
                "get_omero_image_metadata",
                arguments={"image_id": IMAGE_ID},
            )
            #print(result)

            # Test dataset metadata.
            print(f"\nDataset metadata for dataset {DATASET_ID}:")
            result = await session.call_tool(
                "get_omero_dataset",
                arguments={"dataset_id": DATASET_ID},
            )
            #print(result)


if __name__ == "__main__":
    asyncio.run(main())
