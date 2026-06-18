import React from 'react';
import Layout from '@theme/Layout';

function ReportVulnerability() {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Reporting a Vulnerability</h2>
        <div className="alert alert--warning margin-bottom--md">
          Do not open a public GitHub issue for security vulnerabilities.
        </div>
        <p>
          Please report security issues to the MAREF security team via email.
          Include as much detail as possible: affected component, steps to reproduce,
          potential impact, and suggested fix if available.
        </p>
        <p>
          You will receive a response within 48 hours. We will keep you updated on
          the remediation progress and credit you in the security advisory (unless
          you request anonymity).
        </p>
      </div>
    </section>
  );
}

function SupportedVersions() {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Supported Versions</h2>
        <table>
          <thead>
            <tr>
              <th>Version</th>
              <th>Supported</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>0.30.x</td>
              <td>
                <span className="badge badge--success">Active support</span>
              </td>
            </tr>
            <tr>
              <td>0.20.x</td>
              <td>
                <span className="badge badge--warning">Security fixes</span>
              </td>
            </tr>
            <tr>
              <td>&lt; 0.20</td>
              <td>
                <span className="badge badge--danger">End of life</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SecurityArchitecture() {
  const features = [
    {
      title: '4-Level Policy Decision Tree',
      description: '97% automated safety decisions',
    },
    {
      title: 'CircuitBreaker',
      description: '3 consecutive failures trigger automatic lockout',
    },
    {
      title: 'RedactionEngine',
      description: 'Automatic screenshot redaction of sensitive content',
    },
    {
      title: 'AuditLogger',
      description: 'Append-only, HMAC-signed audit trail',
    },
    {
      title: 'TLA+ Formal Verification',
      description: 'Mathematically proven safety properties',
    },
    {
      title: 'DID/VC Identity',
      description: 'Cryptographic agent identity and trust scoring',
    },
  ];

  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Security Architecture</h2>
        <p>
          MAREF implements an <strong>8-layer defense-in-depth</strong> architecture for desktop
          agent security. See the{' '}
          <a href="https://github.com/maref-org/maref/blob/main/docs/MAREF-Security-Whitepaper.md">
            MAREF Security Whitepaper
          </a>{' '}
          for full details.
        </p>
        <div className="row">
          {features.map((f) => (
            <div key={f.title} className="col col--4 margin-bottom--lg">
              <div className="card">
                <div className="card__body">
                  <h4>{f.title}</h4>
                  <p className="margin-bottom--none">{f.description}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function CryptoCompliance() {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Cryptographic Compliance and Export Control</h2>

        <h3>Chinese National Cryptographic Standards</h3>
        <p>
          MAREF includes implementations of Chinese national cryptographic standards
          for compliance with <strong>GB/T 32918</strong> and participation in the{' '}
          <strong>AIP (AI Agent Protocol) Pioneer Program</strong>.
        </p>
        <table>
          <thead>
            <tr>
              <th>Algorithm</th>
              <th>Standard</th>
              <th>Implementation</th>
              <th>File</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>SM2</td>
              <td>GB/T 32918.2-2016</td>
              <td>Elliptic curve public key cryptography</td>
              <td>
                <code>src/maref/crypto/sm2.py</code>
              </td>
            </tr>
            <tr>
              <td>SM3</td>
              <td>GB/T 32918.1-2016</td>
              <td>Cryptographic hash function (256-bit)</td>
              <td>
                <code>src/maref/crypto/sm3.py</code>
              </td>
            </tr>
            <tr>
              <td>SM4-GCM</td>
              <td>GB/T 32907-2016</td>
              <td>Block cipher with authenticated encryption</td>
              <td>
                <code>src/maref/crypto/sm4_gcm.py</code>
              </td>
            </tr>
          </tbody>
        </table>

        <h3>Export Control Notice</h3>
        <div className="alert alert--danger margin-bottom--md">
          The SM2/SM3/SM4-GCM implementations in this repository are subject to
          Chinese cryptographic export control regulations (密码出口管制).
        </div>
        <ul>
          <li>
            <strong>Within China</strong>: Free to use, modify, and distribute under Apache-2.0
          </li>
          <li>
            <strong>Outside China</strong>: Users are responsible for ensuring compliance with
            local cryptographic import/export laws. MAREF provides these algorithms
            for interoperability and standards compliance only.
          </li>
          <li>
            <strong>Dual-use</strong>: These algorithms are classified as dual-use technology
            under Wassenaar Arrangement Category 5 Part 2. Users in jurisdictions
            with export control restrictions must obtain appropriate licenses before
            redistribution.
          </li>
        </ul>

        <h3>Disclaimer</h3>
        <div className="alert alert--info">
          MAREF is an open-source reference implementation. The inclusion of SM2/SM3/SM4
          does not constitute an official endorsement by Chinese regulatory bodies.
          Users must conduct their own compliance assessment for production deployments.
        </div>
      </div>
    </section>
  );
}

function BestPractices() {
  const practices = [
    'Always run with MAREF_SAFETY_LEVEL=production',
    'Enable all 8 defense layers (they are on by default)',
    'Grant only the minimum required OS permissions',
    'Review audit logs regularly (maref audit show --last 100)',
    'Monitor CircuitBreaker trip rate via Prometheus',
    'Keep dependencies updated (pip list --outdated)',
  ];

  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>Security Best Practices</h2>
        <p>When deploying MAREF in production:</p>
        <ol>
          {practices.map((p, i) => (
            <li key={i}>
              <p>{p}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

export default function Security(): React.ReactElement {
  return (
    <Layout
      title="Security — MAREF"
      description="MAREF security vulnerability disclosure policy, supported versions, security architecture, cryptographic compliance, and best practices."
    >
      <header className="hero hero--primary">
        <div className="container">
          <h1 className="hero__title">Security</h1>
          <p className="hero__subtitle">
            Vulnerability disclosure, supported versions, architecture, and best practices
          </p>
        </div>
      </header>
      <main>
        <ReportVulnerability />
        <SupportedVersions />
        <SecurityArchitecture />
        <CryptoCompliance />
        <BestPractices />
      </main>
    </Layout>
  );
}
