"use client";

import React, { useState, useEffect } from "react";
import { Complaint, api, RootCause } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertTriangle, Clock, Folder, Link as LinkIcon, Loader2, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";

interface AlertsViewProps {
  complaints: Complaint[];
  onInspect: (complaint: Complaint) => void;
}

export default function AlertsView({ complaints, onInspect }: AlertsViewProps) {
  const [loading, setLoading] = useState(true);
  const [rootCauses, setRootCauses] = useState<RootCause[]>([]);
  const [errorMessage, setErrorMessage] = useState("");

  const fetchDiagnostics = async () => {
    setLoading(true);
    setErrorMessage("");
    try {
      const res = await api.getRootCause();
      if (res.message === "insufficient data") {
        setErrorMessage("No systemic clusters large enough for diagnostic profiling yet. Ingest more data via the 'Live Demo' streaming simulation.");
      } else {
        setRootCauses(res.root_causes || []);
      }
    } catch (e) {
      setErrorMessage("Outage diagnostics disabled. Configure GEMINI_API_KEY inside backend .env file to enable automated root-cause engine clustering.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDiagnostics();
  }, []);

  const cleanText = (value: string = "") => {
    return value
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F\u200D]/gu, "")
      .replace(/\*/g, "")
      .replace(/^\s*complaint\s+summary:\s*/i, "")
      .replace(/\s{2,}/g, " ")
      .trim();
  };

  const timeAgo = (iso: string) => {
    const diffMs = Date.now() - new Date(iso).getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  // Find unique clusters from complaints list where systemic_alert is true
  const alertsList = complaints.filter(c => c.cluster?.systemic_alert);
  const uniqueClustersMap: Record<string, Complaint> = {};
  alertsList.forEach(c => {
    if (c.cluster?.cluster_id) {
      const clId = c.cluster.cluster_id;
      if (!uniqueClustersMap[clId]) {
        uniqueClustersMap[clId] = c;
      }
    }
  });
  const clusterIncidents = Object.values(uniqueClustersMap);

  return (
    <div className="space-y-6 font-sans">
      {/* Title */}
      <div className="flex items-center justify-between select-none">
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          <AlertTriangle className="h-6 w-6 text-rose-600 animate-pulse" /> Systemic Outage Alerts
        </h2>
      </div>

      {/* Outage Diagnostics Panel */}
      <Card className="bg-slate-50/50 border-slate-200">
        <CardContent className="p-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-extrabold text-blue-800 select-none">
            <span className="w-2 h-2 rounded-full bg-rose-600 animate-ping inline-block" />
            Gen-AI Outage Diagnostics (Union Bank gateway)
          </div>
          {loading ? (
            <div className="py-2 flex items-center gap-2 text-xs text-slate-500 select-none">
              <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              Auditing clusters using Gemini root-cause engine...
            </div>
          ) : errorMessage ? (
            <p className="text-xs text-slate-500 leading-relaxed font-semibold italic pl-1 select-none">{errorMessage}</p>
          ) : rootCauses.length > 0 ? (
            <div className="space-y-3 leading-relaxed">
              <p className="text-xs text-slate-500 font-semibold pl-1 select-none">
                Gemini compliance analyzer has mapped the ticket logs and isolated these core root-cause incidents:
              </p>
              <div className="grid grid-cols-1 gap-3">
                {rootCauses.map((rc, idx) => (
                  <div 
                    key={idx} 
                    className="p-3 bg-white border border-slate-200 border-l-4 border-l-rose-500 rounded-lg flex flex-col gap-1 shadow-sm"
                  >
                    <div className="flex justify-between items-center text-xs">
                      <span className="font-extrabold text-blue-800 flex items-center gap-1">
                        <Sparkles className="h-3.5 w-3.5 text-blue-600" /> Incident #{idx + 1}: {cleanText(rc.cause)}
                      </span>
                      <Badge className="bg-rose-50 border border-rose-200 text-rose-700 font-extrabold text-[9px] hover:bg-rose-50">
                        {rc.count_estimate} reports matching
                      </Badge>
                    </div>
                    <p className="text-[11px] text-slate-400 font-semibold italic mt-1 pl-1">
                      &ldquo;{cleanText(rc.example_complaint)}&rdquo;
                    </p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-500 pl-1 font-semibold italic select-none">No active diagnostics logged.</p>
          )}
        </CardContent>
      </Card>

      {/* Incident Reports Table / Card List */}
      <h3 className="text-sm font-bold text-slate-700 select-none">Outage Incident Reports</h3>
      <div className="flex flex-col gap-4">
        {clusterIncidents.length > 0 ? (
          clusterIncidents.map((c) => {
            const clId = c.cluster?.cluster_id;
            // Get all member complaints inside this cluster
            const members = complaints.filter(m => m.cluster?.cluster_id === clId);

            return (
              <Card 
                key={clId} 
                className="border-l-4 border-l-rose-500 border-slate-200 shadow-sm overflow-hidden"
              >
                <CardContent className="p-5 space-y-4">
                  <div className="flex justify-between items-start flex-wrap gap-2 text-xs">
                    <span className="font-black text-rose-600 text-xs tracking-wider uppercase select-none">
                      INCIDENT ID: {clId ? clId.substring(0, 8).toUpperCase() : "UNKNOWN"}
                    </span>
                    <div className="flex gap-2">
                      <Badge className="bg-rose-150 text-rose-900 hover:bg-rose-150 font-extrabold uppercase text-[10px]">
                        {members.length} targets
                      </Badge>
                      <Badge className="bg-rose-600 text-white hover:bg-rose-700 font-extrabold uppercase text-[10px]">
                        {c.cluster?.affected_customers || 1} customers affected
                      </Badge>
                    </div>
                  </div>

                  <div className="text-xs text-slate-700 space-y-1.5 font-medium select-none">
                    <div><strong>Category:</strong> {(c.triage?.category || "General").toUpperCase()}</div>
                    <div><strong>Diagnosis:</strong> {cleanText(c.cluster?.cluster_description || "Systemic gateway outage detected.")}</div>
                    <div className="flex items-center gap-1.5 text-slate-400 text-[11px] mt-1.5 font-semibold">
                      <Clock className="h-3.5 w-3.5" /> Active since: {new Date(c.received_at).toLocaleString()} ({timeAgo(c.received_at)})
                    </div>
                  </div>

                  {/* List of matched complaints in this incident */}
                  <div className="bg-slate-50/50 border border-slate-200 rounded-lg p-3 space-y-2">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block select-none">Matched System Tickets</span>
                    <div className="flex flex-col gap-2 max-h-[190px] overflow-y-auto pr-1">
                      {members.map((m) => (
                        <div 
                          key={m.id}
                          onClick={() => onInspect(m)}
                          className="flex justify-between items-center p-2 bg-white border border-slate-150 rounded-md hover:border-blue-500 cursor-pointer transition-all duration-200"
                        >
                          <span className="text-xs font-bold text-blue-600">{m.ticket_id || "TKT-PENDING"}</span>
                          <span className="text-xs font-medium text-slate-700 truncate max-w-[45%]">
                            {cleanText(m.triage?.key_issue || m.summary || "")}
                          </span>
                          <span className="text-[10px] text-slate-400 font-semibold flex items-center gap-2 select-none">
                            <span>{m.channel.toUpperCase()}</span>
                            <span>&bull;</span>
                            <span>{timeAgo(m.received_at)}</span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex justify-end select-none">
                    <Button
                      onClick={() => onInspect(c)}
                      variant="outline"
                      className="border-slate-200 hover:bg-rose-600 hover:text-white font-extrabold text-xs h-8 cursor-pointer gap-1.5"
                    >
                      <LinkIcon className="h-3 w-3" /> Inspect Lead Incident Ticket &rarr;
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })
        ) : (
          <Card className="p-8 text-center border-dashed border-slate-200 bg-slate-50/50">
            <ShieldCheck className="h-8 w-8 text-emerald-500 mx-auto mb-2" />
            <p className="text-sm font-medium text-slate-500">No active systemic alerts detected</p>
          </Card>
        )}
      </div>
    </div>
  );
}
