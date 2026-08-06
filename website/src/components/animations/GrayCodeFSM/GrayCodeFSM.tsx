import { useState, useEffect, useCallback } from "react";

interface Content {
  badge: string;
  title: string;
  subtitle: string;
  stateNames: string[];
  legendCurrent: string;
  legendPath: string;
  legendHalt: string;
  legendHamming: string;
  autoPlay: string;
  step: string;
  reset: string;
}

interface Props {
  content: Content;
}

const STATES = [
  { id: 0, grayCode: "000000", isHalt: false },
  { id: 1, grayCode: "000001", isHalt: false },
  { id: 2, grayCode: "000011", isHalt: false },
  { id: 3, grayCode: "000010", isHalt: false },
  { id: 4, grayCode: "000110", isHalt: false },
  { id: 5, grayCode: "000111", isHalt: false },
  { id: 6, grayCode: "000101", isHalt: false },
  { id: 7, grayCode: "000100", isHalt: false },
  { id: 8, grayCode: "001100", isHalt: false },
  { id: 9, grayCode: "100000", isHalt: true },
];

function getChangedBit(from: string, to: string): number {
  for (let i = 0; i < 6; i++) {
    if (from[i] !== to[i]) return i;
  }
  return -1;
}

const STATE_COLORS = [
  "var(--color-brand-accent-blue)",
  "var(--color-brand-accent-cyan)",
  "var(--color-brand-accent-cyan)",
  "var(--color-brand-accent-green)",
  "var(--color-brand-accent-green)",
  "var(--color-brand-accent-amber)",
  "var(--color-brand-accent-amber)",
  "var(--color-brand-accent-orange)",
  "var(--color-brand-accent-purple)",
  "var(--color-brand-accent-red)",
];

/** Layout grid positions (grid units, not pixels) */
const LAYOUT_POSITIONS = [
  { x: 0, y: 0 }, { x: 1, y: 0 }, { x: 2, y: 0 }, { x: 3, y: 0 }, { x: 4, y: 0 },
  { x: 0.5, y: 1 }, { x: 1.5, y: 1 }, { x: 2.5, y: 1 }, { x: 3.5, y: 1 },
  { x: 4.5, y: 0.5 },
];

