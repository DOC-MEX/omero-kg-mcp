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

## Knowledge Graph schema and MCP Resources

The project includes a curated, plain-text **Knowledge Graph schema description** that helps an LLM construct SPARQL queries using RDF classes and relationships actually represented in our OMERO Knowledge Graph. In this repository, *schema* means a **query guide** for the LLM, not the underlying OMERO relational database schema.

The descriptions are derived from the RDF side of the SQL-to-RDF mappings. They document graph paths such as `?image geo:hasGeometry/geo:asWKT ?wkt` without exposing SQL joins or embedding repository records.

The MCP server exposes four schema descriptions as **MCP Resources**:

| MCP Resource | Backing file | Scope |
| --- | --- | --- |
| `omero://schema/full` | `mcp/prompts/omero_kg_schema.txt` | Full compact KG query guide |
| `omero://schema/geolocation` | `mcp/prompts/omero_kg_geolocation.txt` | Geolocated images and WKT geometry |
| `omero://schema/hierarchy` | `mcp/prompts/omero_kg_hierarchy.txt` | Projects, datasets and images |
| `omero://schema/imaging` | `mcp/prompts/omero_kg_imaging.txt` | Pixels, channels and ROIs |

**[Read the detailed documentation: KG schema, SQL-to-RDF mappings, MCP Resources, example queries and the full contents of all four schema files](docs/kg-schema-and-mcp-resources.md).**

For predefined MCP questions, the web application's Standard mode does not supply KG schema context. Its Dynamic SPARQL mode currently supplies the full schema guide; automatic Resource selection has not been yet implemented into the web app.

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
qwen3-coder-next
```

## Model selection and agent modes

The web application currently allows the user to select between several language models available through the Academic Cloud API:

```text
qwen3-coder-next
qwen3.6-35b-a3b
qwen3.5-397b-a17b
```

`qwen3.5-397b-a17b` was used as an initial selection, while `qwen3-coder-next` and `qwen3.6-35b-a3b` are currently being evaluated as alternatives as faster alternative.

The application also provides two agent modes:

- **Standard MCP** — uses the predefined native OMERO and Knowledge Graph MCP tools. Dynamic SPARQL is disabled and the Knowledge Graph schema is not added to the model context.
- **Dynamic SPARQL** — enables the `query_knowledge_graph()` tool and provides the Knowledge Graph schema to the agent, allowing it to generate SPARQL queries when the predefined tools are not sufficient.

The same model can be tested under different workload.

The current goal is to evaluate whether different models are better suited to different tasks, for example:

- relatively simple requests that can be answered through predefined MCP tools;
- requests that require combining information from several MCP tools;
- more complex Knowledge Graph questions requiring schema-grounded dynamic SPARQL generation.

For each request, the web application reports the selected model and agent mode together with execution time, total token usage, and the MCP tools that were called. These measurements provide an initial basis for comparing model efficiency and tool selection.


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
mcp/prompts/omero_kg_schema.txt
```

The schema describes the classes, properties, relationships, and prefixes available in the OMERO Knowledge Graph. It provides the agent with the information required to construct SPARQL queries without assuming predicates or relationships that are not represented in the graph.

The agent is instructed to prefer the predefined MCP tools when they can fully answer the question. When a question requires additional Knowledge Graph relationships, filtering, grouping, or aggregation, it can generate a SPARQL SELECT query from the supplied schema. The test can be configured to connect to either the Evolomero or NFDI4BIOIMAGE MCP server.