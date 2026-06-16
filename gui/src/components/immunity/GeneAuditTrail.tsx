import { useState, useEffect, useCallback } from "react";
import { Dna, ArrowUpDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface GeneEntry {
  id: string;
  source: string;
  cwe: string;
  risk_level: "low" | "medium" | "high" | "critical";
  severity: number;
  occurrences: number;
  first_seen: string;
  last_seen: string;
  description: string;
}

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

async function fetchGenes(): Promise<{ genes: GeneEntry[] }> {
  const res = await fetch("/api/immunity/genes");
  if (!res.ok) return { genes: [] };
  return res.json();
}

function SortableHeader({
  field,
  sortField,
  sortDir,
  onSort,
  children,
}: {
  field: SortField;
  sortField: SortField;
  sortDir: SortDir;
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

  const loadGenes = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchGenes();
      setGenes(data.genes ?? []);
    } catch {
      setGenes([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadGenes();
  }, [loadGenes]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const sorted = [...genes].sort((a, b) => {
    const cmp = sortField === "risk_level"
      ? ["low", "medium", "high", "critical"].indexOf(a.risk_level) - ["low", "medium", "high", "critical"].indexOf(b.risk_level)
      : String(a[sortField]).localeCompare(String(b[sortField]));
    return sortDir === "asc" ? cmp : -cmp;
  });

  if (!loading && genes.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center py-16">
        <Dna className="h-10 w-10 text-maref-text-muted mb-3" />
        <p className="text-sm text-maref-text-muted">Gene bank not yet connected</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-lg border border-maref-border">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-maref-border bg-maref-surface-alt">
              <SortableHeader field="cwe" sortField={sortField} sortDir={sortDir} onSort={handleSort}>CWE</SortableHeader>
              <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">来源</th>
              <SortableHeader field="risk_level" sortField={sortField} sortDir={sortDir} onSort={handleSort}>风险</SortableHeader>
              <SortableHeader field="severity" sortField={sortField} sortDir={sortDir} onSort={handleSort}>严重度</SortableHeader>
              <SortableHeader field="occurrences" sortField={sortField} sortDir={sortDir} onSort={handleSort}>出现次数</SortableHeader>
              <SortableHeader field="last_seen" sortField={sortField} sortDir={sortDir} onSort={handleSort}>最近</SortableHeader>
              <th className="px-4 py-2.5 text-left font-medium text-maref-text-muted">描述</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-maref-text-muted text-xs">
                  加载中...
                </td>
              </tr>
            )}
            {sorted.map((gene) => (
              <tr key={gene.id} className="border-b border-maref-border last:border-0 hover:bg-maref-surface-alt/30">
                <td className="px-4 py-2 font-mono text-[11px] text-maref-text">{gene.cwe}</td>
                <td className="px-4 py-2 text-maref-text-muted">{gene.source}</td>
                <td className="px-4 py-2">
                  <span className={cn("rounded px-1.5 py-0.5 text-[10px]", RISK_COLORS[gene.risk_level])}>
                    {RISK_LABELS[gene.risk_level]}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-12 rounded-full bg-maref-border overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full",
                          gene.severity > 7 ? "bg-maref-danger" :
                          gene.severity > 4 ? "bg-maref-warning" :
                          "bg-maref-success"
                        )}
                        style={{ width: `${(gene.severity / 10) * 100}%` }}
                      />
                    </div>
                    <span className="font-mono text-maref-text-muted">{gene.severity}/10</span>
                  </div>
                </td>
                <td className="px-4 py-2">
                  <span className="font-mono text-maref-text">{gene.occurrences}</span>
                </td>
                <td className="px-4 py-2 text-maref-text-muted whitespace-nowrap">
                  {gene.last_seen}
                </td>
                <td className="px-4 py-2 text-maref-text-muted max-w-[200px] truncate">
                  {gene.description}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
