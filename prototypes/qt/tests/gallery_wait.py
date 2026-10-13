"""Bounded Qt waits for the async gallery integration tests."""
from __future__ import annotations

import json
import math
import shutil

from PySide6.QtCore import QEventLoop, QTimer


DEFAULT_TIMEOUT_MS = 5_000


def _detail_value(window):
    try:
        value = json.loads(window.detail.toPlainText())
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _snapshot(window):
    model = window.model
    gateway = window.catalog_client.gateway
    index = window.gallery.currentIndex()
    asset = model.loaded_asset_at(index.row()) if index.isValid() else None
    detail = window.detail.toPlainText()
    return (
        f"generation={model._generation}, count={model.rowCount()}, "
        f"actionable={model._actionable}, token={'set' if model._token is not None else 'none'}, "
        f"cached_pages={tuple(model._cache)}, current_row={index.row() if index.isValid() else None}, "
        f"current_asset={asset.get('asset_id') if asset else None}, "
        f"pending_pages={tuple(model._pending_pages)}, failed_pages={dict(model._failed_pages)}, "
        f"filter_error={model.last_filter_error!r}, "
        f"mutation_pending={window._mutation_pending}, gateway_running={gateway.isRunning()}, "
        f"gateway_close_complete={gateway.close_complete}, detail={detail[:180]!r}"
    )


def _signals(value):
    return tuple(value) if isinstance(value, (tuple, list)) else (value,)


def _wait(signal, predicate, *, description, window, timeout_ms=DEFAULT_TIMEOUT_MS,
          start=None):
    """Wait for a named state change while pumping Qt events, with a hard bound."""
    if predicate():
        return
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    signals = _signals(signal)
    for item in signals:
        item.connect(loop.quit)
    timeout.timeout.connect(loop.quit)
    timeout.start(timeout_ms)
    try:
        # Recheck after connecting so a state transition between the first
        # check and connection cannot be lost.
        while not predicate() and timeout.isActive():
            if start is not None:
                begin, start = start, None
                begin()
                if predicate():
                    break
            loop.exec()
    finally:
        for item in signals:
            item.disconnect(loop.quit)
        timeout.stop()
    if not predicate():
        raise AssertionError(
            f"Timed out waiting for {description} within {timeout_ms} ms; "
            f"current state: {_snapshot(window)}"
        )


