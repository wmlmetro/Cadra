/**
 * App shell — auth gate, providers, and lazy-loaded route table.
 *
 * Every route component is loaded via React.lazy so the initial bundle is
 * just the shell + React + the route the user is on. Vendor libraries
 * (react-query, leaflet, recharts, radix) are split into separate chunks
 * by vite.config.ts so they cache independently across deploys.
 *
 * The react-query cache is persisted to localStorage so a returning user
 * sees their last-known data instantly while it refreshes in the
 * background — the "stale-while-revalidate" feel.
 */
import { lazy, Suspense, useEffect, useState } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient } from "@tanstack/react-query";
import { PersistQueryClientProvider } from "@tanstack/react-query-persist-client";
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import AppLayout from "@/components/layout/AppLayout";
import { hasLiveSession, onLogout } from "@/lib/auth";
import { Clock } from "lucide-react";

const Login                      = lazy(() => import("@/pages/Login"));
const Dashboard                  = lazy(() => import("@/pages/Dashboard"));
const GlobalSearch               = lazy(() => import("@/pages/GlobalSearch"));
const FMOperationsDashboard      = lazy(() => import("@/pages/FMOperationsDashboard"));
const FleetCommandCenter         = lazy(() => import("@/pages/FleetCommandCenter"));
const ITAssetsCommand            = lazy(() => import("@/pages/ITAssetsCommand"));
const SecurityOperations         = lazy(() => import("@/pages/SecurityOperations"));
const BarcodeStation             = lazy(() => import("@/pages/BarcodeStation"));
const RequestsList               = lazy(() => import("@/pages/RequestsList"));
const TriageInbox                = lazy(() => import("@/pages/RequestsList").then(m => ({ default: m.TriageInbox })));
const RequestDetail              = lazy(() => import("@/pages/RequestDetail"));
const RequestForm                = lazy(() => import("@/pages/RequestForm"));
const AssetRegister              = lazy(() => import("@/pages/AssetRegister"));
const AssetRegisterDashboard     = lazy(() => import("@/pages/AssetRegisterDashboard"));
const AssetDetail                = lazy(() => import("@/pages/AssetDetail"));
const AssetForm                  = lazy(() => import("@/pages/AssetForm"));
const Locations                  = lazy(() => import("@/pages/Locations"));
const LocationDetail             = lazy(() => import("@/pages/LocationDetail"));
const LocationForm               = lazy(() => import("@/pages/LocationForm"));
const Employees                  = lazy(() => import("@/pages/Employees"));
const EmployeeDetail             = lazy(() => import("@/pages/Employees").then(m => ({ default: m.EmployeeDetail })));
const SAPSyncStatus              = lazy(() => import("@/pages/SAPSyncStatus"));
const EmployeeBulkImport         = lazy(() => import("@/pages/EmployeeBulkImport"));
const EmployeeByIr               = lazy(() => import("@/pages/EmployeeByIr"));
const Fleet                      = lazy(() => import("@/pages/Fleet"));
const FleetDetail                = lazy(() => import("@/pages/Fleet").then(m => ({ default: m.FleetDetail })));
const StaffBus                   = lazy(() => import("@/pages/StaffBus"));
const Identity                   = lazy(() => import("@/pages/Identity"));
const NotFound                   = lazy(() => import("@/pages/not-found"));

const FleetRosterReport          = lazy(() => import("@/pages/reports/FleetRosterReport"));
const AssetInventoryReport       = lazy(() => import("@/pages/reports/AssetInventoryReport"));
const DepreciationReport         = lazy(() => import("@/pages/reports/DepreciationReport"));
const DepreciationSettings       = lazy(() => import("@/pages/settings/DepreciationSettings"));
const AssetCategoriesSettings    = lazy(() => import("@/pages/settings/AssetCategories"));
const BrandingSettings           = lazy(() => import("@/pages/settings/Branding"));
const MaintenanceReadinessReport = lazy(() => import("@/pages/reports/MaintenanceReadinessReport"));
const LocationCoverageReport     = lazy(() => import("@/pages/reports/LocationCoverageReport"));
const TagAdoptionReport          = lazy(() => import("@/pages/reports/TagAdoptionReport"));

