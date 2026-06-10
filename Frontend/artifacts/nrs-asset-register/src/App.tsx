import { useEffect, useState } from "react";
import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import AppLayout from "@/components/layout/AppLayout";
import { hasLiveSession, onLogout } from "@/lib/auth";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import FMOperationsDashboard from "@/pages/FMOperationsDashboard";
import FleetCommandCenter from "@/pages/FleetCommandCenter";
import SecurityOperations from "@/pages/SecurityOperations";
import BarcodeStation from "@/pages/BarcodeStation";
import RequestsList, { TriageInbox } from "@/pages/RequestsList";
import RequestDetail from "@/pages/RequestDetail";
import RequestForm from "@/pages/RequestForm";
import AssetRegister from "@/pages/AssetRegister";
import AssetRegisterDashboard from "@/pages/AssetRegisterDashboard";
import AssetDetail from "@/pages/AssetDetail";
import AssetForm from "@/pages/AssetForm";
import Locations from "@/pages/Locations";
import LocationDetail from "@/pages/LocationDetail";
import LocationForm from "@/pages/LocationForm";
import Employees, { EmployeeDetail } from "@/pages/Employees";
import SAPSyncStatus from "@/pages/SAPSyncStatus";
import EmployeeBulkImport from "@/pages/EmployeeBulkImport";
import EmployeeByIr from "@/pages/EmployeeByIr";
import Fleet, { FleetDetail } from "@/pages/Fleet";
import StaffBus from "@/pages/StaffBus";
import Identity from "@/pages/Identity";
import NotFound from "@/pages/not-found";

const queryClient = new QueryClient();

function AppRoutes() {
  return (
    <AppLayout>
      <Switch>
        <Route path="/"                    component={Dashboard}            />
        <Route path="/dashboards/fm"       component={FMOperationsDashboard} />
        <Route path="/dashboards/fleet"    component={FleetCommandCenter}   />
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

  // When the user logs out we also wipe the react-query cache so the next
  // sign-in doesn't read stale per-user data.
  useEffect(() => {
    if (!signedIn) queryClient.clear();
  }, [signedIn]);

  if (!signedIn) return <Login />;
  return <AppRoutes />;
}

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem storageKey="nrs-theme">
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
            <AuthGate />
          </WouterRouter>
          <Toaster />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

export default App;
