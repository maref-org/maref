import React from 'react';
import Layout from '@theme/Layout';

function Acceptance(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>1. Acceptance of Terms</h2>
        <p>
          By accessing or using MAREF (the "Software"), you agree to be bound by these
          Terms of Service. If you do not agree, you may not use the Software.
        </p>
        <p>
          These terms may be updated at any time. Continued use after changes constitutes
          acceptance of the revised terms.
        </p>
      </div>
    </section>
  );
}

function License(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>2. Open Source License</h2>
        <p>
          MAREF is licensed under the{' '}
          <a href="https://www.apache.org/licenses/LICENSE-2.0">
            Apache License, Version 2.0
          </a>
          . You may use, modify, and distribute the Software in compliance with the
          terms of that license.
        </p>
        <p>
          A copy of the license is included in the{' '}
          <code>LICENSE</code> file at the root of the repository.
        </p>
      </div>
    </section>
  );
}

function NoWarranty(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>3. No Warranty</h2>
        <div className="alert alert--danger margin-bottom--md">
          THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
          IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
          FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.
        </div>
        <p>
          MAREF is an experimental research framework. It is not certified for use in
          safety-critical systems, including but not limited to medical devices,
          autonomous vehicles, or financial infrastructure, unless expressly approved
          in writing by the MAREF governance board.
        </p>
      </div>
    </section>
  );
}

function LimitationOfLiability(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>4. Limitation of Liability</h2>
        <div className="alert alert--danger margin-bottom--md">
          IN NO EVENT SHALL THE MAREF CONTRIBUTORS BE LIABLE FOR ANY CLAIM, DAMAGES,
          OR OTHER LIABILITY ARISING FROM THE USE OF THE SOFTWARE.
        </div>
        <p>
          This limitation applies to all theories of liability, whether in contract,
          tort, or otherwise. Contributors are not responsible for any damages,
          including direct, indirect, incidental, consequential, or punitive damages,
          arising from your use of the Software.
        </p>
      </div>
    </section>
  );
}

function GoverningLaw(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>5. Governing Law</h2>
        <p>
          These terms are governed by the laws of the People's Republic of China.
          Any disputes arising from the use of MAREF shall be resolved through
          friendly consultation. If consultation fails, disputes shall be submitted
          to the competent court in the jurisdiction of the project's primary
          maintainers.
        </p>
        <p>
          Nothing in these terms restricts your rights under applicable consumer
          protection laws where you reside.
        </p>
      </div>
    </section>
  );
}

function Contact(): JSX.Element {
  return (
    <section className="margin-vert--lg">
      <div className="container">
        <h2>6. Contact</h2>
        <p>
          For questions about these Terms of Service or the MAREF project, please
          contact us at{' '}
          <a href="mailto:legal@maref.org">legal@maref.org</a>.
        </p>
      </div>
    </section>
  );
}

export default function Terms(): React.ReactElement {
  return (
    <Layout
      title="Terms of Service — MAREF"
      description="MAREF Terms of Service — acceptance, license, warranty disclaimer, liability limitation, governing law, and contact information."
    >
      <header className="hero hero--primary">
        <div className="container">
          <h1 className="hero__title">Terms of Service</h1>
          <p className="hero__subtitle">
            Last updated: June 18, 2026
          </p>
        </div>
      </header>
      <main>
        <Acceptance />
        <License />
        <NoWarranty />
        <LimitationOfLiability />
        <GoverningLaw />
        <Contact />
      </main>
    </Layout>
  );
}
