# Legacy website snapshot — not a deployment source

This directory is a **stale copy** of the maref.cc site, kept for historical reference only.

- No workflow builds or deploys anything under `website/`.
- The live site is maintained and deployed from the maintainers' separate source repository.
- Deploying from this directory would roll the live site back to an older state.

The documentation site is separate: `docs/website` builds and deploys to the Cloudflare Pages
project `maref-docs` via `.github/workflows/deploy-website.yml`.

> 本目录是 maref.cc 的过期快照，仅作历史参考。切勿从此处部署——线上站点由维护者的独立源码仓库构建。
