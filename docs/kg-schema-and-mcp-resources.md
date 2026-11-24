# OMERO Knowledge Graph schema context and MCP Resources

>In this project, *KG schema* means a curated, plain-text **SPARQL query guide** describing the vocabulary and relationships available in our mapped OMERO Knowledge Graph. It is **not** the PostgreSQL/OMERO relational schema or an OWL ontology.

## 1. From OMERO records to the graph — and to a query guide

```text
OMERO database (actual image, dataset, annotation records)
    |
    | SQL-to-RDF mappings: SQL sources + RDF target templates
    v
Queryable RDF: Ontop (virtual) or materialized triples indexed in QLever
    ^
    | SPARQL SELECT queries execute against these relationships
    |
LLM-generated SPARQL
    ^
    | receives prefixes + classes + properties + graph patterns
    |
Compact KG schema text (served as an MCP Resource)
    ^
    | curated from the RDF target side of the mappings
    |
SQL-to-RDF mapping definitions
```

The mappings determine how RDF is produced; the schema text is separately curated documentation of those resulting RDF paths. **The schema file does not produce RDF triples and is not executed by Ontop or QLever.**

### What a mapping contains

An SQL-to-RDF mapping has a SQL **source** that identifies database rows and an RDF **target** that states what triples those rows create. The file `omero-ontop-mappings.obda` includes the mapping `MAPID-image-geosparql-point`, abbreviated below:

```text
mappingId  MAPID-image-geosparql-point

target    ome_instance:Image/{image_id}
            geo:hasGeometry ome_instance:Image/{image_id}/geometry .
          ome_instance:Image/{image_id}/geometry
            a geo:Geometry ; geo:asWKT {wkt}^^geo:wktLiteral .

source    SELECT ial.parent AS image_id,
                 concat('POINT(', lon.value, ' ', lat.value, ')') AS wkt
          FROM annotation_mapvalue lat
          JOIN annotation_mapvalue lon
            ON lat.annotation_id = lon.annotation_id
          JOIN imageannotationlink ial
            ON ial.child = lat.annotation_id
          WHERE lat.name = 'latitude'
            AND lon.name = 'longitude'
```

In other words, OMERO stores latitude and longitude in map-annotation values. The mapping associates those annotations with an image, constructs a **WKT `POINT(longitude latitude)`**, and relates the image to a geometry node with `geo:hasGeometry` and `geo:asWKT`.

For illustration, image 427 has latitude `51.472264` and longitude `6.962458`, corresponding to a WKT point of `POINT(6.962458 51.472264)` (**longitude first**). Those coordinates are actual repository *data*: they are **not hard-coded into either the mapping rule or the schema guide**.

### What the schema retains and omits

The query guide exposes the RDF path the agent needs:

```sparql
?image geo:hasGeometry ?geometry .
?geometry geo:asWKT ?wkt .
?image dc:identifier ?id .
?image rdfs:label ?name .
```

It deliberately leaves out details that belong to the implementation of the RDF mappings, such as `annotation_mapvalue`, `imageannotationlink`, SQL `JOIN` conditions, `concat(...)`, and URI-construction templates.

The guide is grounded in the *actual mapped RDF vocabulary*. For example, it tells the LLM to traverse `geo:hasGeometry/geo:asWKT` rather than guessing that images possess direct `geo:latitude` and `geo:longitude` properties. A model may know SPARQL syntax but cannot reliably infer this repository-specific RDF representation on its own.

## 2. Why provide a compact description instead of the mapping file?

The complete mapping definitions are useful for development and materialization, but they contain much more implementation detail than an LLM generally needs for writing a SPARQL query. We **could** supply the mappings directly, but the model would then have to infer the RDF model from significantly larger set of instructions.

The following sizes describe the source copies used for this documentation:

| Source | Characters | What it provides |
| --- | ---: | --- |
| `omero-ontop-mappings.obda` | 19,696 | SQL sources and RDF construction templates |
| `mcp/prompts/omero_kg_schema.txt` | 4,880 | All major documented graph sections |
| `mcp/prompts/omero_kg_geolocation.txt` | 686 | Image IDs/names and geometry/WKT paths |
| `mcp/prompts/omero_kg_hierarchy.txt` | 1,524 | Projects, datasets, images and related metadata |
| `mcp/prompts/omero_kg_imaging.txt` | 1,598 | Pixels, channels, physical sizes and ROIs |


