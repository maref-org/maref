import { useState, useEffect, useRef, useCallback } from "react";

interface LayerDef {
  name: string;
  color: string;
  interceptable?: boolean;
}

interface Content {
  badge: string;
  title: string;
  subtitle: string;
  attackLabel: string;
  blockedLabel: string;
  layers: LayerDef[];
}

interface Props {
  content: Content;
}

interface Particle {
  id: number;
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  color: string;
  life: number;
}

export default function DefenseLayers({ content }: Props) {
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<"idle" | "running" | "intercept" | "done">("idle");
  const [particles, setParticles] = useState<Particle[]>([]);
  const animRef = useRef<number>(0);
  const startTimeRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  const numLayers = content.layers.length;
  const layerH = 36;
  const layerGap = 8;
  const svgW = 700;
  const svgH = numLayers * (layerH + layerGap) + 60;
  const arrowY = 30;
  const interceptLayerIdx = content.layers.findIndex((l) => l.interceptable);

  // Intercept x position (center of the intercept layer)
  const interceptX = 420;

  function getLayerY(idx: number): number {
    return 50 + idx * (layerH + layerGap);
  }

  function spawnParticles(atX: number, atY: number) {
    const p: Particle[] = [];
    const colors = [
      "#ef4444", "#f97316", "#f59e0b", "#eab308",
      "#3b82f6", "#06b6d4", "#10b981", "#8b5cf6",
    ];
    for (let i = 0; i < 24; i++) {
      const angle = (Math.PI * 2 * i) / 24 + (Math.random() - 0.5) * 0.3;
      const speed = 1.5 + Math.random() * 3;
      p.push({
        id: i,
        x: atX,
        y: atY,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
        size: 2 + Math.random() * 4,
        color: colors[i % colors.length],
        life: 1,
      });
    }
    setParticles(p);
  }

  const reset = useCallback(() => {
    setProgress(0);
    setPhase("idle");
    setParticles([]);
    startTimeRef.current = 0;
  }, []);

  const start = useCallback(() => {
    reset();
    // Small delay then run
    setTimeout(() => {
      setPhase("running");
      startTimeRef.current = performance.now();
    }, 300);
  }, [reset]);

  // Animation loop
  useEffect(() => {
    if (phase !== "running") return;

    const duration = 4000; // 4 seconds total
    const interceptTime = (interceptLayerIdx + 0.5) / (numLayers + 1) * duration;

    function tick(now: number) {
      if (!startTimeRef.current) startTimeRef.current = now;
      const elapsed = now - startTimeRef.current;
      const p = Math.min(elapsed / duration, 1);
      setProgress(p);

      if (elapsed >= interceptTime && phase === "running" && interceptLayerIdx >= 0) {
        const lY = getLayerY(interceptLayerIdx) + layerH / 2;
        spawnParticles(interceptX, lY);
        setPhase("intercept");
        setTimeout(() => setPhase("done"), 800);
        return;
      }

      if (p >= 1) {
        setPhase("done");
        return;
      }

      animRef.current = requestAnimationFrame(tick);
    }

    animRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animRef.current);
  }, [phase, interceptLayerIdx, numLayers]);

  // Update particles
  useEffect(() => {
    if (phase !== "intercept" || particles.length === 0) return;

    const interval = setInterval(() => {
      setParticles((prev) =>
        prev
          .map((p) => ({
            ...p,
            x: p.x + p.vx,
            y: p.y + p.vy,
            vx: p.vx * 0.97,
            vy: p.vy * 0.97,
            life: p.life - 0.02,
          }))
          .filter((p) => p.life > 0)
      );
    }, 30);

    return () => clearInterval(interval);
  }, [phase, particles.length > 0]);

  // Arrow position
  const arrowX = (() => {
    if (phase === "idle") return -80;
    if (phase === "intercept" || phase === "done") return interceptX;
    return -80 + (interceptX + 80) * progress;
  })();

  function isLayerActive(idx: number): boolean {
    if (phase === "idle") return false;
    if (phase === "done") return idx < interceptLayerIdx;
    const layerProgress = (idx + 0.5) / numLayers;
    return progress > layerProgress && idx < interceptLayerIdx;
  }

  function isLayerCurrent(idx: number): boolean {
    if (phase === "idle") return false;
    if (idx >= interceptLayerIdx) return false;
    const layerStart = idx / numLayers;
    const layerEnd = (idx + 1) / numLayers;
    return progress >= layerStart && progress < layerEnd;
  }

  const prefersReduced = typeof window !== "undefined"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

  // Show static "blocked" state for reduced motion
  if (prefersReduced) {
    return (
      <DefenseLayersStatic
        content={content}
        interceptLayerIdx={interceptLayerIdx}
        getLayerY={getLayerY}
        layerH={layerH}
        layerGap={layerGap}
        svgW={svgW}
        svgH={svgH}
        arrowY={arrowY}
        interceptX={interceptX}
      />
    );
  }

  return (
    <div className="py-24 px-6" id="defense-layers" ref={containerRef}>
      <style>{`
        @keyframes defense-blocked-in {
          from { opacity: 0; transform: scale(0.5); }
          to { opacity: 1; transform: scale(1); }
        }
        .defense-blocked {
          animation: defense-blocked-in 0.5s ease-out forwards;
        }
      `}</style>
      <div className="mx-auto max-w-(--content-max)">
        {/* Badge + Title */}
        <div className="text-center mb-12">
          <span
            className="inline-block text-xs font-semibold tracking-widest uppercase px-3 py-1 rounded-full mb-4"
            style={{ backgroundColor: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)", color: "var(--color-brand-accent-orange)" }}
          >
            {content.badge}
          </span>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{content.title}</h2>
          <p className="text-lg text-brand-text-secondary max-w-2xl mx-auto">{content.subtitle}</p>
        </div>

        {/* SVG */}
        <div className="relative overflow-x-auto md:overflow-visible">
          <svg
            viewBox={`0 0 ${svgW} ${svgH}`}
            className="min-w-[500px] md:min-w-0 w-full max-h-[500px]"
            role="img"
            aria-label={content.title}
          >
            {/* Background */}
            <rect x="0" y="0" width={svgW} height={svgH} fill="transparent" />

            {/* "SAFE ZONE" label on right side */}
            <text
              x={svgW - 20}
              y={svgH / 2}
              textAnchor="middle"
              transform={`rotate(90, ${svgW - 20}, ${svgH / 2})`}
              fill="var(--color-brand-accent-green)"
              fontSize="11"
              fontWeight="700"
              opacity="0.3"
              letterSpacing="4"
            >
              PROTECTED
            </text>

            {/* Layers */}
            {content.layers.map((layer, i) => {
              const y = getLayerY(i);
              const active = isLayerActive(i);
              const current = isLayerCurrent(i);
              const isIntercepted = i === interceptLayerIdx && (phase === "intercept" || phase === "done");

              return (
                <g key={`layer-${i}`}>
                  {/* Layer bar */}
                  <rect
                    x="120"
                    y={y}
                    width={svgW - 160}
                    height={layerH}
                    rx="6"
                    fill={isIntercepted
                      ? "rgba(16,185,129,0.15)"
                      : current
                      ? `${layer.color}25`
                      : active
                      ? `${layer.color}15`
                      : "var(--color-brand-bg-code)"
                    }
                    stroke={isIntercepted
                      ? "var(--color-brand-accent-green)"
                      : current
                      ? layer.color
                      : active
                      ? `${layer.color}60`
                      : "var(--color-brand-border)"
                    }
                    strokeWidth={isIntercepted ? "2" : current ? "2" : "1"}
                  />

                  {/* Layer number */}
                  <text
                    x="110"
                    y={y + layerH / 2}
                    textAnchor="end"
                    dominantBaseline="central"
                    fill={current ? layer.color : "var(--color-brand-text-muted)"}
                    fontSize="11"
                    fontWeight={current ? "700" : "500"}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </text>

                  {/* Layer name */}
                  <text
                    x="130"
                    y={y + layerH / 2}
                    textAnchor="start"
                    dominantBaseline="central"
                    fill={isIntercepted ? "var(--color-brand-accent-green)" : current ? layer.color : active ? "var(--color-brand-text-secondary)" : "var(--color-brand-text-muted)"}
                    fontSize="11"
                    fontWeight={isIntercepted ? "700" : current ? "600" : "400"}
                  >
                    {layer.name}
                  </text>

                  {/* Intercepted shield icon */}
                  {isIntercepted && (
                    <text
                      x={svgW - 80}
                      y={y + layerH / 2}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="var(--color-brand-accent-green)"
                      fontSize="16"
                    >
                      🛡
                    </text>
                  )}
                </g>
              );
            })}

            {/* Progress track */}
            <rect
              x={120}
              y={arrowY - 2}
              width={interceptX - 120}
              height="4"
              rx="2"
              fill="var(--color-brand-border)"
              opacity="0.5"
            />
            <rect
              x={120}
              y={arrowY - 2}
              width={(interceptX - 120) * Math.min(progress * (numLayers + 1), 1)}
              height="4"
              rx="2"
              fill="var(--color-brand-accent-red)"
              opacity="0.6"
              style={{ transition: "width 0.05s linear" }}
            />

            {/* Attack arrow */}
            {phase !== "idle" && (
              <g style={{
                transform: `translateX(${Math.max(0, arrowX - 120)}px)`,
                transition: phase === "running" ? "none" : "transform 0.6s cubic-bezier(0.34, 1.56, 0.64, 1)",
              }}>
                {/* Arrow body */}
                <polygon
                  points="0,10 30,0 30,20"
                  fill="var(--color-brand-accent-red)"
                />
                {/* Arrow trail */}
                <rect
                  x="-40"
                  y="8"
                  width="40"
                  height="4"
                  rx="2"
                  fill="var(--color-brand-accent-red)"
                  opacity="0.4"
                />
                {/* Attack label */}
                <text
                  x="-35"
                  y="28"
                  fill="var(--color-brand-accent-red)"
                  fontSize="8"
                  fontWeight="700"
                >
                  {content.attackLabel}
                </text>
              </g>
            )}

            {/* Particles */}
            {particles.map((p) => (
              <circle
                key={p.id}
                cx={p.x}
                cy={p.y}
                r={p.size}
                fill={p.color}
                opacity={Math.max(0, p.life)}
              />
            ))}

            {/* BLOCKED message */}
            {(phase === "intercept" || phase === "done") && (
              <g className="defense-blocked">
                <rect
                  x={interceptX - 80}
                  y={arrowY + 40}
                  width="160"
                  height="32"
                  rx="8"
                  fill="rgba(16,185,129,0.15)"
                  stroke="var(--color-brand-accent-green)"
                  strokeWidth="2"
                />
                <text
                  x={interceptX}
                  y={arrowY + 60}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fill="var(--color-brand-accent-green)"
                  fontSize="12"
                  fontWeight="800"
                >
                  {content.blockedLabel}
                </text>
              </g>
            )}
          </svg>

          {/* Replay button */}
          {phase === "done" && (
            <div className="flex justify-center mt-4">
              <button
                onClick={start}
                className="px-5 py-2 text-sm rounded-lg border transition-colors hover:opacity-80"
                style={{ borderColor: "var(--color-brand-border)", color: "var(--color-brand-text-secondary)" }}
              >
                ⟳ Replay
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Auto-start on view */}
      <AutoStart onStart={start} phase={phase} />
    </div>
  );
}

/** Auto-triggers the animation once when the component enters the viewport */
function AutoStart({ onStart, phase }: { onStart: () => void; phase: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || phase !== "idle") return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          onStart();
          observer.disconnect();
        }
      },
      { threshold: 0.3 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [onStart, phase]);

  return <div ref={ref} className="h-1" />;
}

