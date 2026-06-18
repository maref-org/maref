import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';

function Mission(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Mission</h2>
        <p>
          MAREF makes multi-agent AI systems provably safe. Not "we hope it's safe"
          — provably safe, using TLA+ formal verification, Lyapunov stability
          analysis, and cryptographic audit trails.
        </p>
      </div>
    </section>
  );
}

function WhyGovernanceFirst(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Why governance-first?</h2>
        <p>
          88% of organizations already had an AI agent security incident. 94%
          don't have a mature strategy. Companies spend 17x more on AI-powered
          security than on securing AI itself. MAREF closes that gap — not by
          slowing development, but by putting guardrails in place.
        </p>
        <div className="alert alert--info">
          <strong>Stat check</strong> — 88% incident rate, 94% no mature
          strategy, 17x spending gap.
        </div>
      </div>
    </section>
  );
}

function Differentiators(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Key differentiators</h2>
        <ul>
          <li>
            <strong>TLA+ formal verification</strong> — every governance state
            transition is mathematically proven
          </li>
          <li>
            <strong>8-layer defense architecture</strong> — defense in depth as
            the architecture, not a feature
          </li>
          <li>
            <strong>Recursive self-evolution</strong> — system gets provably
            safer over time (FNR -60% over 200 rounds)
          </li>
          <li>
            <strong>Zero-trust identity per agent</strong> — Ed25519 signing for
            every decision
          </li>
          <li>
            <strong>National-grade cryptography</strong> — SM2/SM3/SM4-GCM (GB/T
            32918)
          </li>
        </ul>
      </div>
    </section>
  );
}

function ProjectStatus(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Project status</h2>
        <p>
          Active development under Apache 2.0. 4,300+ tests, 82% code coverage.
          Available at{' '}
          <a href="https://github.com/maref-org/maref">
            github.com/maref-org/maref
          </a>
          .
        </p>
      </div>
    </section>
  );
}

function Contact(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Contact</h2>
        <p>
          Technical support and general inquiries:{' '}
          <a href="mailto:contact@maref.org">contact@maref.org</a>.
        </p>
      </div>
    </section>
  );
}

export default function About(): React.ReactElement {
  return (
    <Layout
      title="About MAREF"
      description="MAREF — Multi-Agent Recursive Evolution Framework. Provably safe multi-agent AI governance via TLA+ formal verification, Lyapunov stability analysis, and cryptographic audit trails."
    >
      <header className="hero hero--primary">
        <div className="container">
          <h1 className="hero__title">About MAREF</h1>
          <p className="hero__subtitle">
            Multi-Agent Recursive Evolution Framework
          </p>
        </div>
      </header>
      <main className="margin-vert--xl">
        <Mission />
        <WhyGovernanceFirst />
        <Differentiators />
        <ProjectStatus />
        <Contact />
        <div className="container margin-vert--lg">
          <Link to="/">Back to Home</Link>
        </div>
      </main>
    </Layout>
  );
}
