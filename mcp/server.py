"""
OMERO MCP Server

Requirements
------------

Python packages:

    pip install httpx uvicorn mcp

The server assumes:

1. A running OMERO server with its JSON API available.

2. The MCP server runs locally on port 8001.

3. A reverse proxy (for example Nginx) may expose the local MCP endpoint
   externally. On Evolomero this is currently exposed as:

       https://evolomero.evolbio.mpg.de/mcp

4. The native OMERO API is available at:

       https://<omero-server>/api/v0/m

   The server URL can be configured using the OMERO_API_URL
   environment variable.

The MCP server uses Streamable HTTP transport.
"""

import asyncio
import os
import re

import httpx
import uvicorn

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Native OMERO JSON API.
#
# The "/api/v0/m" API exposes OMERO objects such as images, datasets,
# projects, experimenters, and experimenter groups.
#

OMERO_API_URL = os.getenv(
    "OMERO_API_URL",
    "https://evolomero.evolbio.mpg.de/api/v0/m",
    #"http://127.0.0.1:4080/api/v0/m",
    #"https://omero.nfdi4bioimage.de/api/v0/m",
)

# Custom REST API providing simplified access to common
# OMERO Knowledge Graph queries.
REST_API_URL = os.getenv(
    "REST_API_URL",
    "http://127.0.0.1:8000",
)

# Local QLever SPARQL endpoint for dynamic queries.
QLEVER_URL = os.getenv(
    "QLEVER_URL",
    "http://127.0.0.1:8888",
)

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

# Tool descriptions and Python type annotations are used by MCP clients
# and AI agents to understand the available tools and their arguments.
mcp = MCPServer(
    "OMERO MCP"
)

# ---------------------------------------------------------------------------
# Native OMERO API tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_omero_image_metadata(
    image_id: int,
) -> dict:
    """
    Retrieve native OMERO metadata for a specific image.

    Use this tool for questions about the technical metadata associated
    with an OMERO image, such as image dimensions, pixel information,
    channels, acquisition metadata, and other information exposed by
    the native OMERO API.

    Args:
        image_id: Numeric OMERO image identifier.

    Returns:
        Native OMERO JSON metadata for the requested image.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{OMERO_API_URL}/images/{image_id}/"
        )

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def get_omero_repository_statistics() -> dict:
    """
    Retrieve general statistics about the OMERO repository.

    Use this tool for repository-wide questions such as:

    - How many images are on the server?
    - How many datasets are there?
    - How many projects are there?
    - How many experimenters/users are there?
    - How many experimenter groups are there?

    The OMERO API provides the total number of objects in the
    ``meta.totalCount`` field. Requesting only one object therefore
    avoids downloading the complete collection when only the count
    is required.

    Returns:
        Counts of images, datasets, projects, experimenters,
        and experimenter groups visible through the OMERO API.
    """

    resources = {
        "images": "images",
        "datasets": "datasets",
        "projects": "projects",
        "experimenters": "experimenters",
        "experimenter_groups": "experimentergroups",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:

        async def get_count(endpoint: str) -> int:
            response = await client.get(
                f"{OMERO_API_URL}/{endpoint}/",
                params={"limit": 1},
            )

            response.raise_for_status()

            data = response.json()

            return data["meta"]["totalCount"]

        # Query the independent OMERO resources concurrently.
        counts = await asyncio.gather(
            *[
                get_count(endpoint)
                for endpoint in resources.values()
            ]
        )

    return dict(zip(resources.keys(), counts))


@mcp.tool()
async def get_omero_dataset(
    dataset_id: int,
) -> dict:
    """
    Retrieve native OMERO information about a specific dataset.

    Use this tool for questions about a dataset, including its name,
    description, owner, group, permissions, and number of images.

    The ``childCount=true`` parameter asks OMERO to include the number
    of images belonging to the dataset.

    Args:
        dataset_id: Numeric OMERO dataset identifier.

    Returns:
        Native OMERO dataset metadata. The field ``omero:childCount``
        contains the number of images in the dataset when available.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{OMERO_API_URL}/datasets/{dataset_id}/",
            params={"childCount": "true"},
        )

        response.raise_for_status()

        return response.json()


# ---------------------------------------------------------------------------
# Knowledge Graph / custom REST API tools
# ---------------------------------------------------------------------------

# These tools use the custom REST API rather than the native OMERO API.

