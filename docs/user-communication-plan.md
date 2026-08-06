# MAREF User Communication Plan

## Pre-Release (T-7d to T-0)
- GitHub Issue announcing release timeline
- CHANGELOG.md updated with all changes since last release
- Breaking changes documented in `UPGRADING.md`

## Release Day (T-0)
- GitHub Release with full changelog
- PyPI package published
- Docker images pushed
- Social media announcement across channels

## Post-Release (T+0 to T+30d)
- GitHub Discussion thread for feedback
- Issue template for bug reports
- Weekly triage of community issues
- Release retrospective at T+30d

## Communication Channels

| Channel | Purpose | Frequency |
|---------|---------|-----------|
| GitHub Issues | Bug reports, feature requests | Continuous |
| GitHub Discussions | Community Q&A, feedback | Continuous |
| Twitter/X | Announcements, updates | Per-release |
| Discord | Real-time support, community | Continuous |

## Escalation

| Severity | Response Time | Channel |
|----------|---------------|---------|
| P0 (security) | 24h | GitHub Security Advisory |
| P1 (critical bug) | 72h | GitHub Issue + Release |
| P2 (feature request) | Next release | GitHub Discussion |
