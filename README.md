# omero-kg-mcp


Model Context Protocol (MCP) tools for accessing OMERO data and, in later versions, OMERO Knowledge Graph services.

The initial version provides a small MCP server that uses the **native OMERO JSON API**. It exposes common OMERO operations as MCP tools that can be used directly by MCP clients or by AI agents.

## Current MCP tools

The initial MCP server provides three tools:

- **`get_omero_image_metadata(image_id)`**  
  Retrieve native OMERO metadata for an image, including dimensions, pixel information, channels, and other available image metadata.

- **`get_omero_dataset(dataset_id)`**  
  Retrieve information about a dataset, including its name, description, owner, group, permissions, and number of images.

- **`get_omero_repository_statistics()`**  
  Retrieve general repository statistics, including the number of images, datasets, projects, experimenters, and experimenter groups.

These tools currently rely only on the native OMERO API.

## Requirements

Python packages:

```bash
pip install httpx uvicorn mcp
```

The MCP server expects an OMERO JSON API endpoint of the form:

```text
https://<omero-server>/api/v0/m
```

By default, `server.py` uses the Evolomero server:

```text
https://evolomero.evolbio.mpg.de/api/v0/m
```


## Running the MCP server

Start the server with:

```bash
python server.py
```

By default, Uvicorn listens locally on:

```text
http://127.0.0.1:8001
```

and the Streamable HTTP MCP endpoint is:

```text
http://127.0.0.1:8001/mcp
```

This endpoint can be exposed through a reverse proxy such as Nginx.

For example, the Evolomero deployment exposes the MCP endpoint at:

```text
https://evolomero.evolbio.mpg.de/mcp
```

## Testing the native OMERO API

Before starting the MCP server, the native OMERO API can be tested directly with `curl`.

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

The same approach can be used for the other resources:

```bash
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/datasets/?limit=1"
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/projects/?limit=1"
curl -s "https://evolomero.evolbio.mpg.de/api/v0/m/experimenters/?limit=1"
```

The MCP tool `get_omero_repository_statistics()` performs these requests concurrently and returns the counts in a single result.

## Testing the MCP server

The included test client connects directly to the local MCP endpoint and:

1. initializes an MCP session;
2. lists the available tools;
3. calls `get_omero_repository_statistics`;
4. calls `get_omero_image_metadata`;
5. calls `get_omero_dataset`.

Run it while `server.py` is running:

```bash
python test_mcp.py
```

The server should expose:

```text
get_omero_image_metadata
get_omero_repository_statistics
get_omero_dataset
```

