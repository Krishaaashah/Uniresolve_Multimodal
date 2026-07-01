"use client";

import React from "react";
import { Complaint, Stats } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AlertCircle, Clock, ShieldAlert, Timer } from "lucide-react";
import SlaProgressBar from "./SlaProgressBar";

interface SlaViewProps {
  complaints: Complaint[];
  stats: Stats;
  onInspect: (complaint: Complaint) => void;
}

export default function SlaView({ complaints, stats, onInspect }: SlaViewProps) {
  const active = complaints.filter(c => c.status !== "resolved" && c.sla);
  
  const breached = active.filter(c => c.sla?.status === "breached");
  const atRisk = active.filter(c => c.sla?.status === "at_risk");
  const onTrack = active.filter(c => c.sla?.status === "on_track");

  // Sort: Breached first, then At Risk, then On Track
  const sortedActive = [...breached, ...atRisk, ...onTrack];

  return (
    <div className="space-y-6 font-sans">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          <Timer className="h-6 w-6 text-blue-600" /> SLA Tracker
        </h2>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Breached */}
        <Card className="border-l-4 border-l-rose-500 shadow-sm">
          <CardHeader className="pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">SLA Breached</span>
            <CardTitle className="text-3xl font-extrabold text-rose-600">{breached.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <CardDescription className="text-xs">Requires immediate supervisor intervention</CardDescription>
          </CardContent>
        </Card>

        {/* At Risk */}
        <Card className="border-l-4 border-l-amber-500 shadow-sm">
          <CardHeader className="pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">At Risk</span>
            <CardTitle className="text-3xl font-extrabold text-amber-600">{atRisk.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <CardDescription className="text-xs">&lt; 20% SLA duration remaining</CardDescription>
          </CardContent>
        </Card>

        {/* On Track */}
        <Card className="border-l-4 border-l-emerald-500 shadow-sm">
          <CardHeader className="pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">On Track</span>
            <CardTitle className="text-3xl font-extrabold text-emerald-600">{onTrack.length}</CardTitle>
          </CardHeader>
          <CardContent>
            <CardDescription className="text-xs">Proceeding within compliance thresholds</CardDescription>
          </CardContent>
        </Card>
      </div>

      {/* Active Table */}
      {sortedActive.length > 0 ? (
        <Card className="shadow-sm overflow-hidden">
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead className="font-bold text-slate-600">Ticket ID</TableHead>
                <TableHead className="font-bold text-slate-600">Category</TableHead>
                <TableHead className="font-bold text-slate-600">Severity</TableHead>
                <TableHead className="font-bold text-slate-600">SLA Status</TableHead>
                <TableHead className="font-bold text-slate-600 w-1/3">Time Progress</TableHead>
                <TableHead className="font-bold text-slate-600 text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedActive.map((c) => {
                const isBreached = c.sla?.status === "breached";
                const isAtRisk = c.sla?.status === "at_risk";
                
                let badgeVariant: "destructive" | "warning" | "success" = "success";
                let badgeText = "On Track";
                
                if (isBreached) {
                  badgeVariant = "destructive";
                  badgeText = "BREACHED";
                } else if (isAtRisk) {
                  badgeVariant = "warning";
                  badgeText = "AT RISK";
                }

                return (
                  <TableRow key={c.id} className="hover:bg-slate-50/50 transition-colors">
                    <TableCell className="font-extrabold text-blue-600">
                      <button 
                        onClick={() => onInspect(c)} 
                        className="hover:underline cursor-pointer text-left"
                      >
                        {c.ticket_id || "TKT-PENDING"}
                      </button>
                    </TableCell>
                    <TableCell className="font-medium text-slate-800">
                      {c.triage?.category || "General"}
                    </TableCell>
                    <TableCell>
                      <Badge 
                        variant="secondary" 
                        className={`text-[10px] font-extrabold uppercase ${
                          c.triage?.severity === "critical"
                            ? "bg-rose-100 text-rose-700"
                            : c.triage?.severity === "high"
                            ? "bg-amber-100 text-amber-700"
                            : c.triage?.severity === "medium"
                            ? "bg-yellow-100 text-yellow-700"
                            : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {c.triage?.severity || "medium"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge 
                        className={`text-[10px] font-extrabold uppercase ${
                          badgeVariant === "destructive"
                            ? "bg-rose-100 text-rose-700 hover:bg-rose-100"
                            : badgeVariant === "warning"
                            ? "bg-amber-100 text-amber-700 hover:bg-amber-100"
                            : "bg-emerald-100 text-emerald-700 hover:bg-emerald-100"
                        }`}
                      >
                        {badgeText}
                      </Badge>
                    </TableCell>
                    <TableCell className="py-2.5">
                      <SlaProgressBar complaint={c} compact={true} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Button 
                        size="sm" 
                        variant="outline" 
                        onClick={() => onInspect(c)}
                        className="font-bold text-xs h-8 border-slate-200 hover:bg-blue-600 hover:text-white cursor-pointer"
                      >
                        Inspect
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      ) : (
        <Card className="p-8 text-center border-dashed border-slate-200 bg-slate-50/50">
          <Clock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
          <p className="text-sm font-medium text-slate-500">No active complaints with SLA tracking</p>
        </Card>
      )}
    </div>
  );
}
