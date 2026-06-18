import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';
import Translate, {translate} from '@docusaurus/Translate';

function Mission(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2><Translate id="about.mission">Mission</Translate></h2>
        <p>
          <Translate id="about.mission.text">
            MAREF makes multi-agent AI systems provably safe. Not "we hope it's safe" — provably safe, using TLA+ formal verification, Lyapunov stability analysis, and cryptographic audit trails.
          </Translate>
        </p>
      </div>
    </section>
  );
}

function WhyGovernanceFirst(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2><Translate id="about.whyGovernanceFirst">Why governance-first?</Translate></h2>
        <p>
          <Translate id="about.whyGovernanceFirst.text">
            88% of organizations already had an AI agent security incident. 94% don't have a mature strategy. Companies spend 17x more on AI-powered security than on securing AI itself. MAREF closes that gap — not by slowing development, but by putting guardrails in place.
          </Translate>
        </p>
        <div className="alert alert--info">
          <Translate id="about.statCheck" values={{strong: <strong>Stat check</strong>}}>
            {'{strong} — 88% incident rate, 94% no mature strategy, 17x spending gap.'}
          </Translate>
        </div>
      </div>
    </section>
  );
}

function Differentiators(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2><Translate id="about.differentiators">Key differentiators</Translate></h2>
        <ul>
          <li>
            <Translate id="about.diff.tla" values={{strong: <strong>TLA+ formal verification</strong>}}>
              {'{strong} — every governance state transition is mathematically proven'}
            </Translate>
          </li>
          <li>
            <Translate id="about.diff.defense" values={{strong: <strong>8-layer defense architecture</strong>}}>
              {'{strong} — defense in depth as the architecture, not a feature'}
            </Translate>
          </li>
          <li>
            <Translate id="about.diff.evolution" values={{strong: <strong>Recursive self-evolution</strong>}}>
              {'{strong} — system gets provably safer over time (FNR -60% over 200 rounds)'}
            </Translate>
          </li>
          <li>
            <Translate id="about.diff.zeroTrust" values={{strong: <strong>Zero-trust identity per agent</strong>}}>
              {'{strong} — Ed25519 signing for every decision'}
            </Translate>
          </li>
          <li>
            <Translate id="about.diff.crypto" values={{strong: <strong>National-grade cryptography</strong>}}>
              {'{strong} — SM2/SM3/SM4-GCM (GB/T 32918)'}
            </Translate>
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
        <h2><Translate id="about.projectStatus">Project status</Translate></h2>
        <p>
          <Translate id="about.projectStatus.text" values={{link: <a href="https://github.com/maref-org/maref">github.com/maref-org/maref</a>}}>
            {'Active development under Apache 2.0. 4,300+ tests, 82% code coverage. Available at {link}.'}
          </Translate>
        </p>
      </div>
    </section>
  );
}

function Contact(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2><Translate id="about.contact">Contact</Translate></h2>
        <p>
          <Translate id="about.contact.text" values={{email: <a href="mailto:contact@maref.org">contact@maref.org</a>}}>
            {'Technical support and general inquiries: {email}.'}
          </Translate>
        </p>
      </div>
    </section>
  );
}

export default function About(): React.ReactElement {
  return (
    <Layout
      title={translate({id: 'about.title', message: 'About MAREF'})}
      description={translate({id: 'about.description', message: 'MAREF — Multi-Agent Recursive Evolution Framework. Provably safe multi-agent AI governance via TLA+ formal verification, Lyapunov stability analysis, and cryptographic audit trails.'})}
    >
      <header className="hero hero--primary">
        <div className="container">
          <h1 className="hero__title"><Translate id="about.title">About MAREF</Translate></h1>
          <p className="hero__subtitle">
            <Translate id="about.subtitle">Multi-Agent Recursive Evolution Framework</Translate>
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
          <Link to="/"><Translate id="about.backToHome">Back to Home</Translate></Link>
        </div>
      </main>
    </Layout>
  );
}