/** Static version shown when prefers-reduced-motion is active */
function DefenseLayersStatic(props: {
  content: Content;
  interceptLayerIdx: number;
  getLayerY: (idx: number) => number;
  layerH: number;
  layerGap: number;
  svgW: number;
  svgH: number;
  arrowY: number;
  interceptX: number;
}) {
  const { content, interceptLayerIdx, getLayerY, layerH, svgW, svgH } = props;

  return (
    <div className="py-24 px-6" id="defense-layers">
      <div className="mx-auto max-w-(--content-max)">
        <div className="text-center mb-12">
          <span
            className="inline-block text-xs font-semibold tracking-widest uppercase px-3 py-1 rounded-full mb-4"
            style={{ backgroundColor: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)", color: "var(--color-brand-accent-orange)" }}
          >
            {content.badge}
          </span>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{content.title}</h2>
          <p className="text-lg text-brand-text-secondary max-w-2xl mx-auto">{content.subtitle}</p>
        </div>

        <svg viewBox={`0 0 ${svgW} ${svgH}`} className="w-full max-h-[500px]" role="img" aria-label={content.title}>
          {content.layers.map((layer, i) => {
            const y = getLayerY(i);
            const isIntercepted = i === interceptLayerIdx;
            return (
              <g key={`layer-${i}`}>
                <rect
                  x="120"
                  y={y}
                  width={svgW - 160}
                  height={layerH}
                  rx="6"
                  fill={isIntercepted ? "rgba(16,185,129,0.15)" : `${layer.color}10`}
                  stroke={isIntercepted ? "var(--color-brand-accent-green)" : "var(--color-brand-border)"}
                  strokeWidth={isIntercepted ? "2" : "1"}
                />
                <text
                  x="110"
                  y={y + layerH / 2}
                  textAnchor="end"
                  dominantBaseline="central"
                  fill="var(--color-brand-text-muted)"
                  fontSize="11"
                >
                  {String(i + 1).padStart(2, "0")}
                </text>
                <text
                  x="130"
                  y={y + layerH / 2}
                  textAnchor="start"
                  dominantBaseline="central"
                  fill={isIntercepted ? "var(--color-brand-accent-green)" : "var(--color-brand-text-secondary)"}
                  fontSize="11"
                  fontWeight={isIntercepted ? "700" : "400"}
                >
                  {layer.name}
                </text>
                {isIntercepted && (
                  <text x={svgW - 80} y={y + layerH / 2} textAnchor="middle" dominantBaseline="central" fill="var(--color-brand-accent-green)" fontSize="16">🛡</text>
                )}
              </g>
            );
          })}

          <text x={interceptLayerIdx >= 0 ? 420 : 400} y={40} textAnchor="middle" fill="var(--color-brand-accent-red)" fontSize="10" fontWeight="700">
            ATTACK STOPPED
          </text>
        </svg>
      </div>
    </div>
  );
}
