import { useCallback } from "react";
import type { FilterState, SortOption } from "../hooks/useNotes";

interface Props {
  sources: string[];
  activeSource: string;
  onSourceChange: (source: string) => void;
  activeStatus: "active" | "done" | "all";
  onStatusChange: (status: "active" | "done" | "all") => void;
  searchText: string;
  onSearchChange: (text: string) => void;
  sortField: "timestamp" | "source";
  sortOrder: "asc" | "desc";
  onSortChange: (field: "timestamp" | "source", order: "asc" | "desc") => void;
}

export function FilterBar({
  sources,
  activeSource,
  onSourceChange,
  activeStatus,
  onStatusChange,
  searchText,
  onSearchChange,
  sortField,
  sortOrder,
  onSortChange,
}: Props) {
  // Debounced search input
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onSearchChange(e.target.value);
    },
    [onSearchChange],
  );

  const handleSortClick = useCallback(
    (field: "timestamp" | "source", order: "asc" | "desc") => {
      onSortChange(field, order);
    },
    [onSortChange],
  );

  if (sources.length <= 1) return null;

  const all = ["all", ...sources];

  return (
    <div className="filters">
      {/* Source filters */}
      <div className="filter-group">
        {all.map((src) => (
          <button
            key={src}
            className={`filter-btn${activeSource === src ? " active" : ""}`}
            onClick={() => onSourceChange(src)}
          >
            {src}
          </button>
        ))}
      </div>

      {/* Status filters */}
      <div className="filter-group">
        <button
          className={`filter-btn${activeStatus === "active" ? " active" : ""}`}
          onClick={() => onStatusChange("active")}
        >
          Active
        </button>
        <button
          className={`filter-btn${activeStatus === "done" ? " active" : ""}`}
          onClick={() => onStatusChange("done")}
        >
          Done
        </button>
        <button
          className={`filter-btn${activeStatus === "all" ? " active" : ""}`}
          onClick={() => onStatusChange("all")}
        >
          All
        </button>
      </div>

      {/* Search input */}
      <div className="filter-group">
        <input
          type="text"
          className="filter-search"
          placeholder="Search notes..."
          value={searchText}
          onChange={handleSearchChange}
        />
      </div>

      {/* Sort options */}
      <div className="filter-group">
        <button
          className={`filter-btn${sortField === "timestamp" && sortOrder === "desc" ? " active" : ""}`}
          onClick={() => handleSortClick("timestamp", "desc")}
        >
          Newest
        </button>
        <button
          className={`filter-btn${sortField === "timestamp" && sortOrder === "asc" ? " active" : ""}`}
          onClick={() => handleSortClick("timestamp", "asc")}
        >
          Oldest
        </button>
        <button
          className={`filter-btn${sortField === "source" ? " active" : ""}`}
          onClick={() => handleSortClick("source", "asc")}
        >
          By Source
        </button>
      </div>
    </div>
  );
}
