# omero-kg-mcp

Model Context Protocol (MCP) tools and a lightweight REST API for accessing OMERO data and an OMERO Knowledge Graph.

The project currently provides two complementary components:

- an **MCP server** exposing selected operations from both the native OMERO JSON API and the custom Knowledge Graph REST API;
- a **custom REST API** providing simple access to common SPARQL and GeoSPARQL queries against an OMERO Knowledge Graph indexed with QLever.

The REST API acts as an abstraction layer over the Knowledge Graph, allowing to perform common queries without constructing SPARQL directly.

## Current MCP tools

The MCP server currently provides six tools.

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

The first three tools access the native OMERO API directly. The Knowledge Graph tools access the custom REST API, which translates the requests into SPARQL or GeoSPARQL queries against QLever.

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
pip install httpx uvicorn mcp fastapi
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

For development and testing, automatic reload can be enabled:

```bash
uvicorn app:app --host 127.0.0.1 --port 8000 --reload
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

1. initializes an MCP session;
2. lists the available tools;
3. calls `get_omero_repository_statistics`;
4. calls `get_omero_image_metadata`;
5. calls `get_omero_dataset`.

Run it while `server.py` is running:

```bash
python test_mcp.py
```

The server should currently expose:

```text
get_omero_image_metadata
get_omero_repository_statistics
get_omero_dataset
```

