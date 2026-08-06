import { useState, useEffect, useCallback } from "react";
import {
  Network,
  Activity,
  ShieldCheck,
  Scale,
  Star,
  Users,
  FileText,
  Coins,
  GitMerge,
  CircleDollarSign,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { api } from "@/api/client";
import type { FederatedPlatformSummary } from "@/types";

const EMPTY: FederatedPlatformSummary = {
  gateway: { agent_count: 0, identity_mapping_count: 0, protocols: {} },
  discovery: { server_id: "", local_agent_count: 0, peer_count: 0, healthy_peers: 0, max_depth: 0 },
  catalog: { entry_count: 0, capability_count: 0, protocol_count: 0, organization_count: 0, active_subscriptions: 0 },
  trust: { local_agent_count: 0, agents_with_peer_reports: 0, total_peer_reports: 0 },
  policy: { conflict_strategy: "", federation_rules: 0, local_rules: 0, adhoc_rules: 0, total_rules: 0 },
  hitl: { total_requests: 0, status_counts: {}, total_orgs: 0, pending_count: 0 },
  marketplace: { total_listings: 0, active_listings: 0, total_reviews: 0, total_capabilities: 0, total_organizations: 0, average_price: 0, priced_listings: 0, free_listings: 0 },
  metering: { total_metrics: 0, total_tasks: 0, total_orgs: 0, orgs: [] },
  settlement: { total_billing_entries: 0, total_proposals: 0, status_counts: {}, total_outstanding: 0, total_settled: 0, ledger_entries: 0, pricing: {} },
};

interface TopologyNode {
  id: string;
  label: string;
  value: number;
  unit: string;
}

const NODE_ICONS: Record<string, React.ElementType> = {
  gateway: Users,
  discovery: Network,
  catalog: FileText,
  trust: ShieldCheck,
  policy: Scale,
  hitl: Star,
  marketplace: Coins,
  metering: Activity,
  settlement: CircleDollarSign,
};

function TopologyMap({ nodes }: { nodes: TopologyNode[] }) {
  const cx = 300;
  const cy = 180;
  const radius = 150;
  const labels: React.ReactNode[] = [];
  const links: React.ReactNode[] = [];

  nodes.forEach((node, i) => {
    const angle = (i / nodes.length) * Math.PI * 2 - Math.PI / 2;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    const Icon = NODE_ICONS[node.id] ?? Activity;
    const active = node.value > 0;
    links.push(
      <line
        key={`link-${node.id}`}
        x1={cx}
        y1={cy}
        x2={x}
        y2={y}
        className={active ? "stroke-maref-accent" : "stroke-maref-border"}
        strokeOpacity={active ? 0.6 : 0.35}
        strokeWidth={1.5}
      />
    );
    labels.push(
      <g key={node.id} transform={`translate(${x}, ${y})`}>
        <circle
          r={26}
          className={active ? "fill-maref-surface-alt" : "fill-maref-surface"}
          stroke="currentColor"
          strokeOpacity={active ? 0.7 : 0.25}
          strokeWidth={1.5}
        />
        <Icon
          className={cn("h-4 w-4", active ? "text-maref-accent" : "text-maref-text-muted")}
          style={{ transform: "translate(-8px, -8px)" }}
        />
        <text
          textAnchor="middle"
          dy={-32}
          className="fill-maref-text text-[11px] font-medium"
        >
          {node.label}
        </text>
        <text
          textAnchor="middle"
          dy={40}
          className={cn(
            "text-[11px] font-semibold",
            active ? "fill-maref-accent" : "fill-maref-text-muted"
          )}
        >
          {node.value} {node.unit}
        </text>
      </g>
    );
  });

  return (
    <svg viewBox="0 0 600 360" className="h-full w-full">
      {links}
      <g transform={`translate(${cx}, ${cy})`}>
        <circle r={40} className="fill-maref-accent/15 stroke-maref-accent" strokeOpacity={0.5} strokeWidth={2} />
        <Network className="h-5 w-5 text-maref-accent" style={{ transform: "translate(-10px, -10px)" }} />
        <text textAnchor="middle" dy={34} className="fill-maref-text text-xs font-semibold">
          联邦平台
        </text>
      </g>
      {labels}
    </svg>
  );
}

export function FederationView() {
  const [summary, setSummary] = useState<FederatedPlatformSummary>(EMPTY);

  const loadSummary = useCallback(async () => {
    try {
      const data = await api.getFederatedPlatformSummary();
      setSummary(data);
    } catch {
      setSummary(EMPTY);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadSummary();
  }, [loadSummary]);

  const nodes: TopologyNode[] = [
    { id: "gateway", label: "网关", value: summary.gateway.agent_count, unit: "Agents" },
    { id: "discovery", label: "发现", value: summary.discovery.peer_count, unit: "Peers" },
    { id: "catalog", label: "目录", value: summary.catalog.entry_count, unit: "条目" },
    { id: "trust", label: "信任", value: summary.trust.total_peer_reports, unit: "报告" },
    { id: "policy", label: "策略", value: summary.policy.total_rules, unit: "规则" },
    { id: "hitl", label: "HITL", value: summary.hitl.pending_count, unit: "待审" },
    { id: "marketplace", label: "市场", value: summary.marketplace.active_listings, unit: "上架" },
    { id: "metering", label: "计量", value: summary.metering.total_tasks, unit: "任务" },
    { id: "settlement", label: "结算", value: summary.settlement.total_proposals, unit: "提案" },
  ];

  const statCards = [
    { icon: Users, label: "联邦 Agent", value: summary.gateway.agent_count, color: "bg-maref-accent/20 text-maref-accent" },
    { icon: Network, label: "联邦 Peer", value: summary.discovery.peer_count, color: "bg-maref-info/20 text-maref-info" },
    { icon: Scale, label: "策略规则", value: summary.policy.total_rules, color: "bg-maref-warning/20 text-maref-warning" },
    { icon: ShieldCheck, label: "信任报告", value: summary.trust.total_peer_reports, color: "bg-maref-success/20 text-maref-success" },
  ];

  const detailSections: Array<{
    title: string;
    icon: React.ElementType;
    rows: Array<[string, string | number]>;
  }> = [
    {
      title: "网关 Gateway",
      icon: Users,
      rows: [
        ["Agent 数", summary.gateway.agent_count],
        ["身份映射", summary.gateway.identity_mapping_count],
        ["协议", Object.entries(summary.gateway.protocols).map(([p, n]) => `${p}×${n}`).join(", ") || "-"],
      ],
    },
    {
      title: "发现 Discovery",
      icon: Network,
      rows: [
        ["Server", summary.discovery.server_id || "-"],
        ["健康 Peer", `${summary.discovery.healthy_peers}/${summary.discovery.peer_count}`],
        ["最大跳数", summary.discovery.max_depth],
      ],
    },
    {
      title: "目录 Catalog",
      icon: FileText,
      rows: [
        ["条目数", summary.catalog.entry_count],
        ["能力索引", summary.catalog.capability_count],
        ["订阅", summary.catalog.active_subscriptions],
      ],
    },
    {
      title: "信任 Trust",
      icon: ShieldCheck,
      rows: [
        ["本地 Agent", summary.trust.local_agent_count],
        ["有报告 Agent", summary.trust.agents_with_peer_reports],
        ["Peer 报告", summary.trust.total_peer_reports],
      ],
    },
    {
      title: "策略 Policy",
      icon: Scale,
      rows: [
        ["联邦规则", summary.policy.federation_rules],
        ["本地规则", summary.policy.local_rules],
        ["冲突策略", summary.policy.conflict_strategy || "-"],
      ],
    },
    {
      title: "HITL",
      icon: Star,
      rows: [
        ["总请求", summary.hitl.total_requests],
        ["待审批", summary.hitl.pending_count],
        ["参与组织", summary.hitl.total_orgs],
      ],
    },
    {
      title: "市场 Marketplace",
      icon: Coins,
      rows: [
        ["活跃上架", summary.marketplace.active_listings],
        ["评论数", summary.marketplace.total_reviews],
        ["平均价格", summary.marketplace.average_price],
      ],
    },
    {
      title: "计量 Metering",
      icon: Activity,
      rows: [
        ["任务数", summary.metering.total_tasks],
        ["指标数", summary.metering.total_metrics],
        ["组织数", summary.metering.total_orgs],
      ],
    },
    {
      title: "结算 Settlement",
      icon: CircleDollarSign,
      rows: [
        ["提案数", summary.settlement.total_proposals],
        ["账本条目", summary.settlement.ledger_entries],
        ["未结算额", summary.settlement.total_outstanding],
      ],
    },
  ];

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      <div className="flex-shrink-0 border-b border-maref-border bg-maref-surface px-6 py-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-maref-text">
          <GitMerge className="h-4 w-4 text-maref-accent" />
          联邦网络
        </h2>
        <p className="mt-0.5 text-xs text-maref-text-muted">
          联邦平台实时状态 · 拓扑可视化（Phase 2.3 真实数据）
        </p>
      </div>

      <div className="flex-1 space-y-6 p-6">
        <div className="grid grid-cols-4 gap-3">
          {statCards.map((card) => (
            <div
              key={card.label}
              className="flex items-center gap-3 rounded-lg border border-maref-border bg-maref-surface-alt/50 px-4 py-3"
            >
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

        <section className="rounded-lg border border-maref-border bg-maref-surface-alt/30 p-4">
          <h3 className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
            <Network className="h-3.5 w-3.5" />
            联邦拓扑
          </h3>
          <div className="h-[340px]">
            <TopologyMap nodes={nodes} />
          </div>
        </section>

        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          {detailSections.map((section) => (
            <section
              key={section.title}
              className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-4"
            >
              <h3 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-maref-text-muted">
                <section.icon className="h-3.5 w-3.5" />
                {section.title}
              </h3>
              <dl className="space-y-2">
                {section.rows.map(([label, value]) => (
                  <div key={label} className="flex items-center justify-between text-xs">
                    <dt className="text-maref-text-muted">{label}</dt>
                    <dd className="font-medium text-maref-text">{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
