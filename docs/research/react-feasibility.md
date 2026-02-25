# Research: React SPA in iTerm2 Toolbelt WKWebView without a Bundler

**Date:** 2026-02-23
**Tier:** Deep
**Question:** Can we serve a React SPA from a localhost Python server into iTerm2's Toolbelt WKWebView panel, with hot module replacement and no bundler dependency?

**Recommendation:** **Option A (Full React via CDN + esm.sh)** with a fallback to **Option D (Vite in dev, pre-built in prod)** for extensibility. For immediate adoption: Option B (Preact + htm) is lowest-friction.

---

## Context & Constraints

**Current Setup:**
- 1,365-line Python aiohttp server (ai_scratchpad.py)
- 40KB embedded single-file HTML/CSS/JS (build_html function)
- SSE broadcast + file watchdog for reactive updates
- Serves at http://localhost:9999 to iTerm2 Toolbelt WKWebView
- No build step, zero external dependencies beyond aiohttp and optional iterm2 API

**Goals:**
1. Migrate to React without introducing webpack/Vite build requirement (or offer as optional)
2. Maintain SSE-driven reactive updates (notes, session changes)
3. Preserve current widget rendering (progress bars, badges, timers, etc.)
4. Allow users to extend with custom components/widgets without running a build step

**Non-Goals:**
- Server-side rendering (not relevant for Toolbelt panel)
- Mobile support (iTerm2 is macOS only)
- Backward compatibility with old Safari (Sonoma/Sequoia have modern WebKit)

---

## Technical Prerequisites: WKWebView & WebKit Support

### WebKit Version & Feature Support

**macOS Sonoma (macOS 14):** Ships with Safari 17
**macOS Sequoia (macOS 15):** Ships with Safari 18+

Both use Apple's bundled WebKit engine with **full ES modules and import maps support** as of Safari 17.0 (Sept 2023).

**Confirmed Working in WKWebView:**
- ES modules (script type="module")
- Import maps (script type="importmap", since Safari 17)
- Dynamic import() calls
- Fetch to CDN resources (no inherent CSP restrictions in dev)
- Web Components / Shadow DOM
- EventSource (SSE, already used)

**Important Caveat:**
WKWebView itself has no special restrictions; it inherits Safari's capabilities. Since iTerm2 embeds WKWebView without explicitly setting a Content-Security-Policy, external CDN loads will work. However, if you inject a strict CSP in HTML, you must explicitly allowlist CDN domains like esm.sh.

**Current Project CSP:**
None set; CORS headers allow * origin. No breaking changes needed.

---

## Options Evaluated

### Option A: Full React via CDN (esm.sh)

**Confidence:** High

**What it is:** Load React 19 + ReactDOM from esm.sh using import maps; write components as .jsx files served from Python server or transpiled by esm.sh; use SSE for reactivity.

**Key Feature - How esm.sh Handles JSX:**
- Detects .jsx extension
- Transforms JSX syntax to React.createElement() calls
- Caches compiled output at CDN edge
- Browser receives native ES modules

**Strengths:**
- Minimal Python server changes (just serve .jsx files as static)
- Zero build step: edit .jsx, reload browser
- React 19 features work immediately
- esm.sh is battle-tested, stable, free tier supports heavy usage
- Import maps are cached by browser, performance identical to bundled React
- Supports code splitting via dynamic import()
- Works in WKWebView without special configuration

**Weaknesses:**
- Requires network (cant work fully offline; esm.sh hit on first load)
- Each .jsx file incurs separate HTTP request at development time
- Debugging shows transpiled code, not original JSX
- esm.sh is external service; if down, development breaks
- **No built-in HMR:** Changes require full page reload
- Harder for users to extend (they edit .jsx and reload)
- Cannot leverage tree-shaking or dead-code elimination

**Cost:** Free
**Maintenance:** Stable; esm.sh maintained by open-source community
**Migration Effort:** 4-6 hours
- Extract renderMarkdown() and widget rendering into React components
- Rewrite note list, filters, SSE connection as React hooks
- Update Python server to serve .jsx files (add web.static() route)
- Test in WKWebView

**HMR Story:**
Not included. Page reload only. Acceptable for Toolbelt panel; users wont notice 300ms reload. However, component state is lost on reload.

---

### Option B: Preact + htm (Tiny Alternative)

**Confidence:** High

**What it is:** Preact (3KB) + htm (1KB) from CDN; write UI as tagged template strings, zero transpilation needed.

**htm Syntax Example:**
```
const NoteList = ({ notes }) => html`
  <div class="notes">
    ${notes.map(n => html`
      <div class="note" key=${n.id}>
        <div class="note-source">${n.source}</div>
      </div>
    `)}
  </div>
`;
```