A practical benefit of documenting only the needed graph relationships is that the schema can be **split into focused sections**. The agent can use relevant context rather than receiving all unrelated classes and properties.

## 3. Available MCP schema Resources

The MCP server (`mcp/server.py`) registers four plain-text Resources using `@mcp.resource`:

The canonical schema files reside in **`mcp/prompts/`**. In the Python code, `Path(__file__).resolve().parent / "prompts"` is correct because `__file__` refers to `mcp/server.py`. The Markdown links below are relative to this `docs/` directory and therefore use `../mcp/prompts/`.

| MCP Resource URI | Backing file | Scope |
| --- | --- | --- |
| `omero://schema/full` | [`mcp/prompts/omero_kg_schema.txt`](../mcp/prompts/omero_kg_schema.txt) | Complete compact query guide |
| `omero://schema/geolocation` | [`mcp/prompts/omero_kg_geolocation.txt`](../mcp/prompts/omero_kg_geolocation.txt) | Images, geometry and WKT |
| `omero://schema/hierarchy` | [`mcp/prompts/omero_kg_hierarchy.txt`](../mcp/prompts/omero_kg_hierarchy.txt) | Project–Dataset–Image relationships and common metadata |
| `omero://schema/imaging` | [`mcp/prompts/omero_kg_imaging.txt`](../mcp/prompts/omero_kg_imaging.txt) | Pixel metadata, channels and ROIs |

For example, the Geolocation Resource is registered in `mcp/server.py` as:

```python
@mcp.resource(
    "omero://schema/geolocation",
    name="OMERO geolocation schema",
    description="RDF properties for querying geolocated OMERO images.",
    mime_type="text/plain",
)
def get_geolocation_schema() -> str:
    return (
        Path(__file__).resolve().parent
        / "prompts"
        / "omero_kg_geolocation.txt"
    ).read_text(encoding="utf-8")
```

An MCP Resource is **context made available to a client**, not a query-execution tool. The client can read the Resource text and include it in the model's context. To run a dynamically created query, the agent uses the separate `query_knowledge_graph(sparql)` MCP **tool**, which sends a read-only `SELECT` to QLever.

### The two distinct roles

| Component | Role |
| --- | --- |
| `omero://schema/geolocation` (Resource) | Describes the vocabulary and relationships the model may use |
| `query_knowledge_graph(sparql)` (tool) | Executes a query that the agent writes |

**Selecting a Resource does not automatically execute SPARQL.** Conversely, the Resource is not an ontology reasoner or a ready-made repository result.

## 4. How the application and benchmarks use schema context

**Predefined MCP questions.** A request that is already handled by `get_image_details`, `get_omero_image_metadata`, `get_geolocation_statistics`, etc. should normally call that tool **without loading any KG schema**. Some predefined KG tools may themselves call tested, prewritten SPARQL behind the REST API; this is different from the LLM generating a new query.

**Dynamic SPARQL mode (current web app).** In the current version of AI-OMERO, the user can enable dynamic SPARQL. The app supplies the **full schema description** and enables `query_knowledge_graph`. Standard MCP mode omits that schema and disables the dynamic SPARQL tool. 


### decision path (future application design)

```text
User asks an OMERO question
    |
    +-- Can a predefined MCP tool answer it?
    |      |
    |      +-- Yes: use the tool; no KG schema context
    |
    +-- Otherwise: needs a dynamic Knowledge Graph query
           |
           +-- Identify task-relevant Resource section(s)
           +-- Read those descriptions and supply them to the LLM
           +-- Generate SPARQL SELECT
           +-- Execute query_knowledge_graph(sparql)
           +-- Validate/format the returned result
```


## 5. Example: generating SPARQL from the Geolocation Resource

**User question:** “List up to 20 images that have geographic information, with their IDs, names and coordinates.”

The Geolocation Resource tells the model that images use `core:Image`, names use `rdfs:label`, identifiers use `dc:identifier`, and geolocation is expressed as a geometry path. The model chooses the output variables and constructs an executable `SELECT` query, for example:

```sparql
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

SELECT DISTINCT ?id ?name ?wkt
WHERE {
  ?image a core:Image ;
         dc:identifier ?id ;
         rdfs:label ?name ;
         geo:hasGeometry/geo:asWKT ?wkt .
}
LIMIT 20
```

