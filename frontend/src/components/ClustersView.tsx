"use client";

import React, { useState, useEffect } from "react";
import { api, Complaint, ClusterNode } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Loader2, Network, TableProperties } from "lucide-react";
import { toast } from "sonner";

interface ClustersViewProps {
  complaints: Complaint[];
  onSelectCategory: (category: string) => void;
}

interface PhysicsBubble extends ClusterNode {
  x: number;
  y: number;
  r: number;
}

export default function ClustersView({ complaints, onSelectCategory }: ClustersViewProps) {
  const [loading, setLoading] = useState(true);
  const [clusters, setClusters] = useState<ClusterNode[]>([]);
  const [bubbles, setBubbles] = useState<PhysicsBubble[]>([]);

  const fetchClustersData = async () => {
    setLoading(true);
    try {
      let data = await api.getClusters();
      if (!data || data.length === 0) {
        data = buildMockClusters(complaints);
      }
      setClusters(data);
      initializePhysics(data);
    } catch (e) {
      const fallback = buildMockClusters(complaints);
      setClusters(fallback);
      initializePhysics(fallback);
    } finally {
      setLoading(false);
    }
  };

  const buildMockClusters = (list: Complaint[]): ClusterNode[] => {
    const map: Record<string, { category: string; complaint_count: number; customers: Set<string>; severity_breakdown: Record<string, number> }> = {};
    list.forEach((c) => {
      const cat = c.triage?.category || "General";
      if (!map[cat]) {
        map[cat] = { category: cat, complaint_count: 0, customers: new Set<string>(), severity_breakdown: {} };
      }
      const item = map[cat];
      item.complaint_count += 1;
      if (c.customer_id) item.customers.add(c.customer_id);
      const sev = c.triage?.severity || "medium";
      item.severity_breakdown[sev] = (item.severity_breakdown[sev] || 0) + 1;
    });

    return Object.values(map)
      .map((item) => ({
        category: item.category,
        complaint_count: item.complaint_count,
        customer_count: item.customers.size || 1,
        severity_breakdown: item.severity_breakdown,
      }))
      .sort((a, b) => b.customer_count - a.customer_count);
  };

  const initializePhysics = (nodes: ClusterNode[]) => {
    const centerX = 400;
    const centerY = 250;
    
    // Layout nodes initially in a spiral
    const initialBubbles: PhysicsBubble[] = nodes.map((c, idx) => {
      const r = 40 + Math.min(c.customer_count * 6, 80);
      const angle = idx * 1.7;
      const distance = 60 + idx * 35;
      return {
        ...c,
        r,
        x: centerX + distance * Math.cos(angle),
        y: centerY + distance * Math.sin(angle),
      };
    });

    // Run simple repelling loop for 120 steps to prevent overlap
    for (let step = 0; step < 120; step++) {
      for (let i = 0; i < initialBubbles.length; i++) {
        for (let j = i + 1; j < initialBubbles.length; j++) {
          const dx = initialBubbles[j].x - initialBubbles[i].x;
          const dy = initialBubbles[j].y - initialBubbles[i].y;
          const dist = Math.hypot(dx, dy);
          const minDist = initialBubbles[i].r + initialBubbles[j].r + 15;
          if (dist < minDist) {
            const overlap = minDist - dist;
            const pushX = (dx / (dist || 1)) * overlap * 0.5;
            const pushY = (dy / (dist || 1)) * overlap * 0.5;
            initialBubbles[i].x -= pushX;
            initialBubbles[i].y -= pushY;
            initialBubbles[j].x += pushX;
            initialBubbles[j].y += pushY;
          }
        }
      }
    }

    // Boundary constraints
    initialBubbles.forEach((b) => {
      b.x = Math.max(b.r + 20, Math.min(800 - b.r - 20, b.x));
      b.y = Math.max(b.r + 20, Math.min(500 - b.r - 20, b.y));
    });

    setBubbles(initialBubbles);
  };

  useEffect(() => {
    fetchClustersData();
  }, [complaints]);

  const getBubbleColors = (b: PhysicsBubble) => {
    const crit = b.severity_breakdown.critical || 0;
    const high = b.severity_breakdown.high || 0;
    const med = b.severity_breakdown.medium || 0;
    const low = b.severity_breakdown.low || 0;

    if (crit > 0) return { border: "#ef4444", fill: "rgba(239, 68, 68, 0.08)" };
    if (high > 0) return { border: "#f97316", fill: "rgba(249, 115, 22, 0.08)" };
    if (med > 0) return { border: "#eab308", fill: "rgba(234, 179, 8, 0.08)" };
    if (low > 0) return { border: "#10b981", fill: "rgba(16, 185, 129, 0.08)" };
    return { border: "#3b82f6", fill: "rgba(59, 130, 246, 0.08)" };
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500 font-sans">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600 mb-4" />
        <p className="text-sm font-medium">Analyzing category clusters...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 font-sans">
      {/* Title */}
      <div className="flex items-center justify-between select-none">
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          <Network className="h-6 w-6 text-blue-600" /> Dynamic Category Clusters
        </h2>
        <span className="text-xs text-slate-400 font-medium">
          Bubble sizes represent distinct affected customers. Click to inspect tickets.
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* SVG Interactive bubble map (Col span 3) */}
        <Card className="lg:col-span-3 shadow-sm border-slate-200 p-4 flex flex-col justify-center bg-white min-h-[500px]">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3 select-none">
            <Network className="h-4 w-4 text-blue-600" /> Interactive Cluster Map
          </div>
          <div className="border border-slate-100 rounded-lg overflow-hidden bg-slate-50/50 relative">
            <svg width="100%" height="450" viewBox="0 0 800 500" className="w-full h-auto">
              {bubbles.map((b, idx) => {
                const colors = getBubbleColors(b);
                return (
                  <g 
                    key={idx}
                    onClick={() => onSelectCategory(b.category)}
                    className="cursor-pointer group"
                  >
                    <circle
                      cx={b.x}
                      cy={b.y}
                      r={b.r}
                      fill={colors.fill}
                      stroke={colors.border}
                      strokeWidth="2.5"
                      className="transition-all duration-300 group-hover:fill-opacity-20 group-hover:scale-[1.03] origin-center"
                      style={{ transformOrigin: `${b.x}px ${b.y}px` }}
                    />
                    <text
                      x={b.x}
                      y={b.y - 4}
                      textAnchor="middle"
                      className="text-[12px] font-bold fill-slate-800 group-hover:fill-blue-600 transition-colors select-none"
                    >
                      {b.category}
                    </text>
                    <text
                      x={b.x}
                      y={b.y + 12}
                      textAnchor="middle"
                      className="text-[10px] font-bold fill-slate-400 select-none"
                    >
                      {b.customer_count} Cust ({b.complaint_count} tix)
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </Card>

        {/* Metrics table side panel (Col span 2) */}
        <Card className="lg:col-span-2 shadow-sm border-slate-200 p-4">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2 mb-3 select-none">
            <TableProperties className="h-4 w-4 text-blue-600" /> Category Metrics Table
          </div>
          <div className="overflow-y-auto max-h-[440px] pr-1">
            <Table>
              <TableHeader className="bg-slate-50 sticky top-0 z-10">
                <TableRow>
                  <TableHead className="font-bold text-xs text-slate-500 py-2 h-auto">Category</TableHead>
                  <TableHead className="font-bold text-xs text-slate-500 text-center py-2 h-auto">Custs</TableHead>
                  <TableHead className="font-bold text-xs text-slate-500 text-center py-2 h-auto">Tickets</TableHead>
                  <TableHead className="font-bold text-xs text-slate-500 text-right py-2 h-auto">Severity</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {clusters.map((c) => {
                  const crit = c.severity_breakdown.critical || 0;
                  const high = c.severity_breakdown.high || 0;
                  const med = c.severity_breakdown.medium || 0;
                  const low = c.severity_breakdown.low || 0;

                  return (
                    <TableRow 
                      key={c.category}
                      onClick={() => onSelectCategory(c.category)}
                      className="hover:bg-slate-50/50 cursor-pointer transition-colors"
                    >
                      <TableCell className="font-extrabold text-blue-600 text-xs py-2.5">
                        {c.category}
                      </TableCell>
                      <TableCell className="text-center font-bold text-xs py-2.5">{c.customer_count}</TableCell>
                      <TableCell className="text-center text-slate-500 text-xs py-2.5">{c.complaint_count}</TableCell>
                      <TableCell className="text-right py-2.5">
                        <div className="inline-flex gap-1">
                          {crit > 0 && <span className="bg-rose-100 text-rose-700 text-[8px] font-extrabold py-0.5 px-1.5 rounded-sm" title={`Critical: ${crit}`}>C:{crit}</span>}
                          {high > 0 && <span className="bg-amber-100 text-amber-700 text-[8px] font-extrabold py-0.5 px-1.5 rounded-sm" title={`High: ${high}`}>H:{high}</span>}
                          {med > 0 && <span className="bg-yellow-100 text-yellow-700 text-[8px] font-extrabold py-0.5 px-1.5 rounded-sm" title={`Medium: ${med}`}>M:{med}</span>}
                          {low > 0 && <span className="bg-emerald-100 text-emerald-700 text-[8px] font-extrabold py-0.5 px-1.5 rounded-sm" title={`Low: ${low}`}>L:{low}</span>}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </Card>
      </div>
    </div>
  );
}