@mcp.tool()
async def get_image_details(
    image_id: int,
) -> dict:
    """
    Retrieve Knowledge Graph metadata and context for an OMERO image.

    Use this tool for semantic information about an image, including
    its dataset, project, repository, geographic location, thumbnail,
    and OMERO URL when available.

    For technical image metadata such as dimensions, channels, pixel
    information, and acquisition metadata, use
    ``get_omero_image_metadata`` instead.

    Args:
        image_id: Numeric OMERO image identifier.

    Returns:
        Image metadata and hierarchical context obtained from the
        OMERO Knowledge Graph.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{REST_API_URL}/api/v1/images/{image_id}",
        )

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def find_images_near_location(
    latitude: float,
    longitude: float,
    radius_km: float = 1.0,
    limit: int = 20,
) -> dict:
    """
    Find OMERO images near a geographic location.

    Use this tool to search the OMERO Knowledge Graph for images
    within a given radius of a latitude and longitude.

    The geographic search is performed by the custom REST API using
    GeoSPARQL queries against the Knowledge Graph.

    Args:
        latitude: Latitude of the search center in decimal degrees.
        longitude: Longitude of the search center in decimal degrees.
        radius_km: Search radius in kilometers.
        limit: Maximum number of images to return.

    Returns:
        Matching OMERO images ordered by distance from the query point.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{REST_API_URL}/api/v1/images/nearby",
            params={
                "lat": latitude,
                "lon": longitude,
                "radius_km": radius_km,
                "limit": limit,
            },
        )

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def get_geolocation_statistics() -> dict:
    """
    Retrieve repository-wide geolocation statistics.

    Use this tool for questions about how many images in the repository
    have geographic location information represented in the Knowledge
    Graph.

    An image is considered geolocated when the Knowledge Graph contains
    a GeoSPARQL geometry with a WKT representation for that image.

    Returns:
        Number of images with geolocation data in the Knowledge Graph.
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{REST_API_URL}/api/v1/statistics/geolocation",
        )

        response.raise_for_status()

        return response.json()


# ---------------------------------------------------------------------------
# Dynamic Knowledge Graph query tool
# ---------------------------------------------------------------------------

@mcp.tool()
async def query_knowledge_graph(
    sparql: str,
) -> dict:
    """
    Execute a read-only SPARQL SELECT query against the OMERO
    Knowledge Graph.

    Use this tool only when the user's question cannot be answered
    by one of the specialized OMERO or Knowledge Graph tools.

    Only SELECT queries are permitted.

    Args:
        sparql: A SPARQL SELECT query using the OMERO Knowledge
                Graph schema.

    Returns:
        SPARQL query results returned by QLever.
    """

    query = sparql.strip()

    if not query:
        raise ValueError(
            "SPARQL query must not be empty"
        )

    # Remove PREFIX declarations before checking the query form.
    query_without_prefixes = re.sub(
        r"(?im)^\s*PREFIX\s+[^\n]+\n?",
        "",
        query,
    ).lstrip()

    if not query_without_prefixes.upper().startswith("SELECT"):
        raise ValueError(
            "Only read-only SPARQL SELECT queries are allowed"
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            QLEVER_URL,
            params={
                "query": query,
            },
        )

        response.raise_for_status()

        return response.json()

# ---------------------------------------------------------------------------
# MCP transport security
# ---------------------------------------------------------------------------

# Local addresses allow development and testing. The public hostname
# allows access when the MCP server is exposed through the reverse proxy.
# Add additional hostnames or origins as needed, for example
# omero.nfdi4bioimage.de
security = TransportSecuritySettings(
    allowed_hosts=[
        "127.0.0.1:8001",
        "localhost:8001",
        "evolomero.evolbio.mpg.de",
        "evolomero.evolbio.mpg.de:*",
    ],
    allowed_origins=[
        "http://127.0.0.1:8001",
        "http://localhost:8001",
        "https://evolomero.evolbio.mpg.de",
    ],
)

# ---------------------------------------------------------------------------
# Streamable HTTP application
# ---------------------------------------------------------------------------
# The MCP Streamable HTTP endpoint is exposed at /mcp.
app = mcp.streamable_http_app(
    transport_security=security,
)


if __name__ == "__main__":

    # Bind only to localhost. External access should normally be provided
    # through a reverse proxy such as Nginx.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
    )