The `?wkt` value is a **WKT geometry literal** (for example `POINT(6.962458 51.472264)`), not two separate numerical latitude and longitude fields. The example is intentionally simple: the main task is to choose *real* RDF paths and return the requested fields, not to demonstrate complex query planning. The actual execution result depends on the repository's indexed graph.

### Example: hierarchy and aggregation

For “Which datasets have the most images?”, the model needs the Hierarchy Resource plus an aggregation, such as:

```sparql
PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?dataset ?name (COUNT(DISTINCT ?image) AS ?image_count)
WHERE {
  ?dataset a core:Dataset ;
           dcterms:hasPart ?image .
  ?image a core:Image .
  OPTIONAL { ?dataset rdfs:label ?name . }
}
GROUP BY ?dataset ?name
ORDER BY DESC(?image_count)
LIMIT 20
```



## 6. Complete schema-file contents (reviewed snapshots)


### 6.1 Full KG schema

Source: [`mcp/prompts/omero_kg_schema.txt`](../mcp/prompts/omero_kg_schema.txt) — 4,880 characters.

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
PREFIX geof: <http://www.opengis.net/def/function/geosparql/>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>
PREFIX omekg: <https://ld.openmicroscopy.org/omekg/>
PREFIX vcard: <http://www.w3.org/2006/vcard/ns#>


CORE RESOURCE TYPES

The graph can contain:

core:Image
core:Dataset
core:Project
core:Experimenter
core:ExperimenterGroup
core:MapAnnotation
core:Plate
core:Well
core:WellSample
core:PlateAcquisition
core:Screen
core:ROI
core:Channel
core:Pixels
core:Reagent
geo:Geometry
omekg:OMEROServer


COMMON RESOURCE METADATA

Numeric OMERO identifier:

?resource dc:identifier ?id .

Name, where mapped:

?resource rdfs:label ?name .

Description, where mapped:

?resource rdfs:comment ?description .

Owner:

?resource core:experimenter ?experimenter .

Experimenter group:

?resource core:experimenter_group ?group .


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


GEOLOCATION

A geolocated image has a GeoSPARQL geometry:

?image a core:Image ;
       geo:hasGeometry ?geometry .

The geometry can contain WKT:

?geometry a geo:Geometry ;
          geo:asWKT ?wkt .

Equivalent property path:

?image geo:hasGeometry/geo:asWKT ?wkt .


MAPANNOTATIONS

An image MapAnnotation is represented as:

?image core:hasAnnotation ?annotation .

?annotation a core:MapAnnotation ;
            dc:identifier ?annotation_id ;
            core:mapEntry ?entry .

Each MapAnnotation entry contains a key and value:

?entry core:key ?key ;
       core:value ?value .

MapAnnotations can also be linked to Project, Dataset, Plate, Screen,
Well, Reagent, and PlateAcquisition resources using core:hasAnnotation.


EXPERIMENTERS AND GROUPS

Experimenter identifier:

?experimenter a core:Experimenter ;
              dc:identifier ?experimenter_id .

Experimenter fields can include:

?experimenter vcard:given-name ?given_name .
?experimenter vcard:family-name ?family_name .
?experimenter vcard:additional-name ?middle_name .
?experimenter vcard:hasEmail ?email .
?experimenter vcard:organization-name ?institution .

Experimenter membership in a group:

?experimenter core:experimenter_group ?group .

Experimenter groups can have:

?group a core:ExperimenterGroup ;
       dc:identifier ?group_id ;
       rdfs:label ?group_name .


PLATES, WELLS, AND WELL SAMPLES

Plate to Well:

?plate a core:Plate ;
       dcterms:hasPart ?well .

Well to WellSample:

?well a core:Well ;
      dcterms:hasPart ?well_sample .

A WellSample can refer to an Image:

?well_sample a core:WellSample ;
             dcterms:relation ?image .

A PlateAcquisition can contain WellSamples:

?plate_acquisition a core:PlateAcquisition ;
                   dcterms:hasPart ?well_sample .

Screen and Plate are related using dcterms:relation:

?screen a core:Screen ;
        dcterms:relation ?plate .

?plate dcterms:relation ?screen .

A Well can reference a Reagent:

?well core:reagent ?reagent .

A WellSample can have:

?well_sample core:well_index ?well_index .


PIXELS, CHANNELS, AND ROIS

Pixels belong to an Image:

?pixels a core:Pixels ;
        dcterms:isPartOf ?image .

Physical pixel sizes are represented through:

?pixels core:physical_size_x ?physical_size_x .
?pixels core:physical_size_y ?physical_size_y .
?pixels core:physical_size_z ?physical_size_z .

The physical-size nodes can contain:

?physical_size this:value ?value ;
               this:unit ?unit .

A Channel is related to Pixels using:

?channel a core:Channel ;
         dcterms:relation ?pixels .

Channel RGB values can be represented with:

?channel this:red ?red ;
         this:green ?green ;
         this:blue ?blue .

An ROI references an Image using:

?roi a core:ROI ;
     core:image ?image .


OMERO SERVER

An OMERO server is represented as:

?server a omekg:OMEROServer .

The server can contain Projects, Datasets, and Images using:

?server dcterms:hasPart ?resource .

```

### 6.2 Geolocation Resource

Source: [`mcp/prompts/omero_kg_geolocation.txt`](../mcp/prompts/omero_kg_geolocation.txt) — 686 characters.

```text
SPARQL KNOWLEDGE GRAPH SCHEMA — GEOLOCATION

Use only the classes and properties described below.
Do not invent predicates or classes.

PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX geo: <http://www.opengis.net/ont/geosparql#>

GEOLOCATION

A geolocated image has a GeoSPARQL geometry:

?image a core:Image ;
       geo:hasGeometry ?geometry .

The geometry can contain WKT:

?geometry a geo:Geometry ;
          geo:asWKT ?wkt .

Equivalent property path:

?image geo:hasGeometry/geo:asWKT ?wkt .

COMMON IMAGE METADATA

?image dc:identifier ?id .
?image rdfs:label ?name .

```

### 6.3 Hierarchy Resource

Source: [`mcp/prompts/omero_kg_hierarchy.txt`](../mcp/prompts/omero_kg_hierarchy.txt) — 1,524 characters.

```text
SPARQL KNOWLEDGE GRAPH SCHEMA — HIERARCHY AND IMAGE METADATA

Use only the classes and properties described below. Do not invent
predicates or classes.

PREFIXES

PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>

CORE RESOURCE TYPES

core:Project
core:Dataset
core:Image
core:Experimenter
core:ExperimenterGroup

COMMON RESOURCE METADATA

Numeric OMERO identifier:

?resource dc:identifier ?id .

Name, where mapped:

?resource rdfs:label ?name .

Description, where mapped:

?resource rdfs:comment ?description .

Owner:

?resource core:experimenter ?experimenter .

Experimenter group:

?resource core:experimenter_group ?group .

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
```

### 6.4 Imaging Resource

Source: [`mcp/prompts/omero_kg_imaging.txt`](../mcp/prompts/omero_kg_imaging.txt) — 1,598 characters.

```text
SPARQL KNOWLEDGE GRAPH SCHEMA — PIXELS, CHANNELS AND ROIS

Use only the classes and properties described below. Do not invent
predicates or classes.

PREFIXES

PREFIX core: <https://ld.openmicroscopy.org/core/>
PREFIX dc: <http://purl.org/dc/elements/1.1/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX this: <https://ld.openmicroscopy.org/omekg#>

CORE RESOURCE TYPES

core:Image
core:Pixels
core:Channel
core:ROI

COMMON RESOURCE METADATA

Numeric OMERO identifier:

?resource dc:identifier ?id .

Name, where mapped:

?resource rdfs:label ?name .

Description, where mapped:

?resource rdfs:comment ?description .

Owner:

?resource core:experimenter ?experimenter .

Experimenter group:

?resource core:experimenter_group ?group .

IMAGE METADATA

Image name:

?image a core:Image ;
       rdfs:label ?image_name .

PIXELS, CHANNELS, AND ROIS

Pixels belong to an Image:

?pixels a core:Pixels ;
        dcterms:isPartOf ?image .

Physical pixel sizes are represented through:

?pixels core:physical_size_x ?physical_size_x .
?pixels core:physical_size_y ?physical_size_y .
?pixels core:physical_size_z ?physical_size_z .

The physical-size nodes can contain:

?physical_size this:value ?value ;
               this:unit ?unit .

A Channel is related to Pixels using:

?channel a core:Channel ;
         dcterms:relation ?pixels .

Channel RGB values can be represented with:

?channel this:red ?red ;
         this:green ?green ;
         this:blue ?blue .

An ROI references an Image using:

?roi a core:ROI ;
     core:image ?image .
```