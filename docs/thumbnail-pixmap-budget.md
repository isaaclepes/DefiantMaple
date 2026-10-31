# Retained gallery pixmap budget

The GUI thumbnail LRU retains at most 128 MiB of estimated raster storage and
1024 entries, across all requested sizes, assets and image types. Costs use
physical QPixmap dimensions, rows rounded to 32-bit alignment, at least 32 bits
per pixel (or the reported depth if larger), plus 4096 bytes per entry.
Device pixel ratio is already represented in physical width/height. Shared
storage is charged per entry, conservatively double-counting aliases.

Visible successful lookups refresh pixel and metadata recency. Foreground
admission evicts cold pixels until both limits fit; a single over-budget or
null pixmap is refused. Replacement, binding invalidation and successful worker
shutdown release accounting. Metadata for resident pixels remains available;
only nonresident result/error history is independently limited to256 entries.
Thus total result/binding entries are at most1280. Pixel eviction does not
immediately destroy useful bounded status history. Speculation can consume only
spare capacity and declines at the nonresident metadata bound; it never evicts
foreground pixels. Existing stale-generation, binding, queue and uncertain-child
cleanup guards remain applicable.

128 MiB is approximately0.8% of a16 GiB machine's memory, leaving most memory
for the catalog, application, operating system and other programs. The1024
entry cap also bounds bookkeeping for tiny thumbnails; it is a safety ceiling,
not a retention target. At128px,300 square RGBA pixmaps cost about19.9 MiB and
remain reusable beyond the previous256-entry boundary.

This is an estimated retained raster budget, not a process RSS guarantee or a
Qt/native allocator measurement. It excludes temporary QImage/decoder storage,
conversion overlap, platform/GPU duplication, allocator fragmentation, text and
Python object storage, the separate detail preview, model pages and disk cache.
The existing single-delivery acknowledgement bounds queued decoded images;
this change does not modify decoding, disk-cache policy, concurrency or source
access. Tests use deterministic generated images and temporary catalogs. No
production library, packaging, deployment or native runtime qualification is
claimed.
