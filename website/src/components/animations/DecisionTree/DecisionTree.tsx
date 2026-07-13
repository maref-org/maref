import { AnimateInView } from "@/components/ui/AnimateInView";

interface DecisionNode {
  label: string;
  desc: string;
  decision: "allow" | "block" | "pending";
  weight: number;
}

interface Content {
  badge: string;
  title: string;
  subtitle: string;
  rootLabel: string;
  rootDesc: string;
  nodes: DecisionNode[];
  allowLabel: string;
  blockLabel: string;
}

interface Props {
  content: Content;
}

export default function DecisionTree({ content }: Props) {
  const nodeWidth = 180;
  const nodeH = 60;
  const gapY = 100;
  const startY = 40;
  const centerX = 400;

  // Layout positions for each node
  const layout = [
    // Root
    { x: centerX - nodeWidth / 2, y: startY },
    // Chain nodes
    { x: centerX - nodeWidth / 2, y: startY + gapY },
    { x: centerX - nodeWidth / 2, y: startY + gapY * 2 },
    // Branch: Policy Engine (stays center)
    { x: centerX - nodeWidth / 2, y: startY + gapY * 3 },
    // Branch: Human Escalation (right)
    { x: centerX + nodeWidth * 0.7, y: startY + gapY * 3 },
  ];

  // Connectors: [fromIndex, toIndex]
  const connectors = [
    [0, 1],
    [1, 2],
    [2, 3],
    [2, 4], // Split at L2: to Policy Engine and Human Escalation
  ];

  function nodeCenter(idx: number): { x: number; y: number } {
    return {
      x: layout[idx].x + nodeWidth / 2,
      y: layout[idx].y + nodeH / 2,
    };
  }

  const nodes = [
    { label: content.rootLabel, desc: content.rootDesc, weight: 100, decision: "pending" as const, isRoot: true },
    ...content.nodes,
  ];

  return (
    <div className="py-24 px-6" id="decision-tree">
      <style>{`
        @keyframes dt-node-in {
          from { opacity: 0; transform: translateY(30px) scale(0.95); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @keyframes dt-line-in {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        .dt-node {
          animation: dt-node-in 0.5s ease-out forwards;
        }
        .dt-line {
          animation: dt-line-in 0.5s ease-out forwards;
        }
        .dt-weight {
          animation: dt-node-in 0.5s ease-out forwards;
        }
      `}</style>
      <div className="mx-auto max-w-(--content-max)">
        {/* Badge + Title */}
        <div className="text-center mb-12">
          <span
            className="inline-block text-xs font-semibold tracking-widest uppercase px-3 py-1 rounded-full mb-4"
            style={{ backgroundColor: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)", color: "var(--color-brand-accent-purple)" }}
          >
            {content.badge}
          </span>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{content.title}</h2>
          <p className="text-lg text-brand-text-secondary max-w-2xl mx-auto">{content.subtitle}</p>
        </div>

        {/* Tree SVG */}
        <div className="overflow-x-auto md:overflow-visible">
          <AnimateInView y={30} duration={0.6} once>
            <svg
              viewBox="0 0 800 460"
              className="min-w-[500px] md:min-w-0 w-full max-h-[500px]"
              role="img"
              aria-label={content.title}
            >
            {/* Connector lines */}
            {connectors.map(([from, to], i) => {
              const f = nodeCenter(from);
              const t = nodeCenter(to);
              return (
                <line
                  key={`conn-${i}`}
                  x1={f.x}
                  y1={f.y}
                  x2={t.x}
                  y2={t.y - 10}
                  stroke="var(--color-brand-border)"
                  strokeWidth="2"
                  className="dt-line"
                  style={{ animationDelay: `${0.1 + i * 0.35}s` }}
                />
              );
            })}

            {/* Weight labels on connectors */}
            {nodes.slice(1).map((node, i) => {
              const n = nodeCenter(i + 1);
              const p = nodeCenter(i);
              const midY = (p.y + n.y) / 2 - 10;
              return (
                <g
                  key={`weight-${i}`}
                  className="dt-weight"
                  style={{ animationDelay: `${0.1 + (i + connectors.length) * 0.35}s` }}
                >
                  <rect
                    x={centerX + 10}
                    y={midY - 10}
                    width="36"
                    height="20"
                    rx="10"
                    fill={node.decision === "block"
                      ? "var(--color-brand-bg-code)"
                      : "var(--color-brand-bg-code)"
                    }
                    stroke={node.decision === "block"
                      ? "var(--color-brand-accent-red)"
                      : node.decision === "allow"
                      ? "var(--color-brand-accent-green)"
                      : "var(--color-brand-border)"
                    }
                    strokeWidth="1"
                  />
                  <text
                    x={centerX + 28}
                    y={midY + 4}
                    textAnchor="middle"
                    fill={node.decision === "block"
                      ? "var(--color-brand-accent-red)"
                      : node.decision === "allow"
                      ? "var(--color-brand-accent-green)"
                      : "var(--color-brand-text-secondary)"
                    }
                    fontSize="11"
                    fontWeight="700"
                  >
                    {node.weight}%
                  </text>
                </g>
              );
            })}

            {/* Nodes */}
            {nodes.map((node, i) => {
              const l = layout[i] || { x: centerX - nodeWidth / 2, y: startY + gapY * 3 };
              const isTerminal = i === nodes.length - 1 || (i === nodes.length - 2 && node.decision === "allow");
              const color = node.decision === "allow"
                ? "var(--color-brand-accent-green)"
                : node.decision === "block"
                ? "var(--color-brand-accent-red)"
                : "var(--color-brand-accent-blue)";

              return (
                <g
                  key={`node-${i}`}
                  className="dt-node"
                  style={{ animationDelay: `${0.1 + (i + connectors.length + nodes.slice(1).length) * 0.35}s` }}
                >
                  {/* Node background */}
                  <rect
                    x={l.x}
                    y={l.y}
                    width={nodeWidth}
                    height={nodeH}
                    rx="12"
                    fill={node.isRoot
                      ? "var(--color-brand-bg-secondary)"
                      : node.decision === "allow"
                      ? "rgba(16,185,129,0.08)"
                      : node.decision === "block"
                      ? "rgba(239,68,68,0.08)"
                      : "var(--color-brand-bg-secondary)"
                    }
                    stroke={color}
                    strokeWidth={node.isRoot ? "1" : "2"}
                    strokeDasharray={node.decision === "pending" ? "4,2" : "none"}
                  />

                  {/* Root indicator */}
                  {node.isRoot && (
                    <>
                      <circle cx={l.x + nodeWidth + 20} cy={l.y + nodeH / 2} r="6" fill="var(--color-brand-accent-amber)" />
                      <text
                        x={l.x + nodeWidth + 34}
                        y={l.y + nodeH / 2 + 1}
                        textAnchor="start"
                        dominantBaseline="central"
                        fill="var(--color-brand-text-muted)"
                        fontSize="9"
                      >
                        ENTER
                      </text>
                    </>
                  )}

                  {/* Node label */}
                  <text
                    x={l.x + nodeWidth / 2}
                    y={l.y + nodeH / 2 - (isTerminal ? 5 : 4)}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fill={node.decision === "allow"
                      ? "var(--color-brand-accent-green)"
                      : node.decision === "block"
                      ? "var(--color-brand-accent-red)"
                      : "var(--color-brand-text-primary)"
                    }
                    fontSize={node.isRoot ? "13" : "12"}
                    fontWeight={node.isRoot ? "700" : "600"}
                  >
                    {node.label}
                  </text>

                  {/* Description */}
                  {!node.isRoot && (
                    <text
                      x={l.x + nodeWidth / 2}
                      y={l.y + nodeH / 2 + 14}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="var(--color-brand-text-muted)"
                      fontSize="9"
                    >
                      {node.desc}
                    </text>
                  )}

                  {/* Decision badge */}
                  {isTerminal && (
                    <g>
                      <rect
                        x={l.x + nodeWidth + 8}
                        y={l.y + nodeH / 2 - 12}
                        width="52"
                        height="24"
                        rx="6"
                        fill={node.decision === "allow"
                          ? "rgba(16,185,129,0.15)"
                          : "rgba(239,68,68,0.15)"
                        }
                        stroke={node.decision === "allow"
                          ? "var(--color-brand-accent-green)"
                          : "var(--color-brand-accent-red)"
                        }
                        strokeWidth="1.5"
                      />
                      <text
                        x={l.x + nodeWidth + 34}
                        y={l.y + nodeH / 2 + 1}
                        textAnchor="middle"
                        dominantBaseline="central"
                        fill={node.decision === "allow"
                          ? "var(--color-brand-accent-green)"
                          : "var(--color-brand-accent-red)"
                        }
                        fontSize="11"
                        fontWeight="800"
                      >
                        {node.decision === "allow" ? content.allowLabel : content.blockLabel}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
            </svg>
          </AnimateInView>
        </div>
      </div>
    </div>
  );
}