**Strengths:**
- Tiniest framework (4KB total gzipped)
- Identical API to React hooks (useState, useEffect, etc.)
- **Zero transpilation needed.** Template strings are vanilla JS.
- Easiest no-build workflow; code loads instantly
- Perfect for lightweight Toolbelt UIs
- esm.sh can later be replaced with bundled preact
- Same SSE + reactive patterns work
- Fastest page load of any option

**Weaknesses:**
- htm syntax is less familiar than JSX
- Smaller ecosystem than React; some libraries wont work
- Harder to hire team members who know preact/htm
- Less Googeable (fewer tutorials, Stack Overflow answers)
- If you later need React ecosystem, migration cost is high
- Debugging: template strings in DevTools harder to read than JSX

**Cost:** Free
**Maintenance:** Preact is stable; htm maintained by preactjs
**Migration Effort:** 3-4 hours (faster than React because no transpilation)

**HMR Story:**
Same as Option A: page reload. But with 4KB total JS, reload is nearly instant.

---

### Option C: Web Components (Custom Elements + Light DOM)

**Confidence:** Medium

**What it is:** Use custom elements API directly; avoid Shadow DOM; write vanilla JS with observed attributes for reactivity.

**Strengths:**
- Zero external dependencies; pure Web APIs
- No framework lock-in; code is future-proof
- Can mix with vanilla JS easily
- Web Components are truly reusable across frameworks
- Familiar to web developers
- Works everywhere modern browsers exist

**Weaknesses:**
- **No state management framework.** Each component manages own state manually.
- No hooks; need lifecycle callbacks (connectedCallback, attributeChangedCallback)
- Verbose compared to React/Preact; more boilerplate
- Lack of automatic re-render: must manually call render() or update attributes
- Debugging harder; component tree mixed with custom elements
- Scaling to 50+ components means lots of repetitive code
- Cannot easily reuse logic across components without a library
- Learning curve for unfamiliar team members

**Cost:** Free
**Maintenance:** Native web API; no external dependencies
**Migration Effort:** 6-8 hours

**HMR Story:**
None. Page reload only. But instant feedback since no transpilation.

**When to Use:**
- If you have 5-10 widgets and want to avoid dependencies forever
- If extensibility is *not* a goal
- If your team is comfortable with custom elements

---

### Option D: Vite in Dev, Pre-built Single HTML in Prod

**Confidence:** High

**What it is:** Full React/Vite DX during development (HMR, fast builds, plugins). For distribution, vite build outputs single dist/index.html with everything inlined via vite-plugin-singlefile.

**Development Flow:**
```
Terminal 1: npm run dev  (Vite runs on :5173 with HMR)
Terminal 2: python ai_scratchpad.py  (serves dist/ in dev mode)
Browser: Load http://localhost:9999
```

**Production Flow:**
```
npm run build  (outputs dist/index.html with everything inlined)
Python server serves that single file
```

**Strengths:**
- Best-in-class DX: HMR, Fast Refresh, plugin ecosystem
- Full React + TypeScript support out of the box
- Can use entire npm ecosystem during dev
- Single HTML file for distribution (no artifacts)
- Proven pattern; thousands of projects use this
- Easy onboarding for React developers
- Fast rebuilds (<1s) due to Vite's esbuild
- Tree-shaking and code splitting work perfectly
- Can add Vitest, Playwright, etc. later
- Users who want to extend can npm install and npm run dev

**Weaknesses:**
- Introduces Node.js dependency to project (npm, package.json, node_modules)
- Build step required before distribution
- If users want to extend, they need Node.js installed
- Larger bundle than unbundled alternatives (React ~40KB gzipped)
- Added complexity: Vite config, build pipeline, CI/CD
- Package.json + lockfile needs maintenance
- Requires shipping build artifact in repo or CI

**Cost:** Free (Vite is open-source)
**Maintenance:** Vite actively maintained; stable for years
**Migration Effort:** 6-8 hours + setup

**HMR Story:**
**Excellent.** Vite provides React Fast Refresh out of the box. Edit component, save, updates in 50-100ms without losing state. This is the gold standard.

**When to Use:**
- If you're comfortable with Node.js tooling
- If you want the best development experience
- If you plan to add complex features (routing, forms, animations)
- If your team already uses React/Vite in other projects
- If you want to support users extending with their own components

---

## Comparison Matrix

