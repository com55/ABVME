import { useState, useMemo } from "react";
import type { Asset } from "../types";
import "./AssetTable.css";

interface Props {
  assets: Asset[];
  selectedIds: Set<string>;
  onSelectionChange: (ids: Set<string>) => void;
}

const COLUMNS = [
  { key: "name", label: "Name", flex: 3 },
  { key: "obj_type", label: "Type", flex: 1 },
  { key: "container", label: "Container", flex: 3 },
  { key: "source_path", label: "Source File", flex: 2 },
] as const;

export default function AssetTable({ assets, selectedIds, onSelectionChange }: Props) {
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<(typeof COLUMNS)[number]["key"]>("name");
  const [sortAsc, setSortAsc] = useState(true);

  const filtered = useMemo(() => {
    const q = filter.toLowerCase();
    const list = q
      ? assets.filter(
          (a) =>
            a.name.toLowerCase().includes(q) ||
            a.obj_type.toLowerCase().includes(q) ||
            a.container.toLowerCase().includes(q)
        )
      : assets;

    return [...list].sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortAsc ? cmp : -cmp;
    });
  }, [assets, filter, sortKey, sortAsc]);

  function toggleSort(key: (typeof COLUMNS)[number]["key"]) {
    if (key === sortKey) {
      setSortAsc((a) => !a);
    } else {
      setSortKey(key);
      setSortAsc(true);
    }
  }

  function handleRowClick(e: React.MouseEvent, id: string) {
    const next = new Set(selectedIds);
    if (e.ctrlKey || e.metaKey) {
      if (next.has(id)) next.delete(id);
      else next.add(id);
    } else if (e.shiftKey && selectedIds.size > 0) {
      const ids = filtered.map((a) => a.path_id);
      const last = [...selectedIds].at(-1)!;
      const from = ids.indexOf(last);
      const to = ids.indexOf(id);
      const [lo, hi] = from < to ? [from, to] : [to, from];
      ids.slice(lo, hi + 1).forEach((i) => next.add(i));
    } else {
      next.clear();
      next.add(id);
    }
    onSelectionChange(next);
  }

  function handleSelectAll() {
    if (selectedIds.size === filtered.length) {
      onSelectionChange(new Set());
    } else {
      onSelectionChange(new Set(filtered.map((a) => a.path_id)));
    }
  }

  const allSelected = filtered.length > 0 && filtered.every((a) => selectedIds.has(a.path_id));

  return (
    <div className="asset-table">
      <div className="table-toolbar">
        <input
          type="text"
          placeholder="Filter assets…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="filter-input"
        />
        <span className="count-badge">
          {selectedIds.size > 0 ? `${selectedIds.size} / ` : ""}
          {filtered.length} assets
        </span>
      </div>

      <div className="table-header">
        <div className="col-check">
          <input type="checkbox" checked={allSelected} onChange={handleSelectAll} />
        </div>
        {COLUMNS.map((col) => (
          <div
            key={col.key}
            className={`col-head ${sortKey === col.key ? "sorted" : ""}`}
            style={{ flex: col.flex }}
            onClick={() => toggleSort(col.key)}
          >
            {col.label}
            {sortKey === col.key && (
              <span className="sort-arrow">{sortAsc ? " ↑" : " ↓"}</span>
            )}
          </div>
        ))}
      </div>

      <div className="table-body">
        {filtered.length === 0 ? (
          <div className="empty-message">
            {assets.length === 0
              ? "Drop Unity bundle files here or click Load"
              : "No assets match the filter"}
          </div>
        ) : (
          filtered.map((asset) => (
            <div
              key={asset.path_id}
              className={`table-row ${selectedIds.has(asset.path_id) ? "selected" : ""} ${asset.is_changed ? "changed" : ""}`}
              onClick={(e) => handleRowClick(e, asset.path_id)}
            >
              <div className="col-check">
                <input
                  type="checkbox"
                  checked={selectedIds.has(asset.path_id)}
                  onChange={() => {}}
                  onClick={(e) => e.stopPropagation()}
                />
              </div>
              <div style={{ flex: 3 }} className="cell truncate" title={asset.name}>
                {asset.is_changed && <span className="changed-dot" title="Modified" />}
                {asset.name || "(unnamed)"}
              </div>
              <div style={{ flex: 1 }} className="cell type-badge">
                {asset.obj_type}
              </div>
              <div style={{ flex: 3 }} className="cell truncate" title={asset.container}>
                {asset.container}
              </div>
              <div
                style={{ flex: 2 }}
                className="cell truncate dim"
                title={asset.source_path}
              >
                {asset.source_path.split(/[/\\]/).at(-1)}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
