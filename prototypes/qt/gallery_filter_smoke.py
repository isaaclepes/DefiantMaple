"""Read-only frozen-artifact check of the bounded gallery filter controls."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
import builtins
import os
from pathlib import Path
import time
from unittest.mock import patch

from defiantmaple.curation import FavoriteFilter
from defiantmaple.gallery_query import GalleryQuery


def _wait(app, predicate, description: str, seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    raise RuntimeError(f"Frozen gallery filter smoke timed out: {description}")


@contextmanager
def _refuse_source_io(source_roots: tuple[Path, ...]):
    """Count only source-path operations after legacy startup validation."""
    roots = tuple(os.path.abspath(os.fspath(root)) for root in source_roots)
    attempts = []

    def guarded(name, original):
        def call(path, *args, **kwargs):
            if not isinstance(path, int):
                try:
                    candidate = os.path.abspath(os.fsdecode(os.fspath(path)))
                except TypeError:
                    candidate = ""
                if any(candidate == root or candidate.startswith(root + os.sep)
                       for root in roots):
                    attempts.append(name)
                    raise AssertionError("Bounded gallery filter touched a registered source path")
            return original(path, *args, **kwargs)
        return call

    with ExitStack() as stack:
        for owner, name in ((builtins, "open"), (os, "open"), (os, "stat"),
                            (os, "lstat"), (os, "listdir"), (os, "scandir"),
                            (Path, "open"), (Path, "resolve")):
            stack.enter_context(patch.object(owner, name, guarded(name, getattr(owner, name))))
        yield attempts


def run_gallery_filter_smoke(app, window_type, catalog: Path,
                             scratch: Path, source_roots: list[Path]) -> dict:
    """Exercise the packaged gateway and picker, returning fixed nonidentifying JSON."""
    scratch = Path(scratch).resolve(strict=True)
    source_roots = tuple(Path(root).resolve(strict=True) for root in source_roots)
    window = window_type(catalog, enable_thumbnails=False,
                         cache_root=scratch / "cache", private_root=scratch / "private",
                         external_settings_path=scratch / "external-settings.json")
    try:
        window.show()
        _wait(app, lambda: window._startup_validated and window.model._actionable and
              window.model._token is not None and window.source_box.count() == 3,
              "source validation, list, count, and first page")
        _wait(app, lambda: window.catalog_client.gateway.pending_count == 0,
              "legacy startup work settled")
        model = window.model
        def labels():
            return [Path(model.asset_at(row)["current_path"]).name
                    for row in range(model.rowCount())]
        if labels() != ["alpha.png", "bravo.jpg", "charlie.png"]:
            raise AssertionError("Frozen gallery filter smoke initial order differed")
        if window.source_box.currentData() is not None:
            raise AssertionError("Scan target changed during gallery startup")

        with _refuse_source_io(source_roots) as source_attempts:
            def forbidden(*_args, **_kwargs):
                raise AssertionError("Bounded picker dispatched legacy source enumeration or scan")
            original_legacy = window._legacy
            def guarded_legacy(key, name, *args, **kwargs):
                if name in ("list_sources", "source_issues", "validate_source_roots"):
                    raise AssertionError("Bounded picker dispatched legacy source management")
                return original_legacy(key, name, *args, **kwargs)
            with patch.object(window, "refresh_source_issues", forbidden), \
                 patch.object(window, "refresh_sources", forbidden), \
                 patch.object(window, "start_source_scan", forbidden), \
                 patch.object(window, "_legacy", guarded_legacy):
                tag = window.gallery_tag_picker
                tag.browse.click()
                _wait(app, lambda: not tag._loading and tag.results.count() == 64,
                      "first bounded canonical tag page")
                first = [tag.results.item(row).text() for row in range(tag.results.count())]
                expected_first = ["Child", "Parent"] + [f"Topic {index:03}" for index in range(62)]
                if first != expected_first or not tag.more.isEnabled():
                    raise AssertionError("Frozen canonical first page or continuation differed")
                tag.more.click()
                _wait(app, lambda: not tag._loading and tag.results.count() == 4,
                      "second bounded canonical tag page")
                second = [tag.results.item(row).text() for row in range(tag.results.count())]
                if second != ["Topic 062", "Topic 063", "Topic 064", "Unassigned"]:
                    raise AssertionError("Frozen canonical continuation differed")

                tag.text.setText("Night Study")
                _wait(app, lambda: not tag._loading and tag.results.count() == 1,
                      "canonical alias result")
                if tag.results.item(0).text() != "Parent":
                    raise AssertionError("Alias did not resolve to its canonical tag")
                tag.results.itemClicked.emit(tag.results.item(0))
                parent_id = tag.selected_id
                if not parent_id:
                    raise AssertionError("Canonical alias selection has no stable identity")

                entity = window.gallery_entity_picker
                entity.text.setText("Phoenix")
                _wait(app, lambda: not entity._loading and entity.results.count() == 2,
                      "category-qualified entity results")
                entity_labels = [entity.results.item(row).text() for row in range(2)]
                if entity_labels != ["Phoenix · Artist", "Phoenix · Character"]:
                    raise AssertionError("Entity categories or canonical order differed")
                entity.results.itemClicked.emit(entity.results.item(1))
                character_id = entity.selected_id
                if not character_id:
                    raise AssertionError("Category-qualified entity has no stable identity")

                source = window.gallery_source_picker
                source.browse.click()
                _wait(app, lambda: not source._loading and source.results.count() == 2,
                      "catalog-only gallery source results")
                source_labels = [source.results.item(row).text() for row in range(2)]
                if source_labels != ["Amber", "Cobalt"]:
                    raise AssertionError("Gallery source catalog result differed")
                source.results.itemClicked.emit(source.results.item(0))
                amber_id = source.selected_id
                if not amber_id or window.source_box.currentData() is not None:
                    raise AssertionError("Gallery source picker changed the scan target")

                window.filter_box.setCurrentIndex(window.filter_box.findData("reviewed"))
                window.favorite_filter_box.setCurrentIndex(
                    window.favorite_filter_box.findData(FavoriteFilter.FAVORITES))
                previous = model._generation
                window.apply_filters_button.click()
                _wait(app, lambda: model._generation > previous and model._actionable and
                      model._query.tag_id == parent_id and
                      model._query.entity_id == character_id and
                      model._query.source_id == amber_id, "composed Apply publication")
                if labels() != ["alpha.png"] or window.gallery.currentIndex().isValid():
                    raise AssertionError("Composed Apply changed order or retained an action target")

                previous = model._generation
                window.clear_filters_button.click()
                _wait(app, lambda: model._generation > previous and model._actionable and
                      model._query == GalleryQuery(), "atomic Clear publication")
                if labels() != ["alpha.png", "bravo.jpg", "charlie.png"]:
                    raise AssertionError("Clear did not restore the complete library")

                source.set_choice(amber_id, "Amber")
                previous = model._generation
                window.apply_filters_button.click()
                _wait(app, lambda: model._generation > previous and model._actionable and
                      model._query.source_id == amber_id, "prior view before stale-ID refusal")
                prior = labels()
                if prior != ["alpha.png", "charlie.png"]:
                    raise AssertionError("Prior gallery source view differed")
                tag.set_choice("unallocated-smoke-tag", "Absent Topic")
                previous = model._generation
                window.apply_filters_button.click()
                _wait(app, lambda: model._generation > previous and model._actionable and
                      model._query.source_id == amber_id and model._query.tag_id is None and
                      "draft retained" in window.filter_feedback.text(),
                      "read-only absent-ID refusal and prior-view refresh")
                if (labels() != prior or tag.selected_id != "unallocated-smoke-tag" or
                        window.gallery.currentIndex().isValid() or source_attempts):
                    raise AssertionError("Absent-ID refusal broadened the view or touched a source")
    finally:
        window.close()
        _wait(app, lambda: window.catalog_client.gateway.close_complete and
              not window.isVisible(), "actual gateway and window close", seconds=15)
    return {"schema": "defiantmaple.gallery-filter-smoke.v1", "status": "passed",
            "bounded_first_page": 64, "bounded_more_page": 4,
            "composed_matches": 1, "clear_matches": 3, "prior_matches": 2,
            "stale_refused": True, "source_io_calls": 0, "close_complete": True}
