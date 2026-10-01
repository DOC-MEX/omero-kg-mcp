"""
OMERO Knowledge Graph REST API

Current endpoints:

    GET /api/v1/images/nearby
        Find geolocated images within a given radius.

    GET /api/v1/images/{image_id}
        Retrieve semantic metadata and hierarchical context for an image.

    GET /api/v1/statistics/geolocation
        Count images with geolocation information.

Requirements
------------

Python packages:

    pip install fastapi uvicorn httpx

The server assumes that a QLever endpoint containing the OMERO
Knowledge Graph is available.

The QLever URL can be configured using the QLEVER_URL environment
variable.
"""


import os
import re

import httpx
from fastapi import FastAPI, HTTPException, Query


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

QLEVER_URL = os.getenv(
    "QLEVER_URL",
    "http://127.0.0.1:8888",
)


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="OMERO Knowledge Graph API",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def parse_wkt_point(wkt: str):
    """
    Parse a GeoSPARQL WKT POINT and return latitude and longitude.

    WKT represents coordinates in the order:

        POINT(longitude latitude)

    Returns:
        Dictionary containing latitude and longitude, or None when the
        supplied value is not a simple WKT POINT.
    """

    match = re.fullmatch(
        r"POINT\(\s*([-+]?\d+(?:\.\d+)?)\s+([-+]?\d+(?:\.\d+)?)\s*\)",
        wkt,
    )

    if not match:
        return None

    longitude = float(match.group(1))
    latitude = float(match.group(2))

    return {
        "latitude": latitude,
        "longitude": longitude,
    }


# ===========================================================================
# Geographic image discovery
# ===========================================================================

@app.get("/api/v1/images/nearby")
async def nearby_images(
    lat: float = Query(
        ...,
        ge=-90,
        le=90,
        description="Latitude of the search center",
    ),
    lon: float = Query(
        ...,
        ge=-180,
        le=180,
        description="Longitude of the search center",
    ),
    radius_km: float = Query(
        1.0,
        gt=0,
        le=1000,
        description="Search radius in kilometers",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
        description="Maximum number of images to return",
    ),
):
    """
    Find geolocated OMERO images near a geographic location.

    The endpoint constructs a GeoSPARQL query and uses QLever's
    geof:distance function to calculate the distance between each
    image location and the supplied query point.

    Results are ordered from nearest to farthest.
    """

    sparql = f"""
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>

SELECT DISTINCT
    ?image
    ?id
    ?name
    ?wkt
    ?distanceKm
    ?thumbnail
    ?ome_details
WHERE {{
    ?image a core:Image ;
           dc:identifier ?id ;
           geo:hasGeometry/geo:asWKT ?wkt .

    OPTIONAL {{
        ?image rdfs:label ?name .
    }}

    OPTIONAL {{
        ?image this:thumbnail ?thumbnail .
    }}

    OPTIONAL {{
        ?image this:ome_details ?ome_details .
    }}

    BIND(
        "POINT({lon} {lat})"^^geo:wktLiteral
        AS ?queryPoint
    )

    BIND(
        geof:distance(?wkt, ?queryPoint)
        AS ?distanceKm
    )

    FILTER(?distanceKm <= {radius_km})
}}
ORDER BY ?distanceKm
LIMIT {limit}
"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                QLEVER_URL,
                params={"query": sparql},
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"QLever request failed: {exc}",
        )

    images = []

    for row in data["results"]["bindings"]:
        wkt = row["wkt"]["value"]

        image = {
            "id": int(row["id"]["value"]),
            "name": row.get("name", {}).get("value"),
            "distance_km": float(row["distanceKm"]["value"]),
            "location": parse_wkt_point(wkt),
            "thumbnail": row.get("thumbnail", {}).get("value"),
            "omero_url": row.get("ome_details", {}).get("value"),
        }

        images.append(image)

    return {
        "query": {
            "latitude": lat,
            "longitude": lon,
            "radius_km": radius_km,
            "limit": limit,
        },
        "returned": len(images),
        "images": images,
    }


# ===========================================================================
# Image metadata and semantic context
# ===========================================================================

@app.get("/api/v1/images/{image_id}")
async def get_image(image_id: int):
    """
    Retrieve metadata and Knowledge Graph context for one OMERO image.

    In addition to image-level metadata, the query follows Knowledge
    Graph relationships to recover the Dataset, Project, and OMERO
    repository associated with the image.
    """

    sparql = f"""
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>
PREFIX omekg: <https://ld.openmicroscopy.org/omekg/>

