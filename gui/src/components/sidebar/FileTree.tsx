import { useState, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "@/api/client";
import { FileTreeItem } from "@/components/sidebar/FileTreeItem";
import { cn } from "@/lib/utils";
import type { FileNode } from "@/types";

interface Props {
  onFileSelect?: (node: FileNode) => void;
}

export function FileTree({ onFileSelect }: Props) {
  const [filterQuery, setFilterQuery] = useState("");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["filetree"],
    queryFn: async () => {
      try {
        return await api.getFileTree();
      } catch {
        throw new Error("文件树加载失败");
      }
    },
    staleTime: 30_000,
  });

  const tree = useMemo(() => data?.tree ?? [], [data]);

  const filteredTree = useMemo(() => {
    if (!filterQuery.trim()) return tree;
    const q = filterQuery.toLowerCase();
    return tree.filter((node) => {
      if (node.name.toLowerCase().includes(q)) return true;
      if (node.children?.some((c) => c.name.toLowerCase().includes(q))) return true;
      return false;
    });
  }, [tree, filterQuery]);

  const handleSelect = useCallback(
    (node: FileNode) => {
      setSelectedPath(node.path);
      onFileSelect?.(node);
    },
    [onFileSelect]
  );

  if (isLoading) {
    return (
      <div className="space-y-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="h-5 animate-pulse rounded bg-maref-surface-alt/50"
            style={{ marginLeft: `${(i % 3) * 12 + 8}px`, width: `${80 - i * 8}%` }}
          />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center gap-2 py-4">
        <p className="text-xs text-maref-danger">
          {error instanceof Error ? error.message : "加载失败"}
        </p>
        <button
          onClick={() => refetch()}
          className="rounded px-2 py-0.5 text-[10px] text-maref-accent hover:bg-maref-surface-alt transition-colors"
        >
          重试
        </button>
      </div>
    );
  }

  if (tree.length === 0) {
    return (
      <div className="py-2 text-center text-[11px] text-maref-text-muted">
        无文件
      </div>
    );
  }

  return (
    <div>
      <div className="relative mb-1 px-2">
        <Search className="absolute left-3.5 top-1/2 h-3 w-3 -translate-y-1/2 text-maref-text-muted" />
        <input
          value={filterQuery}
          onChange={(e) => setFilterQuery(e.target.value)}
          placeholder="搜索文件…"
          className={cn(
            "w-full rounded-md border border-maref-border bg-maref-surface-alt py-1 pl-6 pr-2",
            "text-[11px] text-maref-text placeholder-maref-text-muted outline-none",
            "focus:border-maref-accent/40 transition-colors"
          )}
        />
      </div>

      <div className="mt-1">
        {filteredTree.map((node) => (
          <FileTreeItem
            key={node.path}
            node={node}
            depth={0}
            selectedPath={selectedPath}
            onSelect={handleSelect}
            filterQuery={filterQuery}
          />
        ))}
        {filteredTree.length === 0 && (
          <div className="py-2 text-center text-[11px] text-maref-text-muted">
            无匹配文件
          </div>
        )}
      </div>
    </div>
  );
}
