import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# ------------------------------------------------------------
# MCP server configuration
# ------------------------------------------------------------

# Local MCP endpoint:
# MCP_URL = "http://127.0.0.1:8001/mcp"

# Public Evolomero MCP endpoint:
MCP_URL = "https://evolomero.evolbio.mpg.de/mcp"
# Public NFDI4BIOIMAGE MCP endpoint:
#MCP_URL = "https://omero.nfdi4bioimage.de/kg-mcp/mcp"

# ------------------------------------------------------------
# Test data
# ------------------------------------------------------------
# IDs from the Evolomero server.
IMAGE_ID = 427
DATASET_ID = 151
# test geographic search.
LATITUDE = 51.48618
LONGITUDE = 7.04247
RADIUS_KM = 1.0
LIMIT = 2


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

            # ------------------------------------------------------------
            # List available MCP tools
            # ------------------------------------------------------------

            tools = await session.list_tools()

            print("Available tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}")

            # ============================================================
            # Native OMERO API tools
            # ============================================================

            print("\n" + "=" * 60)
            print("NATIVE OMERO API TOOLS")
            print("=" * 60)

            # Repository statistics.
            print("\n1. Repository statistics:")
            result = await session.call_tool(
                "get_omero_repository_statistics",
                arguments={},
            )
            print(result)

            # Image metadata.
            print(f"\n2. Image metadata for image {IMAGE_ID}:")
            result = await session.call_tool(
                "get_omero_image_metadata",
                arguments={
                    "image_id": IMAGE_ID,
                },
            )
            #### print(result)

            # Dataset metadata.
            print(f"\n3. Dataset metadata for dataset {DATASET_ID}:")
            result = await session.call_tool(
                "get_omero_dataset",
                arguments={
                    "dataset_id": DATASET_ID,
                },
            )
            ## print(result)

            # ============================================================
            # Knowledge Graph / custom REST API tools
            # ============================================================

            print("\n" + "=" * 60)
            print("KNOWLEDGE GRAPH / CUSTOM REST API TOOLS")
            print("=" * 60)

            # Semantic image details.
            print(f"\n4. Knowledge Graph details for image {IMAGE_ID}:")
            result = await session.call_tool(
                "get_image_details",
                arguments={
                    "image_id": IMAGE_ID,
                },
            )
            ##print(result)

            # Geographic image search.
            print(
                f"\n5. Images within {RADIUS_KM} km of "
                f"{LATITUDE}, {LONGITUDE}:"
            )
            result = await session.call_tool(
                "find_images_near_location",
                arguments={
                    "latitude": LATITUDE,
                    "longitude": LONGITUDE,
                    "radius_km": RADIUS_KM,
                    "limit": LIMIT,
                },
            )
            ##print(result)

            # Geolocation statistics.
            print("\n6. Geolocation statistics:")
            result = await session.call_tool(
                "get_geolocation_statistics",
                arguments={},
            )
            print(result)


if __name__ == "__main__":
    asyncio.run(main())