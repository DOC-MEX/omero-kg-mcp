# omero-kg-mcp

Model Context Protocol (MCP) tools, a lightweight REST API, and a simple AI-assisted web interface for accessing OMERO data and an OMERO Knowledge Graph.

The project currently provides three complementary components:

- an **MCP server** exposing selected operations from both the native OMERO JSON API and the OMERO Knowledge Graph;

- a **custom REST API** providing simple access to common SPARQL and GeoSPARQL queries against an OMERO Knowledge Graph indexed with QLever;

- a **lightweight web application** providing a natural-language interface to one or more OMERO repositories through an AI agent and MCP.

The REST API acts as an abstraction layer over the Knowledge Graph, allowing common queries to be performed without constructing SPARQL directly.

For questions that are not covered by the predefined tools, the MCP server can also execute SPARQL `SELECT` queries directly against QLever.

The web application connects an AI agent to one or more OMERO MCP servers. The agent can select and combine native OMERO tools, predefined Knowledge Graph tools, and dynamic SPARQL queries according to the user's question.

## Current MCP tools

The MCP server currently provides seven tools.

### Native OMERO API tools

- **`get_omero_image_metadata(image_id)`**  
  Retrieve native OMERO metadata for an image, including dimensions, pixel information, channels, and other available image metadata.

- **`get_omero_dataset(dataset_id)`**  
  Retrieve information about a dataset, including its name, description, owner, group, permissions, and number of images.

- **`get_omero_repository_statistics()`**  
  Retrieve general repository statistics, including the number of images, datasets, projects, experimenters, and experimenter groups.

### Knowledge Graph tools

- **`get_image_details(image_id)`**  
  Retrieve semantic metadata and context for an image, including its dataset, project, repository, geographic location, thumbnail, and OMERO URL.

- **`find_images_near_location(latitude, longitude, radius_km, limit)`**  
  Find geolocated OMERO images near a geographic location.

- **`get_geolocation_statistics()`**  
  Retrieve the number of images with geographic location information in the Knowledge Graph.

- **`query_knowledge_graph(sparql)`**  
  Execute a SPARQL `SELECT` query directly against the OMERO Knowledge Graph in QLever. This provides access to Knowledge Graph queries that are not covered by the predefined REST API tools.

The first three tools access the native OMERO API directly. The predefined Knowledge Graph tools access the custom REST API, which translates common operations into SPARQL or GeoSPARQL queries against QLever.

The `query_knowledge_graph()` tool provides direct read-only SPARQL access to QLever for queries that are not covered by the predefined tools.

## Knowledge Graph schema

The project includes a compact description of the OMERO Knowledge Graph schema:

```text
prompts/omero_kg_schema.txt
```
The file is organized into sections, each describing the RDF classes, properties, and graph patterns for a particular part of the OMERO data model, for our OMERO knowledge graph we have these sections:

- PREFIXES — namespace/prefix definitions
- CORE RESOURCE TYPES — resource/class definitions
- COMMON RESOURCE METADATA — common metadata properties
- PROJECT, DATASET, AND IMAGE HIERARCHY — hierarchy domain section
- IMAGE METADATA — image metadata domain section
- GEOLOCATION — geospatial domain section
- MAPANNOTATIONS — annotation domain section
- EXPERIMENTERS AND GROUPS — user/group domain section
- PLATES, WELLS, AND WELL SAMPLES — high-content-screening domain section
- PIXELS, CHANNELS, AND ROIS — imaging metadata domain section
- OMERO SERVER — repository/server domain section

A general-purpose LLM can already generate SPARQL syntax, but it does not inherently know how a particular OMERO Knowledge Graph represents Images, Datasets, Projects, annotations, or geographic information. Without this information, a model could generate plausible or valid SPARQL but using predicates or relationships that do not exist in the graph.

The schema therefore provides the agent with the specific information required for valid SPARQL generation. 
The following excerpt shows how the vocabulary, relationships, and  patterns are described in the schema file (`omero_kg_schema.txt`):

