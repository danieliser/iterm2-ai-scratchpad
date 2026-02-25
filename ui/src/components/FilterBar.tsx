import { useCallback } from "react";
import { AnimatePresence, motion } from "motion/react";

interface Props {
  visible: boolean;
  sources: string[];
  activeSource: string;
  onSourceChange: (source: string) => void;
  searchText: string;
  onSearchChange: (text: string) => void;
  sortField: "timestamp" | "source";
  sortOrder: "asc" | "desc";
  onSortChange: (field: "timestamp" | "source", order: "asc" | "desc") => void;
}

export function FilterBar({
  visible,
  sources,
  activeSource,
  onSourceChange,
  searchText,
  onSearchChange,
  sortField,
  sortOrder,
  onSortChange,
}: Props) {
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      onSearchChange(e.target.value);
    },
    [onSearchChange],
  );

  const sortValue =
    sortField === "source"
      ? "source"
      : sortOrder === "asc"
        ? "oldest"
        : "newest";

  const handleSortChange = useCallback(
    (e: React.ChangeEvent<HTMLSelectElement>) => {
      const v = e.target.value;
      if (v === "newest") onSortChange("timestamp", "desc");
      else if (v === "oldest") onSortChange("timestamp", "asc");
      else if (v === "source") onSortChange("source", "asc");
    },
    [onSortChange],
  );

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="filters"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          style={{ overflow: "hidden" }}
        >
          <input
            type="text"
            className="filter-search"
            placeholder="Search..."
            value={searchText}
            onChange={handleSearchChange}
          />
          {sources.length > 1 && (
            <select
              className="filter-select"
              value={activeSource}
              onChange={(e) => onSourceChange(e.target.value)}
            >
              <option value="all">All sources</option>
              {sources.map((src) => (
                <option key={src} value={src}>
                  {src}
                </option>
              ))}
            </select>
          )}
          <select
            className="filter-select"
            value={sortValue}
            onChange={handleSortChange}
          >
            <option value="newest">Newest</option>
            <option value="oldest">Oldest</option>
            <option value="source">By source</option>
          </select>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