// react-query defaults tuned for snappy navigation:
//  - staleTime 5 min so revisiting a page reuses the cached data instantly
//  - refetchOnWindowFocus off so tab switches don't trigger spurious loads
//  - gcTime 24h so the persister has something to actually restore
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60_000,
      gcTime:    24 * 60 * 60_000,
      refetchOnWindowFocus: false,
      // `true`, NOT `false`. `true` refetches on mount only when the data is
      // STALE, so inside `staleTime` a revisit is still instant — which is
      // all `false` was ever chosen for. What `false` also did, silently and
      // app-wide, was make `invalidateQueries` a no-op for every query not on
      // screen: invalidation only REFETCHES mounted queries and merely flags
      // the rest, and a flagged query that is never refetched on mount is
      // shown from cache for ever. Acted in handoff 29: mark an asset missing
      // on its detail page, open the dashboard from the sidebar — *Missing: 8*
      // on screen, 9 in the database. Every mutation in the app had this.
      refetchOnMount: true,
      retry: 1,
    },
  },
});

// localStorage-backed persister. Limits the persisted cache age to 6h so
// stale data doesn't stick around forever between sessions.
const persister = createSyncStoragePersister({
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  key: "cadra.queryCache",
  throttleTime: 1000,
});

/** Minimal centered loader for route Suspense — keeps the layout chrome
 *  visible while the chunk + data come in. */
function RouteFallback() {
  return (
    <div className="flex-1 flex flex-col items-center justify-center gap-2 text-muted-foreground py-16">
      <Clock size={18} className="animate-pulse" />
      <p className="text-xs">Loading…</p>
    </div>
  );
}

function AppRoutes() {
  return (
    <AppLayout>
      <Suspense fallback={<RouteFallback />}>
        <Switch>
          <Route path="/"                    component={Dashboard}            />
          <Route path="/search"              component={GlobalSearch}         />
          <Route path="/dashboards/fm"       component={FMOperationsDashboard} />
          <Route path="/dashboards/fleet"    component={FleetCommandCenter}   />
          <Route path="/dashboards/it"       component={ITAssetsCommand}      />
          <Route path="/dashboards/security" component={SecurityOperations}   />
          <Route path="/tools/barcode"          component={BarcodeStation}    />
          {/* Service Desk — order: /new, /triage, /:id/edit, /:id, list */}
          <Route path="/service-desk/new"       component={() => <RequestForm mode="create" />} />
          <Route path="/service-desk/triage"    component={TriageInbox}       />
          <Route path="/service-desk/:id/edit"  component={() => <RequestForm mode="edit"   />} />
          <Route path="/service-desk/:id"       component={RequestDetail}     />
          <Route path="/service-desk"           component={() => <RequestsList />} />
          <Route path="/assets"              component={AssetRegisterDashboard} />
          <Route path="/assets/list"         component={AssetRegister}         />
          <Route path="/assets/new"          component={() => <AssetForm mode="create" />} />
          <Route path="/assets/:id/edit"     component={() => <AssetForm mode="edit"   />} />
          <Route path="/assets/:id"          component={AssetDetail}    />
          <Route path="/locations"           component={Locations}      />
          <Route path="/locations/new"       component={() => <LocationForm mode="create" />} />
          <Route path="/locations/:id/edit"  component={() => <LocationForm mode="edit"   />} />
          <Route path="/locations/:id"       component={LocationDetail} />
          {/* Reports — focused single-page views built on the dashboard APIs */}
          <Route path="/reports/fleet-roster"           component={FleetRosterReport}           />
          <Route path="/reports/asset-inventory"        component={AssetInventoryReport}        />
          <Route path="/reports/depreciation"           component={DepreciationReport}          />
          <Route path="/settings/depreciation"          component={DepreciationSettings}         />
          <Route path="/settings/categories"            component={AssetCategoriesSettings}      />
          <Route path="/settings/branding"              component={BrandingSettings}             />
          <Route path="/reports/maintenance-readiness"  component={MaintenanceReadinessReport}  />
          <Route path="/reports/location-coverage"      component={LocationCoverageReport}      />
          <Route path="/reports/tag-adoption"           component={TagAdoptionReport}           />
          <Route path="/hr/sap-sync"            component={SAPSyncStatus}        />
          <Route path="/hr/import"              component={EmployeeBulkImport}    />
          <Route path="/hr/employees"           component={Employees}             />
          {/* by-ir must precede :id so wouter doesn't try to resolve "by-ir" as an id */}
          <Route path="/hr/employees/by-ir/:ir" component={EmployeeByIr}          />
          <Route path="/hr/employees/:id"       component={EmployeeDetail}        />
          <Route path="/hr/identity"            component={Identity}              />
          {/* specific fleet routes must precede the dynamic :id catch-all */}
          <Route path="/fleet/staff-bus"     component={StaffBus}       />
          <Route path="/fleet"               component={Fleet}          />
          <Route path="/fleet/:id"           component={FleetDetail}    />
          <Route component={NotFound} />
        </Switch>
      </Suspense>
    </AppLayout>
  );
}

