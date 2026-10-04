# Gallery usability feedback record

Source: the user's explicit Phase 1a request on 4 October 2026, as recorded in
[Task 20](tasks/20-gallery-usability-implementation.md). This file records
priorities only. It does not claim observed defects, timings, screenshots, or
test outcomes.

| Confirmed user priority | SDD v0.2 mapping | Acceptance intent |
| --- | --- | --- |
| Thumbnails preserve image shape instead of distorting it. | FR-UX-001, FR-MEDIA-001, FR-MEDIA-003, FR-MEDIA-004 | Generated portrait, landscape, square, EXIF-oriented, and alpha fixtures retain correct aspect/orientation and source bytes. Any crop mode is identified accurately. |
| Image loading feels responsive. | FR-UX-001, FR-UX-006, FR-JOB-001, FR-JOB-003, FR-JOB-004 | Capture cold/warm visible loading and timer-heartbeat behavior under generated-fixture load, plus selection safety when work finishes stale. Candidate numerical budgets remain proposals unless separately adopted. |
| Full-image viewing works. | FR-UX-002, FR-MEDIA-001, FR-MEDIA-003, FR-UX-010 | Inspect the captured asset's supported original pixels with orientation, fit, zoom, pan, alpha background choice, keyboard controls, and truthful unsupported/error states. |
| The app has correct Fedora/KDE identity. | Derived requirement only, anchored to SDD §§15, 20–22; no SDD ID is assigned. | Check product/window/application identity, icon, packaged desktop entry, and actual KDE Wayland app-id/window grouping. |

The explicit request names priorities but supplies no more precise visual
observations, reproduction steps, performance thresholds, or identity failure
details. Those are left for generated-fixture acceptance and native evidence;
they are not inferred as user statements. The candidate budgets in SDD §19.2
remain unadopted.
