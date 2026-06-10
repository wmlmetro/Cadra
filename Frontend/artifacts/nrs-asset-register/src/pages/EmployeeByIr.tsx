/**
 * Deep-link resolver: /hr/employees/by-ir/:ir → resolves the IR via the API
 * and replaces history with /hr/employees/:id. Used by external systems
 * that link by IR number rather than by Odoo id.
 */
import { useEffect } from "react";
import { useLocation, useParams } from "wouter";
import { useQuery } from "@tanstack/react-query";
import { fetchEmployeeByIr } from "@/lib/dataProvider";
import { CadraApiError } from "@/lib/api";
import { AlertCircle, Clock, UserX } from "lucide-react";
import type { Employee } from "@/types";

export default function EmployeeByIr() {
  const { ir } = useParams<{ ir: string }>();
  const [, nav] = useLocation();

  const { data: emp, isLoading, error } = useQuery<Employee | null, CadraApiError>({
    queryKey: ["employee-by-ir", ir],
    queryFn: () => fetchEmployeeByIr(ir ?? ""),
    enabled: !!ir,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (emp?.id) nav(`/hr/employees/${emp.id}`, { replace: true });
  }, [emp, nav]);

  if (isLoading) return (
    <div className="p-8 flex flex-col items-center gap-3 text-muted-foreground">
      <Clock size={20} className="animate-pulse" />
      <p className="text-sm">Resolving IR <span className="font-mono">{ir}</span>…</p>
    </div>
  );

  if (error) return (
    <div className="p-8 max-w-xl mx-auto">
      <div className="bg-red-50 dark:bg-red-950/30 border border-red-200/70 dark:border-red-800/30 rounded-2xl p-4 flex items-start gap-3">
        <AlertCircle size={16} className="text-red-600 dark:text-red-400 shrink-0 mt-0.5" />
        <div>
          <p className="text-[13px] font-semibold text-red-700 dark:text-red-400">{error.code}</p>
          <p className="text-[12px] text-red-700 dark:text-red-400 mt-0.5">{error.message}</p>
        </div>
      </div>
    </div>
  );

  if (!emp) return (
    <div className="p-8 max-w-md mx-auto flex flex-col items-center gap-3">
      <UserX size={28} className="text-muted-foreground/40" />
      <p className="text-sm font-semibold text-foreground">No employee with IR <span className="font-mono">{ir}</span></p>
      <button onClick={() => nav("/hr/employees")} className="text-xs text-primary hover:opacity-80">
        Back to employees
      </button>
    </div>
  );

  return null;
}
