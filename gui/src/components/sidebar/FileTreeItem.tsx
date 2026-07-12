import { useState } from "react";
import {
  Folder,
  FolderOpen,
  File,
  ChevronRight,
  ChevronDown,
  FileCode,
  FileJson,
  FileText,
  FileType,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileNode } from "@/types";

interface Props {
  node: FileNode;
  depth: number;
  selectedPath: string | null;
  onSelect: (node: FileNode) => void;
  filterQuery?: string;
}

const EXTENSION_ICONS: Record<string, React.ElementType> = {
  ".tsx": FileCode,
  ".ts": FileCode,
  ".jsx": FileCode,
  ".js": FileCode,
  ".py": FileCode,
  ".json": FileJson,
  ".md": FileText,
  ".css": FileType,
  ".html": FileCode,
  ".toml": FileJson,
  ".yaml": FileJson,
  ".yml": FileJson,
};

function matchesFilter(node: FileNode, query: string): boolean {
  const q = query.toLowerCase();
  if (node.name.toLowerCase().includes(q)) return true;
  if (node.children) {
    return node.children.some((child) => matchesFilter(child, q));
  }
  return false;
}

export function FileTreeItem({
  node,
  depth,
  selectedPath,
  onSelect,
  filterQuery = "",
}: Props) {
  const [expanded, setExpanded] = useState(depth < 1);
  const isDirectory = node.type === "directory";
  const isSelected = selectedPath === node.path;
  const isFiltered = filterQuery && !matchesFilter(node, filterQuery);

  if (isFiltered && isDirectory && !node.children?.some((c) => matchesFilter(c, filterQuery))) {
    return null;
  }

  if (isDirectory && !isFiltered && !expanded && node.children?.some((c) => matchesFilter(c, filterQuery))) {
    // expand when filter matches children
  }

  const handleClick = () => {
    if (isDirectory) {
      setExpanded((prev) => !prev);
    } else {
      onSelect(node);
    }
  };

  const extension = isDirectory ? undefined : node.name.split(".").pop();
  const IconComponent = extension && EXTENSION_ICONS[`.${extension}`] ? EXTENSION_ICONS[`.${extension}`] : File;

  return (
    <div
      className={cn(
        "flex items-center gap-1 px-2 py-1 cursor-pointer rounded-md text-sm transition-colors",
        isSelected
          ? "bg-accent text-accent-foreground"
          : "hover:bg-accent/50 text-foreground",
        isFiltered && "opacity-40"
      )}
      style={{ paddingLeft: `${depth * 16 + 8}px` }}
      onClick={handleClick}
      role="treeitem"
      aria-expanded={isDirectory ? expanded : undefined}
      aria-selected={isSelected}
    >
      {isDirectory ? (
        <>
          <span className="w-4 h-4 flex items-center justify-center">
            {expanded ? (
              <ChevronDown className="w-3.5 h-3.5" />
            ) : (
              <ChevronRight className="w-3.5 h-3.5" />
            )}
          </span>
          {expanded ? (
            <FolderOpen className="w-4 h-4 text-blue-500" />
          ) : (
            <Folder className="w-4 h-4 text-blue-500" />
          )}
        </>
      ) : (
        <>
          <span className="w-4 h-4" />
          <IconComponent className="w-4 h-4 text-muted-foreground" />
        </>
      )}
      <span className="truncate">{node.name}</span>
    </div>
  );
}