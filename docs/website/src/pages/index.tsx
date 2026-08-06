import React from 'react';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import HomepageHeader from '@site/src/components/HomepageHeader';

export default function Home() {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title="MAREF — Agent Governance OS"
      description="Multi-Agent Recursive Evolution Framework — Formal verification, constitutional governance, self-healing infrastructure for multi-agent systems."
    >
      <main>
        <HomepageHeader />
      </main>
    </Layout>
  );
}
