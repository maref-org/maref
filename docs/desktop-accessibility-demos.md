# Desktop Accessibility API — Real Demos

> **Prerequisites:** macOS 12+, Accessibility permissions granted for Terminal/IDE.
> **Zero dependencies:** No GPU, no ML models, no new pip installs.

## Demo 1: Find current window elements

```bash
python3 -c "
from maref.desktop.accessibility_parser import AccessibilityParser
p = AccessibilityParser()
p.initialize()
r = p.parse()
print(f'Found {len(r.elements)} elements in {r.parse_time_ms:.0f}ms')
for e in r.elements[:10]:
    print(f'  {e.element_type.value:15s} \"{e.text[:40]:40s}\" at ({e.bbox.x}, {e.bbox.y}) {e.bbox.width}x{e.bbox.height}')
"
```

Expected output: Lists real UI elements from the frontmost window with types, positions, and sizes.

## Demo 2: Find text fields (e.g., Safari URL bar)

```bash
python3 -c "
from maref.desktop.accessibility_parser import AccessibilityParser
p = AccessibilityParser()
p.initialize()
r = p.parse()
text_fields = [e for e in r.elements if e.element_type.value == 'text_field']
print(f'Found {len(text_fields)} text fields')
for tf in text_fields:
    print(f'  \"{tf.text}\" at ({tf.bbox.x}, {tf.bbox.y})')
"
```

Expected output: Shows real text fields with their screen positions.

## Demo 3: DesktopAgent E2E with accessibility backend

```bash
python3 -c "
from maref.desktop.agent import DesktopAgent
agent = DesktopAgent(dry_run=True)
env = agent.check_environment()
print(f'Parser backend: {env[\"parser_actual_backend\"]}')
result = agent.parse_screen()
print(f'Found {len(result.elements)} elements')
interactive = [e for e in result.elements if e.is_interactive]
print(f'Interactive: {len(interactive)}')
for el in interactive[:5]:
    print(f'  {el.element_type.value}: \"{el.text[:30]}\" center={el.bbox.center}')
"
```

Expected output: Shows DesktopAgent successfully parsing real UI via accessibility API with interactive elements identified.