SELECT DISTINCT
    ?image
    ?id
    ?name
    ?description
    ?wkt
    ?thumbnail
    ?ome_details
    ?dataset
    ?dataset_id
    ?dataset_name
    ?project
    ?project_id
    ?project_name
    ?repository
WHERE {{
    ?image a core:Image ;
           dc:identifier ?id .

    FILTER(?id = {image_id})

    OPTIONAL {{
        ?image rdfs:label ?name .
    }}

    OPTIONAL {{
        ?image rdfs:comment ?description .
    }}

    OPTIONAL {{
        ?image geo:hasGeometry/geo:asWKT ?wkt .
    }}

    OPTIONAL {{
        ?image this:thumbnail ?thumbnail .
    }}

    OPTIONAL {{
        ?image this:ome_details ?ome_details .
    }}

    # Recover Dataset and Project context.
    OPTIONAL {{
        ?dataset a core:Dataset ;
                 dc:identifier ?dataset_id ;
                 dcterms:hasPart ?image .

        OPTIONAL {{
            ?dataset rdfs:label ?dataset_name .
        }}

        OPTIONAL {{
            ?project a core:Project ;
                     dc:identifier ?project_id ;
                     dcterms:hasPart ?dataset .

            OPTIONAL {{
                ?project rdfs:label ?project_name .
            }}
        }}
    }}

    # Identify the OMERO repository containing the image.
    OPTIONAL {{
        ?repository a omekg:OMEROServer ;
                    dcterms:hasPart ?image .
    }}
}}
"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                QLEVER_URL,
                params={"query": sparql},
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"QLever request failed: {exc}",
        )

    rows = data["results"]["bindings"]

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Image {image_id} not found",
        )

    row = rows[0]

    # Convert optional SPARQL bindings into a simpler JSON structure.

    location = None
    if "wkt" in row:
        location = parse_wkt_point(row["wkt"]["value"])

    dataset = None
    if "dataset_id" in row:
        dataset = {
            "id": int(row["dataset_id"]["value"]),
            "name": row.get("dataset_name", {}).get("value"),
        }

    project = None
    if "project_id" in row:
        project = {
            "id": int(row["project_id"]["value"]),
            "name": row.get("project_name", {}).get("value"),
        }

    repository = None
    if "repository" in row:
        repository = {
            "iri": row["repository"]["value"],
        }

    return {
        "id": int(row["id"]["value"]),
        "name": row.get("name", {}).get("value"),
        "description": row.get("description", {}).get("value"),
        "thumbnail": row.get("thumbnail", {}).get("value"),
        "omero_url": row.get("ome_details", {}).get("value"),
        "location": location,
        "dataset": dataset,
        "project": project,
        "repository": repository,
    }


# ===========================================================================
# Repository statistics
# ===========================================================================

@app.get("/api/v1/statistics/geolocation")
async def get_geolocation_statistics():
    """
    Retrieve repository-wide statistics about geolocated images.

    An image is considered geolocated when the Knowledge Graph contains
    a GeoSPARQL geometry with a WKT representation for that image.
    """

    sparql = """
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

SELECT
    (COUNT(DISTINCT ?image) AS ?images_with_geolocation)
WHERE {
    ?image a core:Image ;
           geo:hasGeometry/geo:asWKT ?wkt .
}
"""

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                QLEVER_URL,
                params={"query": sparql},
            )

            response.raise_for_status()
            data = response.json()

    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"QLever request failed: {exc}",
        )

    rows = data["results"]["bindings"]

    if not rows:
        raise HTTPException(
            status_code=502,
            detail="QLever returned no geolocation statistics",
        )

    count = int(
        rows[0]["images_with_geolocation"]["value"]
    )

    return {
        "images_with_geolocation": count,
    }