/** Listens for the logout event + auth-changed event and flips between the
 *  Login screen and the authenticated app shell. */
function AuthGate() {
  const [signedIn, setSignedIn] = useState(hasLiveSession);

  useEffect(() => {
    const refresh = () => setSignedIn(hasLiveSession());
    window.addEventListener("cadra:auth-changed", refresh);
    const off = onLogout(refresh);
    return () => { window.removeEventListener("cadra:auth-changed", refresh); off(); };
  }, []);

  // The cache is wiped on BOTH transitions — signing out AND signing in.
  // Clearing only on sign-out missed the ordinary end of a session on a
  // shared PC: A's token expires with the tab closed, so no sign-out ever
  // happens here; B opens the app, A's persisted cache is restored, B signs
  // in — and B reads A's cached data, the top bar's name included, beside a
  // Verify button that records B.
  useEffect(() => {
    queryClient.clear();
  }, [signedIn]);

  if (!signedIn) return (
    <Suspense fallback={<RouteFallback />}>
      <Login />
    </Suspense>
  );
  return <AppRoutes />;
}

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="nrs-theme">
      <PersistQueryClientProvider
        client={queryClient}
        persistOptions={{
          persister,
          maxAge: 6 * 60 * 60_000,
          // Never written to disk: who is signed in, and the raw record the
          // Edit form hydrates from. Both must come from the server each
          // time — a restored copy of the first names the wrong person, and
          // of the second writes an old `state` back over a newer one.
          dehydrateOptions: {
            shouldDehydrateQuery: (q) =>
              q.state.status === "success"
              && q.queryKey[0] !== "whoami" && q.queryKey[0] !== "asset-raw",
          },
          // BUMP THIS whenever an adapter changes what a cached object MEANS.
          // The persisted cache holds objects AFTER `lib/adapters.ts` has run,
          // and a restored one is shown as it was stored for as long as it is
          // fresh: `refetchOnMount: true` (above) refetches only what is STALE,
          // and `staleTime` is five minutes — so a browser reopened inside
          // that window paints the old objects and asks nobody.
          //
          // v1 → v2 in handoff 29: `deriveStatus` used to turn a missing or
          // disposed asset into "Cleared", and every browser that had opened
          // the register was holding those objects — so the fix could have
          // shipped and the green pill stayed on screen, out of the user's
          // own localStorage.
          //
          // v2 → v3 in handoff 30, for the same reason pointed the other way.
          // `deriveStatus` gained "Review — no SAP code", `reviewFlags` gained
          // its sentence, and `Asset` gained `sapReconciliationState`. A v2
          // object has none of them: a tagged asset finance never booked would
          // be restored wearing "Cleared", under a Status filter that now asks
          // the server for exceptions and drops every row whose cached status
          // disagrees. The history object changed shape too (`eventRecording`
          // is mapped over, and a v2 one has no such key).
          //
          // v3 → v4 in handoff 34. `Asset` gained `warranty`, and a v3 object
          // has none — which the asset page reads as "a server that predates
          // the block" and draws no verdict from. Honest, but wrong about the
          // server for as long as the copy is fresh, and the register's
          // warranty filter would sit over rows that cannot show one.
          buster: "v4",
        }}
      >
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <AuthGate />
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </PersistQueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