export default function GrayCodeFSM({ content }: Props) {
  const [current, setCurrent] = useState(0);
  const [autoPlay, setAutoPlay] = useState(true);
  const [prev, setPrev] = useState(-1);

  const stepForward = useCallback(() => {
    setPrev(current);
    setCurrent((c) => (c < 9 ? c + 1 : 9)); // HALT is absorbing
  }, [current]);

  const reset = useCallback(() => {
    setPrev(-1);
    setCurrent(0);
    setAutoPlay(true);
  }, []);

  useEffect(() => {
    if (!autoPlay || current >= 9) return;
    const t = setTimeout(() => stepForward(), 2500);
    return () => clearTimeout(t);
  }, [autoPlay, current, stepForward]);

  const handleStep = () => {
    setAutoPlay(false);
    stepForward();
  };

  const changedBit = prev >= 0
    ? getChangedBit(STATES[prev].grayCode, STATES[current].grayCode)
    : -1;

  const baseW = 720;
  const baseH = 380;
  const cx = 80;
  const cy = 70;
  const gapX = 125;
  const gapY = 120;

  function pos(id: number): { x: number; y: number } {
    const l = LAYOUT_POSITIONS[id];
    return { x: cx + l.x * gapX, y: cy + l.y * gapY };
  }

  return (
    <div className="py-24 px-6" id="gray-code-fsm">
      <style>{`
        @keyframes graycode-glow {
          0%, 100% { opacity: 0.15; transform: scale(1); }
          50% { opacity: 0.25; transform: scale(1.15); }
        }
        @keyframes graycode-wiggle {
          0%, 100% { transform: rotate(0deg); }
          25% { transform: rotate(10deg); }
          75% { transform: rotate(-10deg); }
        }
        .graycode-glow {
          animation: graycode-glow 2s ease-in-out infinite;
          transform-origin: var(--gcx) var(--gcy);
        }
        .graycode-wiggle {
          animation: graycode-wiggle 1.5s ease-in-out infinite;
        }
      `}</style>
      <div className="mx-auto max-w-(--content-max)">
        {/* Badge + Title */}
        <div className="text-center mb-12">
          <span
            className="inline-block text-xs font-semibold tracking-widest uppercase px-3 py-1 rounded-full mb-4"
            style={{ backgroundColor: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)", color: "var(--color-brand-accent-green)" }}
          >
            {content.badge}
          </span>
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{content.title}</h2>
          <p className="text-lg text-brand-text-secondary max-w-2xl mx-auto">{content.subtitle}</p>
        </div>

        {/* SVG */}
        <div className="overflow-x-auto md:overflow-visible">
          <svg
            viewBox={`0 0 ${baseW} ${baseH}`}
            className="min-w-[500px] md:min-w-0 w-full max-h-[400px]"
            role="img"
            aria-label={content.title}
          >
          {/* Transition arrows */}
          {Array.from({ length: STATES.length - 1 }, (_, i) => {
            const from = pos(i);
            const to = pos(i + 1);
            const midX = (from.x + to.x) / 2;
            const midY = (from.y + to.y) / 2;
            const isActive = current === i + 1;
            const isPrev = current > i;

            return (
              <g key={`arrow-${i}`}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={isActive ? "var(--color-brand-accent-green)" : isPrev ? "var(--color-brand-text-muted)" : "var(--color-brand-border)"}
                  strokeWidth="2"
                  strokeDasharray={isPrev ? "none" : "4,4"}
                  opacity={isPrev ? 0.8 : 0.4}
                  style={{ transition: "opacity 0.5s, stroke 0.5s" }}
                />
                {isActive && changedBit >= 0 && (
                  <g>
                    <rect
                      x={midX - 22}
                      y={midY - 12}
                      width="44"
                      height="16"
                      rx="4"
                      fill="var(--color-brand-bg-code)"
                      stroke="var(--color-brand-accent-green)"
                      strokeWidth="1"
                    />
                    <text
                      x={midX}
                      y={midY}
                      textAnchor="middle"
                      dominantBaseline="central"
                      fill="var(--color-brand-accent-green)"
                      fontSize="9"
                      fontWeight="600"
                    >
                      bit {changedBit}
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {/* States */}
          {STATES.map((state, i) => {
            const p = pos(i);
            const isCurrent = current === i;
            const isReached = current >= i;
            const color = state.isHalt
              ? "var(--color-brand-accent-red)"
              : STATE_COLORS[i];

            return (
              <g key={`state-${i}`}>
                {/* Glow for current state */}
                {isCurrent && (
                  <circle
                    cx={p.x}
                    cy={p.y}
                    r="32"
                    fill={color}
                    className="graycode-glow"
                    style={{ "--gcx": `${p.x}px`, "--gcy": `${p.y}px` } as React.CSSProperties}
                  />
                )}

                {/* HALT padlock indicator */}
                {state.isHalt && isCurrent && (
                  <g className="graycode-wiggle">
                    <text x={p.x + 36} y={p.y - 28} fill={color} fontSize="18">🔒</text>
                  </g>
                )}

                {/* State circle */}
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={isCurrent ? "26" : "22"}
                  fill={isReached ? `${color}20` : "var(--color-brand-bg-code)"}
                  stroke={isCurrent ? color : isReached ? `${color}80` : "var(--color-brand-border)"}
                  strokeWidth={isCurrent ? "3" : "1.5"}
                  style={{ transition: "r 0.4s ease-in-out, stroke-width 0.4s ease-in-out, fill 0.4s ease-in-out, stroke 0.4s ease-in-out" }}
                />

                {/* State name */}
                <text
                  x={p.x}
                  y={p.y - 3}
                  textAnchor="middle"
                  fill={isReached ? "var(--color-brand-text-primary)" : "var(--color-brand-text-secondary)"}
                  fontSize="9"
                  fontWeight={isCurrent ? "700" : "500"}
                >
                  {content.stateNames[i]}
                </text>

                {/* Gray code */}
                <text
                  x={p.x}
                  y={p.y + 14}
                  textAnchor="middle"
                  fontFamily="monospace"
                  fontSize="8"
                  fill={isReached ? "var(--color-brand-text-secondary)" : "var(--color-brand-text-muted)"}
                >
                  {state.grayCode}
                </text>
              </g>
            );
          })}

          {/* Bit indicators for current state */}
          <g transform={`translate(10, ${baseH - 70})`}>
            <text x="0" y="0" fill="var(--color-brand-text-secondary)" fontSize="9" fontWeight="600">
              Current: {STATES[current].grayCode}
            </text>
            <g transform="translate(0, 10)">
              {Array.from({ length: 6 }, (_, b) => (
                <rect
                  key={b}
                  x={b * 16}
                  y="0"
                  width="14"
                  height="14"
                  rx="3"
                  fill={STATES[current].grayCode[b] === "1"
                    ? "var(--color-brand-accent-blue)"
                    : "var(--color-brand-text-muted)"
                  }
                  opacity={STATES[current].grayCode[b] === "1" ? "0.8" : "0.2"}
                />
              ))}
            </g>
          </g>

          {/* Legend */}
          <g transform={`translate(${baseW - 130}, ${baseH - 80})`}>
            <circle cx="0" cy="0" r="5" fill="var(--color-brand-accent-green)" opacity="0.6" />
            <text x="12" y="4" fill="var(--color-brand-text-secondary)" fontSize="9">{content.legendCurrent}</text>
            <line x1="0" y1="18" x2="14" y2="18" stroke="var(--color-brand-text-muted)" strokeWidth="1.5" strokeDasharray="3,2" />
            <text x="20" y="22" fill="var(--color-brand-text-secondary)" fontSize="9">{content.legendPath}</text>
            <text x="0" y="40" fill="var(--color-brand-accent-green)" fontSize="9">{content.legendHamming}</text>
            <text x="0" y="52" fill="var(--color-brand-accent-red)" fontSize="9">{content.legendHalt}</text>
          </g>
          </svg>
        </div>

        {/* Controls */}
        <div className="flex items-center justify-center gap-4 mt-8">
          <button
            onClick={reset}
            className="px-4 py-2 text-sm rounded-lg border transition-colors hover:opacity-80"
            style={{ borderColor: "var(--color-brand-border)", color: "var(--color-brand-text-secondary)" }}
            disabled={current === 0 && autoPlay}
          >
            {content.reset}
          </button>

          <button
            onClick={() => setAutoPlay(!autoPlay)}
            className={`px-4 py-2 text-sm rounded-lg border transition-colors ${
              autoPlay
                ? "border-brand-accent-green text-brand-accent-green"
                : "text-brand-text-secondary border-brand-border hover:opacity-80"
            }`}
          >
            {autoPlay ? "⏸" : "▶"} {content.autoPlay}
          </button>

          <button
            onClick={handleStep}
            className="px-4 py-2 text-sm rounded-lg border text-brand-accent-blue border-brand-border hover:opacity-80 transition-colors"
            disabled={current >= 9}
            style={{ opacity: current >= 9 ? 0.4 : 1 }}
          >
            {content.step}
          </button>
        </div>
      </div>
    </div>
  );
}
