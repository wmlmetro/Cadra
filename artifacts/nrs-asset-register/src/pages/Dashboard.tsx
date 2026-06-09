import { useEffect } from "react";
import { useLayoutCtx } from "@/components/layout/AppLayout";
import { getDashboardStats, getReviewQueueAssets, getAssetsByCategory, getAssetsByStatus } from "@/lib/dataProvider";
import StatusPill from "@/components/StatusPill";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { Monitor, Car, Sofa, MapPin, Users, AlertTriangle, CheckCircle2 } from "lucide-react";

const STATUS_COLORS: Record<string, string> = {
  "Cleared": "#22c55e",
  "Review — data quality": "#f59e0b",
  "Review — allottee not in nominal roll": "#f97316",
  "Review — VIN not verifiable": "#eab308",
  "Review — possible duplicate": "#a855f7",
};

export default function Dashboard() {
  const { setTitle, setSearchHandler } = useLayoutCtx();
  const stats = getDashboardStats();
  const reviewAssets = getReviewQueueAssets();
  const categoryData = getAssetsByCategory();
  const statusData = getAssetsByStatus();

  useEffect(() => {
    setTitle("Facility Command Center");
    setSearchHandler(undefined);
  }, [setTitle, setSearchHandler]);

  return (
    <div className="p-6 space-y-6 max-w-[1400px] mx-auto">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Assets */}
        <div className="bg-card border border-card-border rounded-xl p-5 col-span-2 lg:col-span-1" data-testid="card-total-assets">
          <div className="flex items-start justify-between mb-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Total Assets</p>
            <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Monitor size={14} className="text-primary" />
            </div>
          </div>
          <p className="text-3xl font-bold text-foreground tabular-nums">{stats.totalAssets.toLocaleString()}</p>
          <div className="mt-3 flex flex-wrap gap-x-3 gap-y-1">
            <span className="text-xs text-muted-foreground">IT <span className="font-semibold text-foreground">{stats.itEquipment.toLocaleString()}</span></span>
            <span className="text-xs text-muted-foreground">Fleet <span className="font-semibold text-foreground">{stats.fleetVehicles.toLocaleString()}</span></span>
            <span className="text-xs text-muted-foreground">Furniture <span className="font-semibold text-foreground">{stats.furniture.toLocaleString()}</span></span>
          </div>
        </div>

        {/* Locations */}
        <div className="bg-card border border-card-border rounded-xl p-5" data-testid="card-locations">
          <div className="flex items-start justify-between mb-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Locations</p>
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <MapPin size={14} className="text-blue-500" />
            </div>
          </div>
          <p className="text-3xl font-bold text-foreground tabular-nums">{stats.locations.toLocaleString()}</p>
          <p className="mt-3 text-xs text-muted-foreground">7 zones · 38 states · 857 offices</p>
        </div>

        {/* Employees */}
        <div className="bg-card border border-card-border rounded-xl p-5" data-testid="card-employees">
          <div className="flex items-start justify-between mb-3">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Employees</p>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <Users size={14} className="text-emerald-500" />
            </div>
          </div>
          <p className="text-3xl font-bold text-foreground tabular-nums">{stats.employees.toLocaleString()}</p>
          <p className="mt-3 text-xs text-muted-foreground">Across all zones &amp; states</p>
        </div>

        {/* Review Queue */}
        <div className="bg-card border border-amber-200 dark:border-amber-900/50 rounded-xl p-5" data-testid="card-review-queue">
          <div className="flex items-start justify-between mb-3">
            <p className="text-xs font-medium text-amber-700 dark:text-amber-400 uppercase tracking-wider">Review Queue</p>
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center">
              <AlertTriangle size={14} className="text-amber-500" />
            </div>
          </div>
          <p className="text-3xl font-bold text-amber-700 dark:text-amber-400 tabular-nums">{stats.reviewQueue.toLocaleString()}</p>
          <p className="mt-3 text-xs text-amber-600 dark:text-amber-500">Assets needing attention</p>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Bar chart */}
        <div className="bg-card border border-card-border rounded-xl p-5 lg:col-span-3">
          <p className="text-sm font-semibold text-foreground mb-4">Assets by Category</p>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={categoryData} barSize={40}>
              <XAxis dataKey="name" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} tickFormatter={(v) => v.toLocaleString()} />
              <Tooltip
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", color: "hsl(var(--foreground))" }}
                formatter={(v: number) => [v.toLocaleString(), "Assets"]}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                <Cell fill="hsl(var(--chart-1))" />
                <Cell fill="hsl(var(--chart-2))" />
                <Cell fill="hsl(var(--chart-3))" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Donut chart */}
        <div className="bg-card border border-card-border rounded-xl p-5 lg:col-span-2">
          <p className="text-sm font-semibold text-foreground mb-4">Approval Status</p>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={statusData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                paddingAngle={2}
              >
                {statusData.map((entry) => (
                  <Cell key={entry.name} fill={STATUS_COLORS[entry.name] ?? "#94a3b8"} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{ fontSize: 11, borderRadius: 8, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", color: "hsl(var(--foreground))" }}
                formatter={(v: number) => [v.toLocaleString(), ""]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="space-y-1.5 mt-1">
            {statusData.map((d) => (
              <div key={d.name} className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ background: STATUS_COLORS[d.name] }} />
                <span className="text-[10px] text-muted-foreground flex-1 truncate">{d.name}</span>
                <span className="text-[10px] font-semibold text-foreground tabular-nums">{d.value.toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Review queue table */}
      <div className="bg-card border border-card-border rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <p className="text-sm font-semibold text-foreground">Recent Review Queue</p>
          <span className="text-xs text-muted-foreground">Showing {reviewAssets.length} of {stats.reviewQueue.toLocaleString()}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="table-review-queue">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Asset</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Category</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="text-left px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Location</th>
                <th className="text-right px-5 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody>
              {reviewAssets.map((asset, i) => (
                <tr key={asset.id} className={i % 2 === 0 ? "bg-background/40" : ""} data-testid={`row-review-${asset.id}`}>
                  <td className="px-5 py-3">
                    <div>
                      <p className="font-medium text-foreground text-xs">{asset.name}</p>
                      <p className="text-muted-foreground text-[10px]">{asset.assetTag || asset.legacyCode}</p>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{asset.category}</td>
                  <td className="px-4 py-3"><StatusPill status={asset.status} /></td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[180px]">{asset.location.path}</td>
                  <td className="px-5 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium border border-green-300 dark:border-green-700 text-green-700 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors"
                        onClick={() => console.log("Approve", asset.id)}
                        data-testid={`button-approve-${asset.id}`}
                      >
                        <CheckCircle2 size={11} />
                        Approve
                      </button>
                      <button
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium border border-amber-300 dark:border-amber-700 text-amber-700 dark:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors"
                        onClick={() => console.log("Override", asset.id)}
                        data-testid={`button-override-${asset.id}`}
                      >
                        Override
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
