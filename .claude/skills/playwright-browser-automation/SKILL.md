---
name: playwright-browser-automation
description: >
  Browser automation using Playwright MCP. Use this skill when the user asks to 
  test a web page, validate UI behavior, fill forms, take screenshots, verify 
  responsive design, check links, or automate any browser-based task. This skill 
  works with the pre-installed Playwright MCP server (microsoft/playwright-mcp).
---

# Playwright Browser Automation Skill

## Overview

You have access to browser automation through **Playwright MCP** (pre-installed). 
This provides AI-driven browser control using the Accessibility Tree (not screenshots),
making it token-efficient and deterministic.

## Pre-configured MCP Server

The Playwright MCP server is already configured and accessible through:
- `npx @playwright/mcp@latest`
- Available tools: browser_navigate, browser_click, browser_fill, browser_snapshot, etc.

## Core Workflow

1. **Navigate**: `browser_navigate` to target URL
2. **Snapshot**: `browser_snapshot` to get accessibility tree (element refs like @e1, @e2)
3. **Analyze**: Review snapshot to find element refs for interaction
4. **Interact**: Use element refs with `browser_click`, `browser_fill`, etc.
5. **Verify**: Take `browser_screenshot` or new `browser_snapshot` to verify result
6. **Repeat**: Continue the snapshot → decision → action cycle

## Key Tools (via Playwright MCP)

### Navigation
- `browser_navigate` — Go to a URL
- `browser_go_back` / `browser_go_forward` — History navigation
- `browser_refresh` — Reload page

### Interaction
- `browser_click @eN` — Click element by ref from snapshot
- `browser_fill @eN "text"` — Fill input field
- `browser_select @eN "value"` — Select dropdown option
- `browser_check @eN` — Check checkbox
- `browser_press "key"` — Press keyboard key (Enter, Tab, Escape, etc.)
- `browser_drag @eFrom @eTo` — Drag and drop between elements
- `browser_hover @eN` — Hover over element
- `browser_clear @eN` — Clear input field

### Observation
- `browser_snapshot` — Get accessibility tree with element refs (preferred over screenshot)
- `browser_screenshot` — Take visual screenshot for visual validation
- `browser_pdf_save` — Save page as PDF
- `browser_close` — Close browser

### Network & Console
- `browser_network_requests` — View network requests
- `browser_console_messages` — View console output

### Advanced
- `browser_evaluate "js_code"` — Execute arbitrary JavaScript (DANGEROUS — requires HITL)
- `browser_install` — Install Playwright browsers

## Safety Rules

1. **ALWAYS use `browser_snapshot` first** — It provides structured element refs and is 93% more token-efficient than screenshots
2. **Element refs change after page updates** — Always take a new snapshot after navigation or interaction
3. **Use `browser_click @eN` with snapshot refs** — Don't guess selectors
4. **`browser_evaluate` is dangerous** — Requires HITL approval through the security gate
5. **Use headless mode for CI** — Use `headless: true` in automated environments
6. **Close browser when done** — Always call `browser_close` after completing tasks

## Testing Patterns

### Page Load Test
```
1. browser_navigate "https://example.com"
2. browser_snapshot
3. Verify expected elements exist in snapshot
4. browser_screenshot (optional, for visual record)
```

### Form Fill Test
```
1. browser_navigate "https://example.com/form"
2. browser_snapshot
3. Identify input refs from snapshot
4. browser_fill @e1 "username"
5. browser_fill @e2 "password"
6. browser_click @e3 (submit button)
7. browser_snapshot (verify result)
```

### Responsive Design Check
```
1. browser_navigate "https://example.com"
2. browser_resize width=1920 height=1080; browser_screenshot
3. browser_resize width=768 height=1024; browser_screenshot
4. browser_resize width=375 height=667; browser_screenshot
```

## When to Use This Skill

- User wants to test or validate a web page
- User needs to fill forms or interact with a website
- User wants screenshots of a web page
- User needs to check responsive design
- User wants to verify links or navigation flows
- User needs to automate browser-based workflows

## When NOT to Use This Skill

- For server-side API testing (use HTTP tools instead)
- For file operations (use Filesystem MCP)
- For database operations (use Database MCP)
- For code execution outside browser context (use shell)

## Token Efficiency Tips

1. Prefer `browser_snapshot` over `browser_screenshot` — snapshots are structured text, screenshots are large base64 images
2. Only screenshot when visual validation is specifically needed
3. Use element refs from snapshots for deterministic clicking
4. Close browser when done to free resources