```text
SPARQL KNOWLEDGE GRAPH SCHEMA

Use only the classes and properties described below. Do not invent
predicates or classes.


PREFIXES

PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>
...


CORE RESOURCE TYPES

The graph can contain:

core:Image
core:Dataset
core:Project
core:Experimenter
core:ExperimenterGroup
core:MapAnnotation
...

PROJECT, DATASET, AND IMAGE HIERARCHY

Project to Dataset:

?project a core:Project ;
         dcterms:hasPart ?dataset .

Dataset to Project:

?dataset dcterms:isPartOf ?project .

Dataset to Image:

?dataset a core:Dataset ;
         dcterms:hasPart ?image .

Image to Dataset:

?image dcterms:isPartOf ?dataset .


IMAGE METADATA

Image name:

?image a core:Image ;
       rdfs:label ?image_name .

Image acquisition date:

?image this:acquisition_date ?acquisition_date .

Image thumbnail:

?image this:thumbnail ?thumbnail .

Tag value attached directly by the mapping:

?image this:tag_annotation_value ?tag .

Dataset tags are also available as:

?dataset this:tag_annotation_value ?tag .
...
```

The file describes graph patterns rather than only listing vocabulary it tells the agent not only which classes and properties exist, but also how resources are connected.

For example, the schema tells the agent that a Dataset contains an Image through:

```sparql
?dataset a core:Dataset ;
         dcterms:hasPart ?image .
```

that an Image identifier and name can be retrieved using:

```sparql
?image dc:identifier ?image_id ;
       rdfs:label ?image_name .
```

For example, given the natural-language question:

```text
Which geolocated images belong to the Duisburg dataset?
Give me their image IDs and names.
```

the agent can identify the required relationships from the schema and construct a query such as:

```sparql
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

SELECT DISTINCT ?image_id ?image_name
WHERE {
    ?dataset a core:Dataset ;
             rdfs:label ?dataset_name ;
             dcterms:hasPart ?image .

    FILTER(LCASE(STR(?dataset_name)) = LCASE("Duisburg"))

    ?image a core:Image ;
           dc:identifier ?image_id ;
           rdfs:label ?image_name ;
           geo:hasGeometry/geo:asWKT ?wkt .
}
LIMIT 20
```

In this example, the query was not predefined in the REST API or MCP server. The agent generated it dynamically by combining graph patterns from different sections of the schema.

The generated `SELECT` query is passed to the `query_knowledge_graph()` MCP tool and executed directly against QLever.

The schema does not replace the OBDA mapping used to construct the Knowledge Graph. Instead, it provides a compact description of the resulting graph that can be supplied to an LLM for SPARQL generation.

## Custom Knowledge Graph REST API

The custom REST API provides simplified access to common queries against the OMERO Knowledge Graph.

It currently provides three endpoints:

- **`GET /api/v1/images/{image_id}`**  
  Retrieve semantic metadata and hierarchical context for an image, including its dataset, project, repository, geographic location, thumbnail, and OMERO URL when available.

- **`GET /api/v1/images/nearby`**  
  Find geolocated OMERO images within a specified radius of a geographic coordinate using GeoSPARQL.

- **`GET /api/v1/statistics/geolocation`**  
  Return the number of images represented in the Knowledge Graph with geographic location information.

The REST API translates these requests into SPARQL or GeoSPARQL queries and sends them to QLever.

## Requirements

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the required packages:

```bash
pip install httpx uvicorn mcp fastapi openai openai-agents jinja2 python-multipart
```

The MCP server expects an OMERO JSON API endpoint of the form:

```text
https://<omero-server>/api/v0/m
```

The custom REST API requires access to a QLever endpoint containing the OMERO Knowledge Graph.

By default, the current example configuration assumes:

```text
QLever:     http://127.0.0.1:8888
```

## Running the custom REST API

The custom REST API provides access to the OMERO Knowledge Graph and should be running when using the Knowledge Graph MCP tools.

Start the REST API from its directory with:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000
```

By default, the REST API is available locally at:

```text
http://127.0.0.1:8000
```

The MCP server connects to this service using `REST_API_URL`.

## Running the MCP server

With the custom REST API running, start the MCP server from its directory with:

```bash
python server.py
```

By default, Uvicorn listens locally on:

```text
http://127.0.0.1:8001
```

The Streamable HTTP MCP endpoint is:

```text
http://127.0.0.1:8001/mcp
```

The MCP server accesses both the native OMERO API and the custom Knowledge Graph REST API.

The MCP endpoint can be exposed through a reverse proxy such as Nginx. For example, the Evolomero deployment exposes it at:

```text
https://evolomero.evolbio.mpg.de/mcp
```
## Running the web application

The lightweight web application provides a natural-language interface to the OMERO MCP tools.

The application uses an AI agent to interpret a user's question, select the appropriate MCP server and tools, and combine the returned metadata into a concise answer.

For common operations, the agent can use the predefined native OMERO and Knowledge Graph tools. For Knowledge Graph questions that are not covered by those tools, the agent can generate a SPARQL query and execute it through the repository's `query_knowledge_graph()` MCP tool.

Before starting the application, make sure that the required API key is available:

```bash
export SAIA_API_KEY="..."
```

Start the web application from its directory with:

```bash
uvicorn app:app --host 127.0.0.1 --port 8002
```

The current application connects to two MCP servers:

```text
Evolomero:
https://evolomero.evolbio.mpg.de/mcp

