import { useState, useEffect, useCallback, useRef } from "react";
import { Dna, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";
import type { GeneEntry } from "@/types";

type SortField = "cwe" | "risk_level" | "severity" | "occurrences" | "last_seen";
type SortDir = "asc" | "desc";

const RISK_COLORS: Record<string, string> = {
  low: "bg-maref-success/10 text-maref-success",
  medium: "bg-maref-warning/10 text-maref-warning",
  high: "bg-maref-danger/10 text-maref-danger",
  critical: "bg-maref-danger/20 text-maref-danger font-bold",
};

const RISK_LABELS: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "严重",
};

function SortableHeader({
  field,
  sortField,
  onSort,
  children,
}: {
  field: SortField;
  sortField: SortField;
  onSort: (field: SortField) => void;
  children: string;
}) {
  const isActive = sortField === field;
  return (
    <th
      className="px-4 py-2.5 text-left font-medium text-maref-text-muted cursor-pointer select-none hover:text-maref-text transition-colors"
      onClick={() => onSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        <ArrowUpDown className={cn("h-3 w-3", isActive ? "text-maref-accent" : "opacity-30")} />
      </span>
    </th>
  );
}

export function GeneAuditTrail() {
  const [genes, setGenes] = useState<GeneEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortField, setSortField] = useState<SortField>("last_seen");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const loadedRef = useRef(false);

  const loadGenes = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.getImmunityGenes();
      setGenes((data.genes ?? []) as GeneEntry[]);
    } catch {
      setGenes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!loadedRef.current) {
      loadedRef.current = true;
      loadGenes();
    }
  }, [loadGenes]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sortedGenes = [...genes].sort((a, b) => {
    const dir = sortDir === "asc" ? 1 : -1;
    if (sortField === "cwe") return a.cwe.localeCompare(b.cwe) * dir;
    if (sortField === "risk_level") return a.risk_level.localeCompare(b.risk_level) * dir;
    if (sortField === "severity") return (a.severity - b.severity) * dir;
    if (sortField === "occurrences") return (a.occurrences - b.occurrences) * dir;
    return (new Date(a.last_seen).getTime() - new Date(b.last_seen).getTime()) * dir;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Dna className="h-6 w-6 animate-pulse text-maref-accent" />
        <span className="ml-2 text-maref-text-muted">加载免疫基因数据...</span>
      </div>
    );
  }

  if (genes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-maref-text-muted">
        <Dna className="h-10 w-10 mb-2 opacity-50" />
        <p>暂无免疫基因记录</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-maref-border/50">
            <SortableHeader field="cwe" sortField={sortField} onSort={handleSort}>CWE</SortableHeader>
            <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">风险等级</th>
            <SortableHeader field="severity" sortField={sortField} onSort={handleSort}>严重程度</SortableHeader>
            <SortableHeader field="occurrences" sortField={sortField} onSort={handleSort}>出现次数</SortableHeader>
            <SortableHeader field="last_seen" sortField={sortField} onSort={handleSort}>最后出现</SortableHeader>
          </tr>
        </thead>
        <tbody>
          {sortedGenes.map((gene, idx) => (
            <tr key={idx} className="border-b border-maref-border/20 hover:bg-maref-surface/50 transition-colors">
              <td className="px-4 py-2.5 font-mono text-maref-accent">{gene.cwe}</td>
              <td className="px-4 py-2.5">
                <span className={cn("inline-block px-2 py-0.5 rounded text-xs", RISK_COLORS[gene.risk_level] ?? "")}>
                  {RISK_LABELS[gene.risk_level] ?? gene.risk_level}
                </span>
              </td>
              <td className="px-4 py-2.5">{gene.severity}</td>
              <td className="px-4 py-2.5">{gene.occurrences}</td>
              <td className="px-4 py-2.5 text-maref-text-muted">{new Date(gene.last_seen).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}