# Task 53 — selected-name JSON derivative

Base: merged PRs 25–27 (`a9c1ed13`). FR-META-008 remains Partial.

Extend the captured single-asset name preview with Save JSON. All seven name
fields remain off by default. Export only explicitly selected names, schema
version, scope and included/omitted field keys; never IDs or other metadata.
Use a bounded deterministic UTF-8 document and a worker for filesystem I/O.
Create a new destination without overwrite: write/close a private staging file,
then publish with an exclusive hard link. Refuse unsupported publication rather
than weaken no-clobber behavior. Report publication and cleanup separately.
An in-flight save keeps its captured payload; closing is held until it finishes.
No catalog/media reads or writes, schema/recovery backend changes, deployment,
hosted experiments or publication are included. Test only generated fixtures.