NFDI4BIOIMAGE:
https://omero.nfdi4bioimage.de/kg-mcp/mcp
```

The default model in the current configuration is:

```text
openai-gpt-oss-120b
```

## Architecture

The three components form a simple layered architecture:

```text
                         Web application
                              :8002
                                |
                           AI agent
                                |
                         MCP server(s)
                              :8001
                    /           |           \
                   /            |            \
          Native OMERO API   Custom REST API   Dynamic SPARQL
                                  :8000              |
                                    |                |
                                    +------ QLever ---+
                                             |
                                   OMERO Knowledge Graph
```

## Testing the native OMERO API

The native OMERO API can be tested independently with `curl`.

### Image metadata

For example, retrieve metadata for image `427`:

```bash
curl -s \
  "https://evolomero.evolbio.mpg.de/api/v0/m/images/427/"
```

### Repository counts

The OMERO API exposes collection counts through the `meta.totalCount` field.

For example:

```bash
curl -s \
  "https://evolomero.evolbio.mpg.de/api/v0/m/images/?limit=1" \
  | python -m json.tool
```

The same approach can be used for other resources:

```bash
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/datasets/?limit=1"
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/projects/?limit=1"
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/experimenters/?limit=1"
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/experimentergroups/?limit=1"
```

The MCP tool `get_omero_repository_statistics()` performs these requests concurrently and returns the counts in a single result.

## Testing the custom REST API

With the REST API running on port `8000`, its endpoints can be tested independently.

### Image details

```bash
curl -s \
  "http://127.0.0.1:8000/api/v1/images/427" \
  | python -m json.tool
```

### Nearby image search

```bash
curl -s -G \
  "http://127.0.0.1:8000/api/v1/images/nearby" \
  --data-urlencode "lat=51.48618" \
  --data-urlencode "lon=7.04247" \
  --data-urlencode "radius_km=1.0" \
  --data-urlencode "limit=2" \
  | python -m json.tool
```

### Geolocation statistics

```bash
curl -s \
  "http://127.0.0.1:8000/api/v1/statistics/geolocation" \
  | python -m json.tool
```


## Testing the MCP server

The included test client connects directly to the MCP endpoint and:

1. Initializes an MCP session.
2. Lists the available tools.
3. Calls native OMERO tools.
4. Calls custom REST API tools.
5. Tests a dynamic SPARQL query.

Run it while `server.py` is running:

```bash
python test_mcp.py
```

The script `test_mcp.py` tests the MCP server directly, without using an AI agent.

```text
Native OMERO API tools:
get_omero_image_metadata
get_omero_repository_statistics
get_omero_dataset

Knowledge Graph REST API tools:
get_image_details
find_images_near_location
get_geolocation_statistics
query_knowledge_graph
```
## Testing the MCP server with an AI agent

The script `test_AI.py` provides a test of the MCP server using an AI agent.

Unlike `test_mcp.py`, which calls MCP tools directly with predefined arguments, `test_AI.py` starts from a natural-language question:

```text
Which geolocated images belong to the Duisburg dataset?
Give me their image IDs and names.
```

The agent receives the Knowledge Graph schema from:

```text
prompts/omero_kg_schema.txt
```

The schema describes the classes, properties, relationships, and prefixes available in the OMERO Knowledge Graph. It provides the agent with the information required to construct SPARQL queries without assuming predicates or relationships that are not represented in the graph.

The agent is instructed to prefer the predefined MCP tools when they can fully answer the question. When a question requires additional Knowledge Graph relationships, filtering, grouping, or aggregation, it can generate a SPARQL SELECT query from the supplied schema. The test can be configured to connect to either the Evolomero or NFDI4BIOIMAGE MCP server.