import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docsSidebar: [
    {
      type: 'doc',
      id: 'introduction',
      label: 'Introduction',
    },
    {
      type: 'doc',
      id: 'quickstart',
      label: 'Quickstart',
    },
    {
      type: 'doc',
      id: 'architecture',
      label: 'Architecture',
    },
    {
      type: 'doc',
      id: 'api-reference',
      label: 'API Reference',
    },
    {
      type: 'category',
      label: 'Cookbook',
      items: [
        'cookbook/governed-agent-setup',
        'cookbook/a2a-federation',
        'cookbook/mcp-tool-integration',
        'cookbook/hitl-approval-flow',
        'cookbook/compliance-audit',
      ],
    },
    {
      type: 'category',
      label: 'Integrations',
      items: [
        'integrations/langgraph',
        'integrations/crewai',
        'integrations/autogen',
        'integrations/dify',
      ],
    },
    {
      type: 'doc',
      id: 'deployment',
      label: 'Deployment',
    },
  ],
};

export default sidebars;
