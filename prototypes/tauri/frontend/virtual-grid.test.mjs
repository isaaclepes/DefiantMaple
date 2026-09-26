import assert from "node:assert/strict";
import test from "node:test";
import { gridGeometry, moveIndex, visibleRange } from "./virtual-grid.mjs";

test("visible range stays bounded for a 100k catalog", () => {
  const geometry = gridGeometry(1_000, 700, 144);
  const range = visibleRange(2_000_000, 100_000, geometry);
  assert.ok(geometry.columns > 1);
  assert.ok(range.start >= 0);
  assert.ok(range.start + range.limit <= 100_000);
  assert.ok(range.limit < 200);
  assert.ok(range.totalHeight > 2_000_000);
});

test("keyboard movement clamps to the catalog", () => {
  assert.equal(moveIndex(0, "ArrowLeft", 5, 100), 0);
  assert.equal(moveIndex(5, "ArrowDown", 5, 100), 10);
  assert.equal(moveIndex(98, "ArrowRight", 5, 100), 99);
  assert.equal(moveIndex(40, "Home", 5, 100), 0);
  assert.equal(moveIndex(40, "End", 5, 100), 99);
});