def wait_for_initial_generation(window, *, expected_count=None,
                                timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model

    def count_ready():
        return (model.rowCount() == expected_count if expected_count is not None
                else model.rowCount() >= 6)

    _wait(
        model.generationPublished,
        lambda: (model._actionable and model._token is not None
                 and model._token.generation == model._generation and count_ready()
                 and (model.rowCount() == 0 or 0 in model._cache)
                 and (model.rowCount() == 0 or model.loaded_asset_at(0) is not None)),
        description=("initial published count/page 0" if expected_count is None else
                     f"initial published count {expected_count} and page 0"),
        window=window,
        timeout_ms=timeout_ms,
    )


def wait_for_generation_after(window, previous_generation, *, expected_count=None,
                              description="refreshed gallery generation",
                              timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model

    def count_ready():
        return expected_count is None or model.rowCount() == expected_count

    _wait(
        model.generationPublished,
        lambda: (model._generation > previous_generation and model._actionable
                 and model._token is not None
                 and model._token.generation == model._generation and count_ready()
                 and (model.rowCount() == 0 or 0 in model._cache)),
        description=description,
        window=window,
        timeout_ms=timeout_ms,
    )
    return model._generation


def wait_for_page(window, page, *, generation, timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model
    _wait(
        (model.pagePublished, model.loadFailed),
        lambda: (model._generation == generation and model._actionable
                 and page in model._cache),
        description=f"page {page} in generation {generation}",
        window=window,
        timeout_ms=timeout_ms,
        start=lambda: model.request_page(page),
    )


def wait_for_asset_at(window, row, asset_id, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model
    generation = model._generation

    def matches():
        page = row // model.page_size
        cached = model._cache.get(page)
        offset = row % model.page_size
        asset = cached[offset] if cached is not None and offset < len(cached) else None
        return (model._generation == generation and model._actionable
                and asset is not None and asset.get("asset_id") == asset_id)

    _wait(
        (model.pagePublished, model.loadFailed, model.generationPublished),
        matches,
        description=f"loaded row {row} for captured asset {asset_id}",
        window=window,
        timeout_ms=timeout_ms,
        start=lambda: model.request_page(row // model.page_size),
    )
    return model.loaded_asset_at(row)


def wait_for_all_asset_ids(window, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model
    generation = model._generation
    count = model.rowCount()
    for page in range(math.ceil(count / model.page_size)):
        wait_for_page(window, page, generation=generation, timeout_ms=timeout_ms)
    return [model.loaded_asset_at(row)["asset_id"] for row in range(count)]


def wait_for_rank(window, asset_id, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model
    generation, token = model._generation, model._token
    result = []
    errors = []
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)

    def received(row, error):
        try:
            result.append((row, error))
        except BaseException as exc:  # surface callback errors as test failures
            errors.append(exc)
        finally:
            loop.quit()

    timeout.timeout.connect(loop.quit)
    timeout.start(timeout_ms)
    try:
        model.request_rank(asset_id, received)
        while not result and not errors and timeout.isActive():
            loop.exec()
    finally:
        timeout.stop()
    if errors:
        raise AssertionError(f"Rank callback for {asset_id} raised: {errors[0]!r}") from errors[0]
    if not result:
        raise AssertionError(
            f"Timed out waiting for rank of captured asset {asset_id} within {timeout_ms} ms; "
            f"current state: {_snapshot(window)}"
        )
    row, error = result[0]
    if error or row is None:
        raise AssertionError(f"Rank for captured asset {asset_id} was refused: {error!r}")
    if model._generation != generation or model._token != token:
        raise AssertionError(
            f"Rank for captured asset {asset_id} completed after its generation changed; "
            f"current state: {_snapshot(window)}"
        )
    return row


def wait_for_gateway_condition(window, predicate, *, description,
                               timeout_ms=DEFAULT_TIMEOUT_MS, signals=None):
    gateway = window.catalog_client.gateway
    signals = signals or (gateway.completed, window.model.generationPublished,
                          window.model.pagePublished)
    _wait(
        signals,
        predicate,
        description=description,
        window=window,
        timeout_ms=timeout_ms,
    )


def wait_for_startup_validation(window, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    wait_for_gateway_condition(
        window,
        lambda: bool(getattr(window, "_startup_validated", False)),
        description="legacy startup containment validation",
        timeout_ms=timeout_ms,
    )


def wait_for_selected_asset(window, asset_id, *, row=None,
                            timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model

    def matches():
        index = window.gallery.currentIndex()
        if not index.isValid() or (row is not None and index.row() != row):
            return False
        asset = model.loaded_asset_at(index.row())
        return asset is not None and asset.get("asset_id") == asset_id

    wait_for_gateway_condition(
        window,
        matches,
        description=f"current gallery selection for captured asset {asset_id}",
        timeout_ms=timeout_ms,
        signals=(model.pagePublished, model.generationPublished,
                 window.catalog_client.gateway.completed),
    )
    wait_for_detail(window, asset_id, timeout_ms=timeout_ms)


def wait_for_collection_record(window, collection_id=None, *, current=True,
                               timeout_ms=DEFAULT_TIMEOUT_MS):
    wait_for_gateway_condition(
        window,
        lambda: (window.collection_box.findData(collection_id) >= 0
                 and (not current or window.collection_box.currentData() == collection_id)),
        description=(f"collection-list publication and current selection {collection_id!r}"
                     if current else f"collection-list choice {collection_id!r}"),
        timeout_ms=timeout_ms,
        signals=(window.catalog_client.gateway.completed,
                 window.model.generationPublished),
    )


def close_windows_and_cleanup(windows, app, directory, *, verify=None,
                              timeout_ms=DEFAULT_TIMEOUT_MS):
    """Close every gateway first; preserve its fixture if any close is incomplete."""
    for window in reversed(windows):
        close_window_and_wait(window, app, timeout_ms=timeout_ms)
    if verify is not None:
        verify()
    shutil.rmtree(directory)


def wait_for_detail(window, asset_id, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    def matches():
        value = _detail_value(window)
        asset = value.get("asset") if value else None
        return isinstance(asset, dict) and asset.get("asset_id") == asset_id

    _wait(
        window.detail.document().contentsChanged,
        matches,
        description=f"detail for captured asset {asset_id}",
        window=window,
        timeout_ms=timeout_ms,
    )


def wait_for_review_write(window, *, row, asset_id, previous_generation,
                          state, timeout_ms=DEFAULT_TIMEOUT_MS):
    model = window.model

    def matches():
        asset = model.loaded_asset_at(row)
        return (model._generation > previous_generation and model._actionable
                and not window._mutation_pending and model._token is not None
                and asset is not None and asset.get("asset_id") == asset_id
                and asset.get("workflow_state") == state)

    _wait(
        model.generationPublished,
        matches,
        description=(f"review write for captured asset {asset_id}, fresh generation, "
                     f"and state {state!r}"),
        window=window,
        timeout_ms=timeout_ms,
    )


def close_window_and_wait(window, app, *, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Request close and keep pumping until the worker has actually finished."""
    gateway = window.catalog_client.gateway
    finished = False
    loop = QEventLoop()
    timeout = QTimer()
    timeout.setSingleShot(True)
    gateway.finished.connect(loop.quit)
    timeout.timeout.connect(loop.quit)
    try:
        window.close()
        timeout.start(timeout_ms)
        while not gateway.close_complete and timeout.isActive():
            loop.exec()
            app.processEvents()
        if gateway.close_complete:
            finished = True
        if not finished:
            raise AssertionError(
                f"Timed out waiting for actual catalog gateway close within {timeout_ms} ms; "
                f"current state: {_snapshot(window)}"
            )
        if window.isVisible():
            # closeEvent retries after the gateway's finished signal.
            window.close()
            app.processEvents()
        if window.isVisible():
            raise AssertionError(
                f"Catalog gateway finished but window remains visible; {_snapshot(window)}"
            )
    finally:
        gateway.finished.disconnect(loop.quit)
        timeout.stop()
