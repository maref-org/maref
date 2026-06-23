import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import styles from './HomepageHeader.module.css';

const features = [
  {
    icon: '🔐',
    title: 'Formal Verification',
    description: 'TLA+ proven invariants with 64-state Gray-code FSM ensuring Hamming distance=1 transition stability across all governance layers.',
  },
  {
    icon: '⚖️',
    title: 'Constitutional Governance',
    description: '5 immutable constitutional red lines enforced by MetaAgentClosure with RuleFreezeZone write protection and recursive meta-governance.',
  },
  {
    icon: '🔄',
    title: 'Self-Healing',
    description: '8 Self-* modules (Observer, Diagnostician, Healer, Optimizer, Architect, Executor, Knowledge, Version) for autonomous system recovery.',
  },
  {
    icon: '🌐',
    title: 'A2A Protocol',
    description: 'Google-standard Agent-to-Agent protocol with signed agent cards, capability-based discovery, JSON-RPC 2.0 task delegation, and state push notifications.',
  },
  {
    icon: '🔌',
    title: 'MCP Gateway',
    description: 'Anthropic-standard Model Context Protocol with 6 transport types, policy engine, circuit breaker, and three-tier trust authorization for tool calls.',
  },
  {
    icon: '📋',
    title: 'Compliance',
    description: 'HMAC-SHA256 tamper-evident audit trails, EU AI Act, SOC 2, HIPAA, PCI-DSS compliance modules with automated report generation and data sovereignty enforcement.',
  },
];

function FeatureCard({icon, title, description}: {icon: string; title: string; description: string}) {
  return (
    <div className="col col--4 margin-bottom--lg">
      <div className="feature-card">
        <span className="feature-icon">{icon}</span>
        <h3 className="feature-title">{title}</h3>
        <p className="feature-description">{description}</p>
      </div>
    </div>
  );
}

export default function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <header className="hero hero--primary">
      <div className="container">
        <div className="hero__content">
          <h1 className="hero__title">Agent Governance OS</h1>
          <p className="hero__subtitle">
            MAREF provides formal verification, constitutional governance, self-healing infrastructure,
            dual-protocol communication (A2A + MCP), and comprehensive compliance for multi-agent systems.
          </p>
          <div className={clsx('cta-section', styles.ctaRow)}>
            <Link className="cta-button primary" to="/docs/introduction">
              Get Started →
            </Link>
            <Link className="cta-button secondary" to="https://github.com/maref-org/maref">
              GitHub
            </Link>
          </div>
          <div className={styles.versionInfo}>
            <span className="version-badge">v0.34.0-rc</span>
            <span className={styles.license}>Apache-2.0</span>
            <span className={styles.platforms}>Python · Electron · TLA+</span>
          </div>
        </div>
      </div>
      <div className="features-section">
        <div className="container">
          <div className="row">
            {features.map((f, i) => (
              <FeatureCard key={i} {...f} />
            ))}
          </div>
        </div>
      </div>
    </header>
  );
}
