"use client";

import React from "react";
import { Complaint } from "@/lib/api";
import { Progress } from "@/components/ui/progress";
import { AlertTriangle, Clock, ShieldAlert } from "lucide-react";

interface SlaProgressBarProps {
  complaint: Complaint;
  compact?: boolean;
}

export default function SlaProgressBar({ complaint, compact = false }: SlaProgressBarProps) {
  if (!complaint.sla || complaint.status === "resolved") return null;

  const { percent_used, hours_remaining, status } = complaint.sla;
  const pct = Math.min(100, Math.max(0, percent_used));

  let label = "";
  let icon = <Clock className="h-3.5 w-3.5" />;
  let colorClass = "text-emerald-600 bg-emerald-50 border-emerald-200";
  let fillClass = "bg-emerald-500";

  if (hours_remaining <= 0 || status === "breached") {
    const hrsOver = Math.abs(hours_remaining);
    const hrs = Math.floor(hrsOver);
    const mins = Math.round((hrsOver - hrs) * 60);
    label = `BREACHED BY ${hrs}h ${mins}m`;
    icon = <ShieldAlert className="h-3.5 w-3.5 animate-pulse" />;
    colorClass = "text-rose-600 bg-rose-50 border-rose-200 font-bold animate-pulse";
    fillClass = "bg-rose-500";
  } else {
    const hrs = Math.floor(hours_remaining);
    const mins = Math.round((hours_remaining - hrs) * 60);
    if (status === "at_risk") {
      label = `AT RISK: ${hrs}h ${mins}m left`;
      icon = <AlertTriangle className="h-3.5 w-3.5 animate-pulse" />;
      colorClass = "text-amber-600 bg-amber-50 border-amber-200 font-bold animate-pulse";
      fillClass = "bg-amber-500";
    } else {
      label = `${hrs}h ${mins}m left`;
      colorClass = "text-emerald-600 bg-emerald-50 border-emerald-200";
      fillClass = "bg-emerald-500";
    }
  }

  if (compact) {
    return (
      <div className="flex items-center gap-2 w-full mt-2 select-none">
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div className={`h-full ${fillClass}`} style={{ width: `${pct}%` }} />
        </div>
        <span className={`text-[10px] uppercase font-bold py-0.5 px-2 rounded-full border inline-flex items-center gap-1.5 ${colorClass}`}>
          {icon} {label}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-1.5 select-none">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-500">SLA Response Progress</span>
        <span className="font-semibold text-slate-700">{pct}% used</span>
      </div>
      <div className="relative">
        <Progress value={pct} className={`h-2.5 bg-slate-100 ${fillClass}`} />
      </div>
      <div className="flex justify-between items-center mt-1">
        <span className={`text-xs py-1 px-3 rounded-full border inline-flex items-center gap-2 ${colorClass}`}>
          {icon} {label}
        </span>
      </div>
    </div>
  );
}