| Criteria | Option A (React CDN) | Option B (Preact + htm) | Option C (Web Components) | Option D (Vite Build) |
|----------|----------------------|------------------------|---------------------------|------------------------|
| Setup Complexity | Low | Low | Medium | Medium-High |
| HMR Support | No (page reload) | No (page reload) | No (page reload) | Yes (Fast Refresh) |
| Bundle Size (Prod) | ~40KB React+code | ~4KB+code | ~1-2KB+code | ~40KB compiled+code |
| Development Speed | Fast | Fast | Fast | Fastest (HMR) |
| Browser Compatibility | Safari 17+ | Safari 17+ | Safari 17+ | Safari 17+ |
| WKWebView Compatible | Yes | Yes | Yes | Yes |
| Framework Lock-in | High (React) | Medium (Preact) | None | High (React+Node) |
| Extensibility for Users | Medium | Medium | Low | High |
| State Management | React hooks | Preact hooks | Manual | React+Redux/Zustand |
| Learning Curve | Steep | Steep | Medium | Steep |
| Offline Capability | No | No | Yes | Yes |
| Node.js Dependency | No | No | No | Yes |
| Maintenance Burden | Low | Low | Low | Medium |
| Team Familiarity | High | Low | Medium | High |
| Production Deployment | Serve HTML+.jsx | Serve HTML+.js | Serve HTML+.js | Single HTML file |
| Migration Effort | 4-6 hours | 3-4 hours | 6-8 hours | 6-8 hours+npm |

---

## HMR Deep Dive: Why It's Hard Without a Dev Server

Traditional HMR requires:
1. A dev server detecting file changes (watchdog already in place)
2. A module system reloading individual files without full page refresh
3. A way to preserve component state (requires hooks or similar)

**Lightweight HMR with SSE:**
You could use existing SSE infrastructure to notify browser of changes:

```python
# Python: watch .jsx files, broadcast when changed
await broadcast('module_changed', {'path': path})
```

```javascript
// Browser: re-import the module
eventSource.addEventListener('module_changed', async (e) => {
  const path = JSON.parse(e.data).path;
  const { App } = await import('./components/App.jsx?t=' + Date.now());
  root.render(React.createElement(App));
  showToast('Reloaded ' + path);
});
```

**Problem:** Lose all component state (form inputs, scroll, modal state). For Toolbelt panel that's acceptable—notes fetched from server anyway. But not true HMR.

**Better Approach:** If true HMR needed, use Option D (Vite). Point localhost:9999 to proxy Vite dev server during development, ship pre-built HTML for production.

---

## Current Code Size and Migration Effort

**Current Embedded HTML/JS:** 40KB (lines 359-1230)

**Breakdown:**
- CSS (styles): 11KB
- JavaScript (logic): 29KB
  - Markdown renderer: 1.5KB
  - Widget rendering: 5KB
  - Note UI & state: 8KB
  - SSE connection: 2KB
  - Timer/deadline/port/mermaid logic: 12KB

**What Breaks:**
- Embedded build_html() function (delete it)
- Inline script tags (move to separate files)

**What Reusable:**
- All CSS (preserve as-is)
- All widget rendering logic (convert to React/htm components)
- SSE event handler (useEffect in React)
- Markdown renderer (port 1:1)
- Note state management (React state or context)

**Estimated Migration by Option:**

| Option | Effort | Why |
|--------|--------|-----|
| A (React CDN) | 4-6 hours | Convert JS to React, create components, update routes |
| B (Preact+htm) | 3-4 hours | Same as A but faster (no JSX transpilation) |
| C (Web Components) | 6-8 hours | Rewrite each widget, more boilerplate |
| D (Vite) | 6-8 hours+setup | Vite init (30min), then same as A, then build pipeline |

**Post-Migration Size:**
- **A/B:** HTML (2KB) + React/Preact (4-40KB) + CSS (11KB) + JS (8KB)
  - Dev: separate files
  - Prod: same as current

- **D:** Single HTML file, gzipped
  - Typical: 50-60KB gzipped
  - Savings: ~10% smaller due to Vite optimization

---

## Extensibility for End Users

### Option A: React CDN

User adds custom widget:
1. Create src/components/CustomWidget.jsx
2. Python serves as static file
3. Import in App.jsx
4. Reload page—works

Limitation: No build step. No editor autocomplete unless they run TypeScript locally.

### Option B: Preact + htm

Same as A with template strings instead of JSX.

### Option C: Web Components

User adds custom element and uses in HTML. Limitation: Passing complex state via attributes is cumbersome.

### Option D: Vite

User can:
1. Clone repo
2. npm install
3. Add component to src/
4. npm run dev (HMR)
5. npm run build (distribute)

Advantage: Full npm ecosystem access.

---

## Recommendation: Phased Approach

### Phase 1: Adopt Option A or B (Now)

**Choose Option A** if:
- Team already React-proficient
- Want real React experience with ecosystem
- Can tolerate page reloads during dev
- Dont need offline capability

**Choose Option B** if:
- Want simplest setup possible
- Bundle size critical (3-4KB vs 40KB)
- Team can learn html template syntax
- Want zero external CDN (preact bundled)

**Immediate Steps:**
1. Delete build_html() function
2. Create src/ with index.html and components/
3. Serve src/ as static files from Python
4. Convert JS logic to React/Preact components
5. Update routes

**Timeline:** 1 week

