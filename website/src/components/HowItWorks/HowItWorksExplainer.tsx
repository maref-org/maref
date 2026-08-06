import { useState, useEffect } from "react";
import { AnimateInView, FadeIn } from "@/components/ui/AnimateInView";

interface SceneContent {
  heroTitle1: string;
  heroTitle2: string;
  problemTitle: string;
  problemDesc: string;
  problemAction1: string;
  problemAction2: string;
  problemAction3: string;
  problemTarget: string;
  interceptTitle: string;
  interceptDesc: string;
  interceptLabel: string;
  pipelineTitle: string;
  pipelineDesc: string;
  stage1Label: string;
  stage1Desc: string;
  stage2Label: string;
  stage2Desc: string;
  stage3Label: string;
  stage3Desc: string;
  resultTitle: string;
  resultDesc: string;
  allowLabel: string;
  blockLabel: string;
  comparisonTitle: string;
  comparisonDesc: string;
  beforeTitle: string;
  afterTitle: string;
  beforeItem1: string;
  beforeItem2: string;
  beforeItem3: string;
  afterItem1: string;
  afterItem2: string;
  afterItem3: string;
  allowSubtitle: string;
  blockSubtitle: string;
  ctaTitle: string;
  ctaDesc: string;
  ctaQuickstart: string;
  ctaStar: string;
}

interface Props {
  content: SceneContent;
  locale?: string;
}

