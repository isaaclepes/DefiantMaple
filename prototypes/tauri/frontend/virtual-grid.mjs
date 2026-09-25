export function gridGeometry(width, height, cellSize, gap = 8, overscanRows = 2) {
  const columnWidth = cellSize + gap;
  const rowHeight = cellSize + 58 + gap;
  const columns = Math.max(1, Math.floor(Math.max(1, width - gap) / columnWidth));
  const visibleRows = Math.max(1, Math.ceil(height / rowHeight));
  return { columns, rowHeight, visibleRows, overscanRows };
}

export function visibleRange(scrollTop, count, geometry) {
  const { columns, rowHeight, visibleRows, overscanRows } = geometry;
  const firstRow = Math.max(0, Math.floor(scrollTop / rowHeight) - overscanRows);
  const start = Math.min(count, firstRow * columns);
  const limit = Math.max(1, (visibleRows + overscanRows * 2) * columns);
  return {
    start,
    limit: Math.min(limit, Math.max(0, count - start)),
    translateY: firstRow * rowHeight,
    totalHeight: Math.ceil(count / columns) * rowHeight,
  };
}

export function moveIndex(index, key, columns, count) {
  const deltas = {
    ArrowLeft: -1,
    ArrowRight: 1,
    ArrowUp: -columns,
    ArrowDown: columns,
    Home: -count,
    End: count,
  };
  if (!(key in deltas) || count === 0) return index;
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return Math.max(0, Math.min(count - 1, index + deltas[key]));
}