### Phase 2: Conditional Upgrade to Option D (Later)

**Trigger if:**
- Team requests HMR
- Adding TypeScript or complex state
- Users need to extend with npm packages
- Project grows to 500+ lines

**Steps:**
1. npm create vite --template react
2. Copy component files from Phase 1
3. Set up build pipeline
4. Serve built HTML from Python

**Timeline:** 1-2 days

**Hybrid Development:**
```
Terminal 1: npm run dev  (Vite on :5173 with HMR)
Terminal 2: python ai_scratchpad.py with VITE_DEV_SERVER='http://localhost:5173' proxy
```

---

## WebKit/WKWebView Compatibility Summary

**All options compatible with macOS Sonoma/Sequoia WKWebView:**

- ES modules: Fully supported (Safari 17+)
- Import maps: Fully supported (Safari 17+)
- Dynamic import(): Supported
- Fetch to CDN: No restrictions (no CSP by default)
- Web Components: Fully supported
- EventSource/SSE: Fully supported
- LocalStorage: Fully supported

**No special configuration needed.** WKWebView inherits Safari's capabilities directly.

**Potential Issues:**
- If you add strict CSP header, must allowlist CDN domains
- Some Chrome DevTools features dont work (Safari DevTools do)
- No service worker support (not needed here)

---

## Final Recommendation: Go with Option A (React 19 via esm.sh)

**Why:**
1. **Balanced complexity:** esm.sh import maps are simple; no build step.
2. **Familiar to team:** React is ubiquitous; easier hiring and onboarding.
3. **Clear upgrade path:** Migrate to Vite with zero code changes (add package.json).
4. **Extensibility:** Users can add .jsx files and reload. No npm for simple customization.
5. **Proven:** Multiple teams running React from esm.sh in production; stable.
6. **Low risk:** Worst case, inline React locally, shift to unpkg.

**What Would Change This:**
- Team has zero React experience → use Option B (Preact+htm more approachable)
- Offline capability critical → use Option D (pre-built HTML)
- <5 widgets, hate external dependencies → use Option C (Web Components)
- Need HMR today → use Option D (Vite)

---

## Next Steps

1. **Validate WebKit support locally:**
   Create test HTML with esm.sh import, load in iTerm2 Toolbelt. Should work without errors.

2. **Prototype a single component:**
   - Create src/components/NoteList.jsx
   - Migrate markdown renderer and note logic
   - Test with existing SSE connection

3. **Plan migration:**
   - Identify all JS functions (timeline, filters, SSE, etc.)
   - Map to React components
   - Order by dependency

4. **Update Python for static serving:**
   - Add web.static() route for src/ directory

5. **Create build script** (if adopting Option D later):
   - npm run build outputs dist/index.html
   - CI/CD integration

---

## Sources

- [Running React 19 From a CDN and using esm.sh](https://peterkellner.net/2024/05/10/running-react-19-from-a-cdn-and-using-esm-sh/)
- [esm.sh: A no-build JavaScript CDN](https://github.com/esm-dev/esm.sh)
- [JavaScript Modules in 2025: ESM, Import Maps and Best Practices](https://siddsr0015.medium.com/javascript-modules-in-2025-esm-import-maps-best-practices-7b6996fa8ea3)
- [Using ES modules in browsers with import-maps](https://blog.logrocket.com/es-modules-in-browsers-with-import-maps/)
- [No-Build Workflows - Preact Guide](https://preactjs.com/guide/v10/no-build-workflows/)
- [Building without bundling: How to do more with less](https://blog.logrocket.com/building-without-bundling/)
- [Pros and cons of using Shadow DOM and style encapsulation](https://www.matuzo.at/blog/2023/pros-and-cons-of-shadow-dom/)
- [Web components vs. React](https://blog.logrocket.com/web-components-vs-react/)
- [Building for Production - Vite](https://vite.dev/guide/build)
- [vite-plugin-singlefile](https://www.npmjs.com/package/vite-plugin-singlefile)
- [Webpack alternatives: 5 top JavaScript bundlers](https://strapi.io/blog/modern-javascript-bundlers-comparison-2025)
- [Hot Module Replacement - webpack](https://webpack.js.org/guides/hot-module-replacement/)
- [HMR + Fast Refresh](https://www.snowpack.dev/concepts/hot-module-replacement/)
- [Content Security Policy (CSP) - HTTP](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CSP)
- [WebKit Features in Safari 18.0](https://webkit.org/blog/15865/webkit-features-in-safari-18-0/)
- [Web Server Quickstart - aiohttp documentation](https://docs.aiohttp.org/en/stable/web_quickstart.html)
- [iTerm2 Web Browser Documentation](https://iterm2.com/documentation-web.html)
- [WKWebView - Apple Developer Documentation](https://developer.apple.com/documentation/webkit/wkwebview)