export default function HowItWorksExplainer({ content, locale = "en" }: Props) {
  const c = content;
  const [isSmall, setIsSmall] = useState(
    typeof window !== "undefined" && window.innerWidth < 640
  );

  useEffect(() => {
    const onResize = () => setIsSmall(window.innerWidth < 640);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    <div>
      <style>{`
        .scene-svg { overflow: visible; }
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.3; }
          50% { opacity: 0.8; }
        }
        @keyframes float {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-6px); }
        }
        @keyframes dash-flow {
          to { stroke-dashoffset: -20; }
        }
        .animate-pulse-glow { animation: pulse-glow 2s ease-in-out infinite; }
        .animate-float { animation: float 3s ease-in-out infinite; }
        .dash-flow { animation: dash-flow 0.8s linear infinite; }
      `}</style>

      {/* Scene 0: Hero */}
      <section className="relative min-h-[85vh] flex items-center justify-center px-6 overflow-hidden">
        <div className="absolute inset-0" style={{
          background: "radial-gradient(ellipse 60% 50% at 50% 40%, rgba(56,189,248,0.06) 0%, transparent 60%)",
        }} />
        <FadeIn className="relative z-10 text-center max-w-3xl mx-auto">
          <h1 className="text-4xl md:text-7xl font-bold tracking-tight mb-6 leading-[1.15]">
            {c.heroTitle1}
            <br />
            <span className="text-brand-accent-blue">{c.heroTitle2}</span>
          </h1>
          <p className="text-lg md:text-xl text-brand-text-secondary max-w-2xl mx-auto mb-10 leading-relaxed">
            {c.interceptDesc}
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <a
              href="#problem"
              className="inline-flex items-center gap-2 rounded-buttons px-6 py-3 font-semibold text-xs uppercase tracking-wider transition-all hover:opacity-90"
              style={{ background: "var(--gradient-current)", color: "var(--surface-trench)" }}
            >
              {isSmall ? "See how →" : "See how it works ↓"}
            </a>
          </div>
        </FadeIn>
        <div
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
          style={{ opacity: 0.5 }}
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-fog-veil">
            <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
          </svg>
        </div>
      </section>

      {/* Scene 1: The Problem */}
      <section id="problem" className="py-24 px-6" style={{ background: "var(--color-brand-bg-primary)" }}>
        <div className="mx-auto max-w-(--content-max)">
          <AnimateInView className="text-center mb-16">
            <span className="inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider mb-4"
              style={{ backgroundColor: "rgba(239,68,68,0.12)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.25)" }}
            >
              ☠ {c.problemTitle}
            </span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.problemDesc}</h2>
          </AnimateInView>

          <AnimateInView
            className="relative mx-auto rounded-xl overflow-hidden"
            delay={0.2}
            style={{
              maxWidth: "800px",
              background: "var(--color-brand-bg-secondary)",
              border: "1px solid rgba(239,68,68,0.2)",
            }}
          >
            <svg viewBox="0 0 800 360" className="w-full h-auto" style={{ overflow: "visible" }}>
              <defs>
                <linearGradient id="dangerGlow" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity="0.15" />
                  <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
                </linearGradient>
              </defs>
              <rect x="0" y="0" width="800" height="360" fill="url(#dangerGlow)" />
              <g className="animate-float" style={{ transformOrigin: "180px 180px" }}>
                <rect x="100" y="120" width="160" height="80" rx="16" fill="var(--color-brand-bg-tertiary)"
                  stroke="#ef4444" strokeWidth="2" opacity="0.9" />
                <text x="180" y="158" textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-primary)" fontSize="20" fontWeight="700">Your Agent</text>
                <text x="180" y="178" textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-muted)" fontSize="13">"delete everything"</text>
              </g>
              <g>
                {[
                  { y: 158, delay: 0, label: c.problemAction1 },
                  { y: 190, delay: 0.5, label: c.problemAction2 },
                ].map((arrow, i) => (
                  <g key={i}>
                    <line x1="260" y1={arrow.y} x2="520" y2={arrow.y}
                      stroke="#ef4444" strokeWidth="2" strokeDasharray="6 4"
                      className="dash-flow"
                      style={{ animationDelay: `${arrow.delay}s` }} />
                    <polygon points="520,158 512,152 512,164" fill="#ef4444"
                      transform={`translate(0, ${arrow.y - 158})`} />
                    <rect x="300" y={arrow.y - 18} width="120" height="24" rx="6"
                      fill="rgba(239,68,68,0.12)" stroke="rgba(239,68,68,0.3)" strokeWidth="1" />
                    <text x="360" y={arrow.y} textAnchor="middle" dominantBaseline="central"
                      fill="#ef4444" fontSize="12" fontWeight="600">{arrow.label}</text>
                  </g>
                ))}
              </g>
              <g>
                <rect x="550" y="100" width="180" height="160" rx="12" fill="var(--color-brand-bg-tertiary)"
                  stroke="var(--color-brand-border)" strokeWidth="2" />
                <text x="640" y={isSmall ? 150 : 145} textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-primary)" fontSize="16" fontWeight="700">{c.problemTarget}</text>
                <line x1="570" y1="170" x2="710" y2="170" stroke="var(--color-brand-border)" strokeWidth="1" />
                {[c.problemAction1, c.problemAction2, c.problemAction3].map((item, i) => (
                  <text key={i} x="640" y={195 + i * 24} textAnchor="middle" dominantBaseline="central"
                    fill="var(--color-brand-text-muted)" fontSize="13">⚠ {item}</text>
                ))}
              </g>
              <circle cx="180" cy="160" r="110" fill="none" stroke="#ef4444" strokeWidth="1.5" opacity="0.15"
                className="animate-pulse-glow" />
            </svg>
          </AnimateInView>
        </div>
      </section>

      {/* Scene 2: The Intercept */}
      <section className="py-24 px-6" style={{ background: "var(--color-brand-bg-secondary)" }}>
        <div className="mx-auto max-w-(--content-max)">
          <AnimateInView className="text-center mb-16">
            <span className="inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider mb-4"
              style={{ backgroundColor: "rgba(56,189,248,0.12)", color: "var(--color-brand-accent-blue)", border: "1px solid rgba(56,189,248,0.25)" }}
            >
              🛡 {c.interceptTitle}
            </span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.interceptDesc}</h2>
          </AnimateInView>

          <AnimateInView
            className="relative mx-auto rounded-xl overflow-hidden"
            delay={0.2}
            style={{
              maxWidth: "800px",
              background: "var(--color-brand-bg-primary)",
              border: "1px solid var(--color-brand-border)",
            }}
          >
            <svg viewBox="0 0 800 360" className="w-full h-auto" style={{ overflow: "visible" }}>
              <g className="animate-float" style={{ transformOrigin: "140px 180px" }}>
                <rect x="60" y="130" width="160" height="80" rx="16" fill="var(--color-brand-bg-tertiary)"
                  stroke="var(--color-brand-border)" strokeWidth="1.5" />
                <text x="140" y="168" textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-primary)" fontSize="20" fontWeight="700">Agent</text>
                <text x="140" y="188" textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-muted)" fontSize="13">action →</text>
              </g>
              <line x1="220" y1="170" x2="340" y2="170" stroke="var(--color-brand-accent-cyan)" strokeWidth="2"
                strokeDasharray="6 4" className="dash-flow" />
              <polygon points="340,170 332,164 332,176" fill="var(--color-brand-accent-cyan)" />
              <g>
                <rect x="340" y="85" width="200" height="170" rx="20" fill="var(--color-brand-bg-tertiary)"
                  stroke="var(--color-brand-accent-blue)" strokeWidth="2.5" />
                <text x="440" y={isSmall ? 130 : 125} textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-accent-blue)" fontSize="22" fontWeight="800">MAREF</text>
                <text x="440" y={isSmall ? 150 : 145} textAnchor="middle" dominantBaseline="central"
                  fill="var(--color-brand-text-muted)" fontSize="12">{c.interceptLabel}</text>
                <line x1="360" y1="165" x2="520" y2="165" stroke="var(--color-brand-border)" strokeWidth="1" />
                {["1. Identity", "2. Policy", "3. Audit"].map((item, i) => (
                  <g key={i}>
                    <rect x="360" y={175 + i * 24} width="160" height="20" rx="6"
                      fill="rgba(56,189,248,0.08)" stroke="rgba(56,189,248,0.15)" strokeWidth="1" />
                    <text x="440" y={185 + i * 24} textAnchor="middle" dominantBaseline="central"
                      fill="var(--color-brand-accent-cyan)" fontSize="11" fontWeight="600">{item}</text>
                  </g>
                ))}
              </g>
              <line x1="540" y1="170" x2="650" y2="170" stroke="var(--color-brand-accent-green)" strokeWidth="2"
                strokeDasharray="6 4" className="dash-flow"
                style={{ animationDelay: "1.5s" }} />
              <polygon points="650,170 642,164 642,176" fill="var(--color-brand-accent-green)" />
              <rect x="650" y="110" width="130" height="120" rx="12" fill="var(--color-brand-bg-tertiary)"
                stroke="var(--color-brand-accent-green)" strokeWidth="1.5" />
              <text x="715" y="160" textAnchor="middle" dominantBaseline="central"
                fill="var(--color-brand-text-primary)" fontSize="14" fontWeight="700">{c.problemTarget}</text>
              <text x="715" y="185" textAnchor="middle" dominantBaseline="central"
                fill="var(--color-brand-accent-green)" fontSize="13" fontWeight="600">✅ ALLOW (safe)</text>
              <text x="715" y="205" textAnchor="middle" dominantBaseline="central"
                fill="var(--color-brand-text-muted)" fontSize="11">⚡ 8ms decision</text>
              <rect x="330" y="75" width="220" height="190" rx="24" fill="none"
                stroke="var(--color-brand-accent-blue)" strokeWidth="1" opacity="0.2"
                className="animate-pulse-glow" />
            </svg>
          </AnimateInView>
        </div>
      </section>

      {/* Scene 3: The Pipeline */}
      <section className="py-24 px-6" style={{ background: "var(--color-brand-bg-primary)" }}>
        <div className="mx-auto max-w-(--content-max)">
          <AnimateInView className="text-center mb-16">
            <span className="inline-block rounded-full px-3 py-1 text-xs font-semibold tracking-widest uppercase mb-4"
              style={{ backgroundColor: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)", color: "var(--color-brand-accent-purple)" }}
            >
              ⚡ {c.pipelineTitle}
            </span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.pipelineDesc}</h2>
          </AnimateInView>

          <div className="grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {[
              { label: c.stage1Label, desc: c.stage1Desc, icon: "🔑", delay: 0 },
              { label: c.stage2Label, desc: c.stage2Desc, icon: "📋", delay: 0.15 },
              { label: c.stage3Label, desc: c.stage3Desc, icon: "🔐", delay: 0.3 },
            ].map((stage, i) => (
              <AnimateInView
                key={i}
                className="relative rounded-xl p-8 text-center"
                delay={stage.delay}
                duration={0.5}
                style={{
                  background: "var(--color-brand-bg-secondary)",
                  border: "1px solid var(--color-brand-border)",
                }}
              >
                <div className="text-3xl mb-4">{stage.icon}</div>
                <h3 className="text-lg font-bold text-brand-text-primary mb-2">{stage.label}</h3>
                <p className="text-sm text-brand-text-muted leading-relaxed">{stage.desc}</p>
                {i < 2 && (
                  <div className="hidden md:block absolute -right-4 top-1/2 -translate-y-1/2 z-10">
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="var(--color-brand-accent-cyan)" opacity="0.4">
                      <polygon points="10,4 16,10 10,16" />
                    </svg>
                  </div>
                )}
              </AnimateInView>
            ))}
          </div>
        </div>
      </section>

      {/* Scene 4: The Result */}
      <section className="py-24 px-6" style={{ background: "var(--color-brand-bg-secondary)" }}>
        <div className="mx-auto max-w-(--content-max)">
          <AnimateInView className="text-center mb-16">
            <span className="inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wider mb-4"
              style={{ backgroundColor: "rgba(16,185,129,0.12)", color: "var(--color-brand-accent-green)", border: "1px solid rgba(16,185,129,0.25)" }}
            >
              ✅ {c.resultTitle}
            </span>
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.resultDesc}</h2>
          </AnimateInView>

          <div className="grid md:grid-cols-2 gap-8 max-w-4xl mx-auto">
            <AnimateInView
              className="rounded-xl p-8"
              x={-30}
              y={0}
              duration={0.5}
              style={{
                background: "rgba(16,185,129,0.06)",
                border: "1px solid rgba(16,185,129,0.25)",
              }}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg"
                  style={{ background: "rgba(16,185,129,0.15)" }}>✅</div>
                <div>
                  <h3 className="text-xl font-bold" style={{ color: "var(--color-brand-accent-green)" }}>{c.allowLabel}</h3>
                  <p className="text-sm text-brand-text-muted">{c.allowSubtitle}</p>
                </div>
              </div>
              <div className="rounded-lg p-4 font-code text-sm" style={{ background: "var(--color-brand-bg-code)" }}>
                <div style={{ color: "var(--color-brand-accent-green)" }}>
                  {"{ "}<br />
                  &nbsp;&nbsp;"decision": "ALLOW",<br />
                  &nbsp;&nbsp;"verifier": "zero_trust",<br />
                  &nbsp;&nbsp;"signed": "0x3a7b...",<br />
                  &nbsp;&nbsp;"duration_ms": 8<br />
                  {"}"}
                </div>
              </div>
            </AnimateInView>

            <AnimateInView
              className="rounded-xl p-8"
              x={30}
              y={0}
              delay={0.15}
              duration={0.5}
              style={{
                background: "rgba(239,68,68,0.06)",
                border: "1px solid rgba(239,68,68,0.25)",
              }}
            >
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg"
                  style={{ background: "rgba(239,68,68,0.15)" }}>🚫</div>
                <div>
                  <h3 className="text-xl font-bold" style={{ color: "#ef4444" }}>{c.blockLabel}</h3>
                  <p className="text-sm text-brand-text-muted">{c.blockSubtitle}</p>
                </div>
              </div>
              <div className="rounded-lg p-4 font-code text-sm" style={{ background: "var(--color-brand-bg-code)" }}>
                <div style={{ color: "#ef4444" }}>
                  {"{ "}<br />
                  &nbsp;&nbsp;"decision": "BLOCK",<br />
                  &nbsp;&nbsp;"reason": "risk_score &gt; 0.85",<br />
                  &nbsp;&nbsp;"intercepted_by": "safety_gate",<br />
                  &nbsp;&nbsp;"duration_ms": 12<br />
                  {"}"}
                </div>
              </div>
            </AnimateInView>
          </div>
        </div>
      </section>

      {/* Scene 5: Before vs After */}
      <section className="py-24 px-6" style={{ background: "var(--color-brand-bg-primary)" }}>
        <div className="mx-auto max-w-(--content-max)">
          <AnimateInView className="text-center mb-16">
            <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.comparisonTitle}</h2>
            <p className="text-lg text-brand-text-secondary max-w-2xl mx-auto">{c.comparisonDesc}</p>
          </AnimateInView>

          <div className="relative grid md:grid-cols-2 gap-0 max-w-5xl mx-auto rounded-xl overflow-hidden"
            style={{ border: "1px solid var(--color-brand-border)" }}>
            <div className="p-8" style={{ background: "rgba(239,68,68,0.04)" }}>
              <h3 className="text-lg font-bold mb-6 flex items-center gap-2" style={{ color: "#ef4444" }}>
                <span className="text-xl">✗</span> {c.beforeTitle}
              </h3>
              <ul className="space-y-4">
                {[c.beforeItem1, c.beforeItem2, c.beforeItem3].map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 text-sm"
                    style={{
                      opacity: 0,
                      animation: `fade-in 0.3s ease-out ${0.1 * i + 0.2}s forwards`,
                    }}
                  >
                    <span className="text-red-500 mt-0.5 shrink-0">✗</span>
                    <span className="text-brand-text-secondary">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="p-8" style={{ background: "rgba(16,185,129,0.04)" }}>
              <h3 className="text-lg font-bold mb-6 flex items-center gap-2" style={{ color: "var(--color-brand-accent-green)" }}>
                <span className="text-xl">✓</span> {c.afterTitle}
              </h3>
              <ul className="space-y-4">
                {[c.afterItem1, c.afterItem2, c.afterItem3].map((item, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 text-sm"
                    style={{
                      opacity: 0,
                      animation: `fade-in 0.3s ease-out ${0.1 * i + 0.35}s forwards`,
                    }}
                  >
                    <span className="text-green-500 mt-0.5 shrink-0">✓</span>
                    <span className="text-brand-text-secondary">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="hidden md:block absolute left-1/2 top-0 bottom-0 w-px"
              style={{ background: "var(--color-brand-border)" }} />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section
        className="py-24 px-6 text-center"
        style={{ background: "var(--color-brand-bg-secondary)" }}
      >
        <div className="mx-auto max-w-(--content-max)">
          <h2 className="text-3xl md:text-5xl font-bold tracking-tight mb-4">{c.ctaTitle}</h2>
          <p className="text-lg text-brand-text-secondary max-w-xl mx-auto mb-8">
            {c.ctaDesc}
          </p>
          <div className="inline-flex items-center gap-2 rounded-cards px-6 py-3 mb-10 font-code text-sm"
            style={{ background: "var(--color-brand-bg-code)", border: "1px solid var(--color-brand-border)" }}>
            <span style={{ color: "var(--color-brand-accent-green)" }}>$</span>
            <span>pip install maref</span>
            <button
              onClick={() => navigator.clipboard?.writeText("pip install maref")}
              className="ml-2 text-fog-veil hover:text-snow-sheet transition-colors"
              aria-label="Copy"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="4" y="4" width="10" height="10" rx="2" />
                <path d="M2 12V2h10" />
              </svg>
            </button>
          </div>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <a
              href={`/${locale}/docs/quickstart/`}
              className="inline-flex items-center gap-2 rounded-buttons px-6 py-3 font-semibold text-xs uppercase tracking-wider transition-all hover:opacity-90"
              style={{ background: "var(--gradient-current)", color: "var(--surface-trench)" }}
            >
              {c.ctaQuickstart} →
            </a>
            <a
              href="https://github.com/maref-org/maref"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-buttons px-6 py-3 font-medium text-base transition-all hover:opacity-90 border"
              style={{ borderColor: "var(--color-brand-border)", color: "var(--color-brand-text-primary)" }}
            >
              ★ {c.ctaStar}
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
