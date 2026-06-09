# NRS Asset Register & Facility Management

A polished React + Vite design prototype for the Nigeria Revenue Service (NRS) Asset Register and Facility Management system, using mock data (no real backend).

## Run & Operate

- `pnpm --filter @workspace/nrs-asset-register run dev` — run the web app (port auto-assigned by workflow)
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Frontend: React 19 + Vite + Tailwind CSS v4 + shadcn/ui
- Routing: wouter
- Charts: recharts
- Tables: @tanstack/react-table
- Theme: next-themes (dark mode via `.dark` class)
- Data: pure mock data in `src/mock/` + `src/lib/dataProvider.ts`

## Where things live

- `artifacts/nrs-asset-register/src/` — all frontend source
  - `types.ts` — Asset, Location, Employee, DashboardStats interfaces
  - `mock/` — mock data (assets.ts × 40 items, locations.ts × 15, employees.ts × 10)
  - `lib/dataProvider.ts` — data access layer (replace with Odoo 17 JSON-RPC calls to go live)
  - `components/layout/` — Sidebar, Topbar, AppLayout (with LayoutContext for title/search)
  - `components/StatusPill.tsx` — approval status badge
  - `components/ConditionBadge.tsx` — asset condition badge
  - `pages/Dashboard.tsx` — Facility Command Center
  - `pages/AssetRegister.tsx` — kanban + list + map views with filters
  - `pages/AssetDetail.tsx` — full asset form with workflow + tabs
  - `pages/Locations.tsx` — tree + list views with detail panel

## Architecture decisions

- **Mock-data-first**: `dataProvider.ts` wraps mock data behind function calls. Each function includes a comment showing the equivalent Odoo 17 JSON-RPC call so the switch to real backend is straightforward.
- **No API client imports**: `@workspace/api-client-react` is deliberately not imported here — this is a standalone design prototype.
- **ThemeProvider wraps the whole tree**: `next-themes` with `attribute="class"` so dark mode adds `.dark` to `<html>`, matching Tailwind v4 `@custom-variant dark (&:is(.dark *))`.
- **LayoutContext**: AppLayout provides `setTitle` and `setSearchHandler` so each page sets its own topbar title and can wire up search without prop drilling.
- **NRS Red**: `#C8102E` → `hsl(351 85% 42%)` used as `--primary` and `--sidebar-primary`.

## Product

Four main screens:
1. **Facility Command Center** (Dashboard) — KPI cards, category bar chart, approval status donut, review queue table
2. **Asset Register** — Kanban/List/Map views, filter by Category/Status/Condition, group by Category/Zone/Status
3. **Asset Detail** — Workflow breadcrumb, hero panel, tabbed detail (Identification, Custodian, Audit & Review, Legacy Data)
4. **Locations** — Collapsible tree (Zone → State → Office) with side panel details, switchable List view

## User preferences

- NRS Red brand color: #C8102E (hsl 351 85% 42%)
- Dark mode support required
- No real backend — keep all data in mock layer with clear Odoo 17 migration path

## Gotchas

- `allMockAssets` in `src/mock/assets.ts` expands 8 base items × 5 = 40 total for realistic list density.
- When adding a new page, call `setTitle(...)` and `setSearchHandler(...)` inside a `useEffect` at the top of the component.
- Dark mode: always test with `.dark` class on `<html>`. Use `dark:` Tailwind prefix for overrides.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
- `dataProvider.ts` is the single source of truth for data access — all pages read from here
