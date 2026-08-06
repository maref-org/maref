# Brand Building Skills for MAREF Marketplace

> **Origin**: Adapted from [arnabbagxd/Brand-building-skills](https://github.com/arnabbagxd/Brand-building-skills) (15 skills) — refactored as MAREF SkillManifest for the federated marketplace.
> **License**: Apache-2.0 (both original and this adaptation)
> **Status**: W1 deliverable — pending three-gate admission (static scan → sandbox test → manual review)

## Why Brand Building Skills?

These skills serve a dual purpose:
1. **Marketplace bootstrap** — First-party skills that populate the MAREF marketplace with real content (solving the cold-start problem)
2. **MAREF's own brand positioning** — MAREF uses these skills to maintain its own brand positioning (eating our own dog food)

## Skill Dependency Graph

```
maref-brand-context (foundation — stores brand DNA)
    ↓
maref-competitor-branding (maps competitive landscape)
    ↓
maref-brand-positioning (generates positioning statement)
    ↓
maref-target-audience (segments audience)
    ↓
maref-messaging-framework (translates positioning to messaging)
```

## Skills

| Skill | Version | Dependencies | Entrypoint |
|-------|---------|-------------|-----------|
| [maref-brand-context](manifests/maref-brand-context.yaml) | 1.0.0 | none | `skills.brand_building.brand_context:get_dna` |
| [maref-competitor-branding](manifests/maref-competitor-branding.yaml) | 1.0.0 | `skill://maref-brand-context@1.0.0` | `skills.brand_building.competitor_branding:map` |
| [maref-brand-positioning](manifests/maref-brand-positioning.yaml) | 1.0.0 | `skill://maref-competitor-branding@1.0.0` | `skills.brand_building.brand_positioning:generate` |
| [maref-target-audience](manifests/maref-target-audience.yaml) | 1.0.0 | `skill://maref-brand-positioning@1.0.0` | `skills.brand_building.target_audience:segment` |
| [maref-messaging-framework](manifests/maref-messaging-framework.yaml) | 1.0.0 | `skill://maref-brand-positioning@1.0.0`, `skill://maref-target-audience@1.0.0` | `skills.brand_building.messaging:translate` |

## Framework Basis

These skills encode the **April Dunford 5+1 positioning framework**:
1. Competitive alternatives (what would customers do without you?)
2. Unique attributes (what only you have)
3. Value proof (how attributes deliver value)
4. Character (who you are)
5. Market category (what frame you compete in)
6. +1: Target audience (who cares most)

## Usage

```python
from maref.marketplace.registry import SkillRegistry

registry = SkillRegistry()

# Register all 5 skills (manifests loaded from YAML)
import yaml
for skill_name in ["brand-context", "competitor-branding", "brand-positioning", "target-audience", "messaging-framework"]:
    with open(f"docs/skills/brand-building/manifests/maref-{skill_name}.yaml") as f:
        data = yaml.safe_load(f)
    from maref.marketplace.registry import SkillManifest
    manifest = SkillManifest(**data)
    registry.register(manifest)

# Run three gates for each
for manifest in registry.list_all():
    registry.run_static_scan(manifest.skill_id)
    registry.run_sandbox_test(manifest.skill_id)
    registry.approve(manifest.skill_id)

# Use brand-positioning skill
positioning_skill = registry.get_by_name("maref-brand-positioning")
print(positioning_skill.description)
```

## Three-Gate Admission Status

| Skill | Static Scan | Sandbox Test | Manual Review | Status |
|-------|------------|-------------|---------------|--------|
| maref-brand-context | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-competitor-branding | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-brand-positioning | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-target-audience | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |
| maref-messaging-framework | ⏳ Pending | ⏳ Pending | ⏳ Pending | PENDING |

> **Discipline**: All 5 skills must pass the full three-gate admission before becoming `APPROVED`. No shortcuts.

## Attribution

- **Original work**: [arnabbagxd/Brand-building-skills](https://github.com/arnabbagxd/Brand-building-skills) — 15 Agent Skills for brand positioning
- **Adaptation**: Refactored from Agent Skills format (Markdown + YAML frontmatter) to MAREF SkillManifest format (structured YAML with input/output schema, dependencies, sandbox config, test cases)
- **Framework basis**: April Dunford's positioning framework as described in "Obviously Awesome"
- **License**: Apache-2.0 (compatible with original)
