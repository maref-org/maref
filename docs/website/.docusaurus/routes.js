import React from 'react';
import ComponentCreator from '@docusaurus/ComponentCreator';

export default [
  {
    path: '/zh-CN/about',
    component: ComponentCreator('/zh-CN/about', '38c'),
    exact: true
  },
  {
    path: '/zh-CN/blog',
    component: ComponentCreator('/zh-CN/blog', '4fd'),
    exact: true
  },
  {
    path: '/zh-CN/blog/agent-governance-checklist',
    component: ComponentCreator('/zh-CN/blog/agent-governance-checklist', '61e'),
    exact: true
  },
  {
    path: '/zh-CN/blog/archive',
    component: ComponentCreator('/zh-CN/blog/archive', '2d5'),
    exact: true
  },
  {
    path: '/zh-CN/blog/authors',
    component: ComponentCreator('/zh-CN/blog/authors', 'afa'),
    exact: true
  },
  {
    path: '/zh-CN/blog/from-steadicam-to-agent-governance',
    component: ComponentCreator('/zh-CN/blog/from-steadicam-to-agent-governance', '50c'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags',
    component: ComponentCreator('/zh-CN/blog/tags', 'e31'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/agent-safety',
    component: ComponentCreator('/zh-CN/blog/tags/agent-safety', '2af'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/ai-safety',
    component: ComponentCreator('/zh-CN/blog/tags/ai-safety', '960'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/best-practices',
    component: ComponentCreator('/zh-CN/blog/tags/best-practices', '83c'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/governance',
    component: ComponentCreator('/zh-CN/blog/tags/governance', '3f4'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/marref',
    component: ComponentCreator('/zh-CN/blog/tags/marref', '2fb'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/openclaw',
    component: ComponentCreator('/zh-CN/blog/tags/openclaw', 'e63'),
    exact: true
  },
  {
    path: '/zh-CN/blog/tags/production',
    component: ComponentCreator('/zh-CN/blog/tags/production', '487'),
    exact: true
  },
  {
    path: '/zh-CN/security',
    component: ComponentCreator('/zh-CN/security', 'eba'),
    exact: true
  },
  {
    path: '/zh-CN/terms',
    component: ComponentCreator('/zh-CN/terms', 'd63'),
    exact: true
  },
  {
    path: '/zh-CN/docs',
    component: ComponentCreator('/zh-CN/docs', '039'),
    routes: [
      {
        path: '/zh-CN/docs/0.33',
        component: ComponentCreator('/zh-CN/docs/0.33', '675'),
        routes: [
          {
            path: '/zh-CN/docs/0.33',
            component: ComponentCreator('/zh-CN/docs/0.33', '096'),
            routes: [
              {
                path: '/zh-CN/docs/0.33/api-reference',
                component: ComponentCreator('/zh-CN/docs/0.33/api-reference', 'cf8'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/0.33/architecture',
                component: ComponentCreator('/zh-CN/docs/0.33/architecture', '156'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/0.33/deployment',
                component: ComponentCreator('/zh-CN/docs/0.33/deployment', 'd1f'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/0.33/introduction',
                component: ComponentCreator('/zh-CN/docs/0.33/introduction', '02d'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/0.33/quickstart',
                component: ComponentCreator('/zh-CN/docs/0.33/quickstart', '0b2'),
                exact: true,
                sidebar: "docsSidebar"
              }
            ]
          }
        ]
      },
      {
        path: '/zh-CN/docs/',
        component: ComponentCreator('/zh-CN/docs/', '5f9'),
        routes: [
          {
            path: '/zh-CN/docs/',
            component: ComponentCreator('/zh-CN/docs/', '6b5'),
            routes: [
              {
                path: '/zh-CN/docs/api-reference',
                component: ComponentCreator('/zh-CN/docs/api-reference', '06d'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/architecture',
                component: ComponentCreator('/zh-CN/docs/architecture', 'bea'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/cookbook/a2a-federation',
                component: ComponentCreator('/zh-CN/docs/cookbook/a2a-federation', '96d'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/cookbook/compliance-audit',
                component: ComponentCreator('/zh-CN/docs/cookbook/compliance-audit', 'afe'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/cookbook/governed-agent-setup',
                component: ComponentCreator('/zh-CN/docs/cookbook/governed-agent-setup', '3b1'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/cookbook/hitl-approval-flow',
                component: ComponentCreator('/zh-CN/docs/cookbook/hitl-approval-flow', '563'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/cookbook/mcp-tool-integration',
                component: ComponentCreator('/zh-CN/docs/cookbook/mcp-tool-integration', '954'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/deployment',
                component: ComponentCreator('/zh-CN/docs/deployment', '38a'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/deployment-docker',
                component: ComponentCreator('/zh-CN/docs/deployment-docker', '615'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/deployment-k8s',
                component: ComponentCreator('/zh-CN/docs/deployment-k8s', '19d'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/deployment-sidecar',
                component: ComponentCreator('/zh-CN/docs/deployment-sidecar', '643'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/error-codes',
                component: ComponentCreator('/zh-CN/docs/error-codes', '7a3'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/integrations/autogen',
                component: ComponentCreator('/zh-CN/docs/integrations/autogen', '751'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/integrations/compatibility-matrix',
                component: ComponentCreator('/zh-CN/docs/integrations/compatibility-matrix', 'cd3'),
                exact: true
              },
              {
                path: '/zh-CN/docs/integrations/crewai',
                component: ComponentCreator('/zh-CN/docs/integrations/crewai', 'b55'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/integrations/dify',
                component: ComponentCreator('/zh-CN/docs/integrations/dify', 'b5c'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/integrations/langgraph',
                component: ComponentCreator('/zh-CN/docs/integrations/langgraph', 'eee'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/introduction',
                component: ComponentCreator('/zh-CN/docs/introduction', '4c6'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/loop-engineering',
                component: ComponentCreator('/zh-CN/docs/loop-engineering', '2f9'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/quickstart',
                component: ComponentCreator('/zh-CN/docs/quickstart', '504'),
                exact: true,
                sidebar: "docsSidebar"
              },
              {
                path: '/zh-CN/docs/reliability',
                component: ComponentCreator('/zh-CN/docs/reliability', '882'),
                exact: true,
                sidebar: "docsSidebar"
              }
            ]
          }
        ]
      }
    ]
  },
  {
    path: '/zh-CN/',
    component: ComponentCreator('/zh-CN/', '22d'),
    exact: true
  },
  {
    path: '*',
    component: ComponentCreator('*'),
  },
];
