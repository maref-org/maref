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

function getFileIcon(extension?: string) {
  if (extension && EXTENSION_ICONS[extension]) {
    return EXTENSION_ICONS[extension];
  }
  return File;
}

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

  const IconComponent = isDirectory
    ? (expanded ? FolderOpen : Folder)
    : getFileIcon(node.extension);

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          "flex w-full items-center gap-1.5 py-1 text-xs transition-colors rounded-sm",
          isSelected
            ? "bg-maref-accent/20 text-maref-accent"
            : "text-maref-text-muted hover:bg-maref-surface-alt/50 hover:text-maref-text",
          isFiltered && "opacity-30"
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px`, paddingRight: "8px" }}
      >
        {isDirectory && (
          <span className="flex-shrink-0">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
        <IconComponent className="h-3.5 w-3.5 flex-shrink-0 text-maref-info" />
        <span className="truncate">{node.name}</span>
      </button>

      {isDirectory && expanded && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeItem
              key={child.path}
              node={child}
              depth={depth + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              filterQuery={filterQuery}
            />
          ))}
        </div>
      )}
    </div>
  );
}
