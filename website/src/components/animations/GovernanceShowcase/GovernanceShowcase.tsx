import { useState, useEffect, useRef } from "react";

interface Content {
  badge: string;
  title: string;
  subtitle: string;
  marefLabel: string;
  decisionsLabel: string;
  blockedLabel: string;
  agentsLabel: string;
  agents: { name: string; type: string }[];
}

interface Props {
  content: Content;
}

type Decision = { id: number; agentIdx: number; type: "ALLOW" | "BLOCK"; x: number; y: number; progress: number };

export default function GovernanceShowcase({ content }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dim, setDim] = useState({ w: 800, h: 500 });
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [stats, setStats] = useState({ decisions: 0, blocked: 0 });
  const idRef = useRef(0);
  const cx = dim.w / 2;
  const cy = dim.h / 2;
  const hubR = 56;

  // Responsive dimensions
  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        const w = containerRef.current.offsetWidth;
        setDim({ w: Math.max(w, 320), h: Math.min(Math.max(w * 0.55, 360), 520) });
      }
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // Agent positions arranged in a circle around hub
  const agentPositions = content.agents.map((_, i) => {
    const angle = (2 * Math.PI * i) / content.agents.length - Math.PI / 2;
    const rad = Math.min(dim.w, dim.h) * 0.32;
    return { x: cx + rad * Math.cos(angle), y: cy + rad * Math.sin(angle) };
  });

  // Spawn decisions periodically
  useEffect(() => {
    if (dim.w < 100) return;
    const interval = setInterval(() => {
      const agentIdx = Math.floor(Math.random() * content.agents.length);
      const pos = agentPositions[agentIdx];
      const type = Math.random() < 0.7 ? "ALLOW" : "BLOCK";
      idRef.current += 1;
      setDecisions((prev) => [...prev.slice(-8), { id: idRef.current, agentIdx, type, x: pos.x, y: pos.y, progress: 0 }]);
      setStats((prev) => ({ decisions: prev.decisions + 1, blocked: prev.blocked + (type === "BLOCK" ? 1 : 0) }));
    }, 1200);
    return () => clearInterval(interval);
  }, [dim, content.agents.length, agentPositions]);

  // Animate decisions along the line
  useEffect(() => {
    if (decisions.length === 0) return;
    const frame = setInterval(() => {
      setDecisions((prev) =>
        prev
          .map((d) => ({ ...d, progress: d.progress + 0.025 }))
          .filter((d) => d.progress < 1)
      );
    }, 30);
    return () => clearInterval(frame);
  }, [decisions.length]);

  const isSmall = dim.w < 500;

  return (
    <div
      ref={containerRef}
      className="relative w-full overflow-hidden rounded-xl"
      style={{
        background: "radial-gradient(ellipse at center, var(--color-brand-bg-secondary) 0%, var(--color-brand-bg-primary) 100%)",
        border: "1px solid var(--color-brand-border)",
        minHeight: "360px",
        aspectRatio: "1.6 / 1",
      }}
      role="img"
      aria-label={content.subtitle}
    >
      <svg viewBox={`0 0 ${dim.w} ${dim.h}`} className="w-full h-full" style={{ overflow: "visible" }}>
        {/* Connecting lines */}
        {agentPositions.map((pos, i) => {
          const angle = Math.atan2(pos.y - cy, pos.x - cx);
          const startX = cx + hubR * Math.cos(angle);
          const startY = cy + hubR * Math.sin(angle);
          const endR = 28;
          const endX = pos.x - endR * Math.cos(angle);
          const endY = pos.y - endR * Math.sin(angle);
          return (
            <line
              key={i}
              x1={startX}
              y1={startY}
              x2={endX}
              y2={endY}
              stroke="var(--color-brand-border)"
              strokeWidth="1.5"
              strokeDasharray="6 4"
              opacity={0.6}
            />
          );
        })}

        {/* Agent nodes */}
        {agentPositions.map((pos, i) => (
          <g key={i}>
            <rect
              x={pos.x - 28}
              y={pos.y - 14}
              width="56"
              height="28"
              rx="14"
              fill="var(--color-brand-bg-tertiary)"
              stroke="var(--color-brand-accent-blue)"
              strokeWidth="1.5"
              opacity={0.9}
            />
            <text
              x={pos.x}
              y={pos.y + 1}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--color-brand-text-primary)"
              fontSize={isSmall ? 8 : 10}
              fontWeight={600}
            >
              {content.agents[i].name}
            </text>
            <text
              x={pos.x}
              y={pos.y + (isSmall ? 10 : 12)}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--color-brand-text-muted)"
              fontSize={isSmall ? 6 : 7}
            >
              {content.agents[i].type}
            </text>
          </g>
        ))}

        {/* Decision particles */}
        {decisions.map((d) => {
          const angle = Math.atan2(d.y - cy, d.x - cx);
          const fromX = cx + hubR * Math.cos(angle);
          const fromY = cy + hubR * Math.sin(angle);
          const toEndR = 28;
          const toX = d.x - toEndR * Math.cos(angle);
          const toY = d.y - toEndR * Math.sin(angle);
          const px = fromX + (toX - fromX) * d.progress;
          const py = fromY + (toY - fromY) * d.progress;
          const isBlock = d.type === "BLOCK";
          return (
            <g key={d.id}>
              <circle cx={px} cy={py} r={5} fill={isBlock ? "#ef4444" : "#22c55e"} opacity={0.9}>
                <animate attributeName="r" values="5;7;5" dur="0.8s" repeatCount="indefinite" />
              </circle>
              <text
                x={px}
                y={py - 10}
                textAnchor="middle"
                dominantBaseline="central"
                fill={isBlock ? "#ef4444" : "#22c55e"}
                fontSize={7}
                fontWeight={700}
              >
                {d.type}
              </text>
            </g>
          );
        })}

        {/* MAREF Hub - Hexagon */}
        <polygon
          points={Array.from({ length: 6 }, (_, i) => {
            const a = (Math.PI / 3) * i - Math.PI / 6;
            return `${cx + hubR * Math.cos(a)},${cy + hubR * Math.sin(a)}`;
          }).join(" ")}
          fill="var(--color-brand-accent-blue)"
          opacity="0.15"
          stroke="var(--color-brand-accent-blue)"
          strokeWidth="2"
        >
          <animateTransform attributeName="transform" type="rotate" from={`0 ${cx} ${cy}`} to={`360 ${cx} ${cy}`} dur="20s" repeatCount="indefinite" />
        </polygon>
        <polygon
          points={Array.from({ length: 6 }, (_, i) => {
            const a = (Math.PI / 3) * i;
            return `${cx + (hubR - 8) * Math.cos(a)},${cy + (hubR - 8) * Math.sin(a)}`;
          }).join(" ")}
          fill="none"
          stroke="var(--color-brand-accent-cyan)"
          strokeWidth="1"
          opacity="0.4"
        >
          <animateTransform attributeName="transform" type="rotate" from={`360 ${cx} ${cy}`} to={`0 ${cx} ${cy}`} dur="25s" repeatCount="indefinite" />
        </polygon>
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--color-brand-accent-blue)"
          fontSize={isSmall ? 10 : 13}
          fontWeight={800}
        >
          MAREF
        </text>
        <text
          x={cx}
          y={cy + (isSmall ? 10 : 12)}
          textAnchor="middle"
          dominantBaseline="central"
          fill="var(--color-brand-text-muted)"
          fontSize={isSmall ? 6 : 7}
        >
          {content.marefLabel}
        </text>

        {/* Pulsing ring around hub */}
        <circle cx={cx} cy={cy} r={hubR + 10} fill="none" stroke="var(--color-brand-accent-blue)" strokeWidth="1" opacity="0.3">
          <animate attributeName="r" values={`${hubR + 10};${hubR + 30};${hubR + 10}`} dur="3s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.3;0;0.3" dur="3s" repeatCount="indefinite" />
        </circle>

        {/* Stats bar at bottom */}
        <g>
          <rect x={cx - 140} y={dim.h - 50} width="280" height="36" rx="8" fill="var(--color-brand-bg-code)" stroke="var(--color-brand-border)" strokeWidth="1" opacity="0.8" />
          <text x={cx - 120} y={dim.h - 34} dominantBaseline="central" fill="var(--color-brand-text-muted)" fontSize={isSmall ? 7 : 9}>
            {content.decisionsLabel}
          </text>
          <text x={cx - 56} y={dim.h - 34} dominantBaseline="central" fill="var(--color-brand-accent-cyan)" fontSize={isSmall ? 10 : 13} fontWeight={700}>
            {stats.decisions}
          </text>
          <text x={cx - 20} y={dim.h - 34} dominantBaseline="central" fill="var(--color-brand-text-muted)" fontSize={isSmall ? 7 : 9}>
            {content.blockedLabel}
          </text>
          <text x={cx + 45} y={dim.h - 34} dominantBaseline="central" fill="#ef4444" fontSize={isSmall ? 10 : 13} fontWeight={700}>
            {stats.blocked}
          </text>
          <text x={cx + 75} y={dim.h - 34} dominantBaseline="central" fill="var(--color-brand-text-muted)" fontSize={isSmall ? 7 : 9}>
            {content.agentsLabel}
          </text>
          <text x={cx + 125} y={dim.h - 34} dominantBaseline="central" fill="var(--color-brand-text-primary)" fontSize={isSmall ? 10 : 13} fontWeight={700}>
            {content.agents.length}
          </text>
        </g>
      </svg>
    </div>
  );
}
