import { useState, useEffect, useCallback } from "react";
import { Shield, Activity, Dna, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { CooldownDashboard } from "./CooldownDashboard";
import { GeneAuditTrail } from "./GeneAuditTrail";

async function fetchImmunitySummary(): Promise<{
  total_agents: number;
  cooling: number;
  blocked: number;
  merged: number;
  gene_count: number;
  critical_genes: number;
}> {
  try {
    const [summaryRes, geneRes] = await Promise.all([
      fetch("/api/immunity/cooldown/summary"),
      fetch("/api/immunity/genes"),
    ]);
    const summary = summaryRes.ok ? await summaryRes.json() : {};
    const geneData = geneRes.ok ? await geneRes.json() : { genes: [] };
    return {
      total_agents: summary.total_agents ?? 0,
      cooling: summary.cooling ?? 0,
      blocked: summary.blocked ?? 0,
      merged: summary.merged ?? 0,
      gene_count: (geneData.genes ?? []).length,
      critical_genes: (geneData.genes ?? []).filter((g: { risk_level: string }) => g.risk_level === "critical").length,
    };
  } catch {
    return { total_agents: 0, cooling: 0, blocked: 0, merged: 0, gene_count: 0, critical_genes: 0 };
  }
}

export function ImmunityDashboard() {
  const [summary, setSummary] = useState({
    total_agents: 0,
    cooling: 0,
    blocked: 0,
    merged: 0,
    gene_count: 0,
    critical_genes: 0,
  });

  const loadSummary = useCallback(async () => {
    const data = await fetchImmunitySummary();
    setSummary(data);
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const statCards = [
    { icon: Activity, label: "冷却中 Agent", value: summary.cooling, color: "bg-maref-info/20 text-maref-info" },
    { icon: AlertTriangle, label: "已阻止", value: summary.blocked, color: "bg-maref-danger/20 text-maref-danger" },
    { icon: Dna, label: "已注册基因", value: summary.gene_count, color: "bg-maref-accent/20 text-maref-accent" },
    { icon: Shield, label: "严重基因", value: summary.critical_genes, color: "bg-maref-warning/20 text-maref-warning" },
  ];

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <Shield className="h-4 w-4 text-maref-accent" />
          免疫看板
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          Agent 冷却隔离 · 基因审计 · 污染防护
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        <div className="grid grid-cols-4 gap-3">
          {statCards.map((card) => (
            <div key={card.label} className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3">
              <div className={cn("rounded-lg p-2", card.color.split(" ")[0])}>
                <card.icon className={cn("h-4 w-4", card.color.split(" ")[1])} />
              </div>
              <div>
                <div className="text-[11px] text-maref-text-muted">{card.label}</div>
                <div className="text-sm font-semibold text-maref-text">{card.value}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <Activity className="h-3.5 w-3.5" />
              冷却隔离
            </h3>
            <CooldownDashboard />
          </section>

          <section>
            <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
              <Dna className="h-3.5 w-3.5" />
              基因审计
            </h3>
            <GeneAuditTrail />
          </section>
        </div>
      </div>
    </div>
  );
}
