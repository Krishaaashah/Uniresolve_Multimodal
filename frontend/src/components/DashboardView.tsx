"use client";

import React from "react";
import { Complaint, Stats } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { 
  BarChart as RechartsBarChart, Bar, Cell, LineChart as RechartsLineChart, Line, PieChart as RechartsPieChart, 
  Pie, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend 
} from "recharts";
import { AlertCircle, Bot, Building, Clock, Folder, Globe, Mail, Network, Phone, Plus, Search, ShieldAlert, Sparkles, TrendingUp } from "lucide-react";
import SentimentHeatmap from "./SentimentHeatmap";

interface DashboardViewProps {
  complaints: Complaint[];
  stats: Stats;
  trends: any;
  onNavigate: (view: string) => void;
  onInspect: (complaint: Complaint) => void;
  onOpenIngest: () => void;
}

export default function DashboardView({
  complaints,
  stats,
  trends,
  onNavigate,
  onInspect,
  onOpenIngest
}: DashboardViewProps) {
  
  const cleanText = (value: string = "") => {
    return value
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F\u200D]/gu, "")
      .replace(/\*/g, "")
      .replace(/^\s*complaint\s+summary:\s*/i, "")
      .replace(/\s{2,}/g, " ")
      .trim();
  };

  const channelIcon = (c: string) => {
    const icons: Record<string, React.ReactNode> = {
      app: <Phone className="h-3.5 w-3.5" />,
      email: <Mail className="h-3.5 w-3.5" />,
      social: <Network className="h-3.5 w-3.5" />,
      ivr: <Phone className="h-3.5 w-3.5" />,
      branch: <Building className="h-3.5 w-3.5" />,
      web: <Globe className="h-3.5 w-3.5" />,
    };
    return icons[c] || <Bot className="h-3.5 w-3.5" />;
  };

  const channelLabel = (c: string) => {
    const labels: Record<string, string> = {
      app: "Mobile App",
      email: "Email",
      social: "Social Media",
      ivr: "IVR / Call Center",
      branch: "Branch",
      web: "Web Portal",
    };
    return labels[c] || c;
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

  // Charts data processing
  const dailyTrendData = stats.daily_trend || [];
  
  const categoryData = Object.entries(stats.by_category || {}).map(([key, val]) => ({
    name: key.replace(/_/g, " ").replace(/\b\w/g, x => x.toUpperCase()),
    value: val
  }));

  const severityColors = ["#ef4444", "#f97316", "#eab308", "#10b981"];
  const severityData = [
    { name: "Critical", value: stats.by_severity?.critical || 0, color: "#ef4444" },
    { name: "High", value: stats.by_severity?.high || 0, color: "#f97316" },
    { name: "Medium", value: stats.by_severity?.medium || 0, color: "#eab308" },
    { name: "Low", value: stats.by_severity?.low || 0, color: "#10b981" }
  ];

  // Process Sparkline data from 7d trends
  const trendData = trends?.data || [];
  const sparklineMap: Record<string, number> = {};
  trendData.forEach((d: any) => {
    sparklineMap[d.date] = (sparklineMap[d.date] || 0) + d.count;
  });
  const sparklineData = Object.entries(sparklineMap).map(([date, count]) => ({
    date,
    count
  }));

  const categoryColors = ["#3b82f6", "#ef4444", "#8b5cf6", "#f97316", "#10b981", "#eab308", "#334155", "#64748b"];

  // Latest 5 complaints
  const sortedComplaints = [...complaints]
    .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime())
    .slice(0, 5);

  return (
    <div className="space-y-6 font-sans">
      {/* 6 Metric Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
        {/* Total */}
        <Card className="border-l-4 border-l-blue-600 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Total</span>
            <CardTitle className="text-2xl font-black text-blue-600 mt-1">{stats.total || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Omnichannel tix</span>
          </CardContent>
        </Card>

        {/* Pending */}
        <Card className="border-l-4 border-l-amber-500 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Pending</span>
            <CardTitle className="text-2xl font-black text-amber-500 mt-1">{stats.pending || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Awaiting action</span>
          </CardContent>
        </Card>

        {/* Resolved */}
        <Card className="border-l-4 border-l-emerald-500 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Resolved</span>
            <CardTitle className="text-2xl font-black text-emerald-600 mt-1">{stats.resolved || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Today: {stats.resolved_today || 0}</span>
          </CardContent>
        </Card>

        {/* Escalated */}
        <Card className="border-l-4 border-l-purple-500 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Escalated</span>
            <CardTitle className="text-2xl font-black text-purple-600 mt-1">{stats.escalated || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Level L2/L3/L4</span>
          </CardContent>
        </Card>

        {/* SLA Breached */}
        <Card className="border-l-4 border-l-rose-500 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">SLA Breached</span>
            <CardTitle className="text-2xl font-black text-rose-600 mt-1">{stats.sla_breached || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Compliance risk</span>
          </CardContent>
        </Card>

        {/* Systemic Alerts */}
        <Card className="border-l-4 border-l-cyan-500 shadow-sm">
          <CardHeader className="p-4 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Systemic</span>
            <CardTitle className="text-2xl font-black text-cyan-600 mt-1">{stats.systemic_alerts || 0}</CardTitle>
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <span className="text-[10px] text-slate-400">Outage clusters</span>
          </CardContent>
        </Card>
      </div>

      {/* 3 Main Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Trend Chart (Span 2) */}
        <Card className="lg:col-span-2 shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0 flex flex-row items-center justify-between">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <TrendingUp className="h-4 w-4 text-blue-600" /> 7-Day Complaint Trend
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[190px]">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsLineChart data={dailyTrendData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ fontSize: "11px", borderRadius: "6px" }} />
                <Line type="monotone" dataKey="count" stroke="#2563eb" fill="rgba(37, 99, 235, 0.05)" strokeWidth={2.5} activeDot={{ r: 6 }} dot={{ r: 3 }} />
              </RechartsLineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Category Doughnut Chart */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <Folder className="h-4 w-4 text-blue-600" /> By Category
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[190px]">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsPieChart>
                <Pie data={categoryData} cx="50%" cy="50%" innerRadius={42} outerRadius={62} paddingAngle={2} dataKey="value">
                  {categoryData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={categoryColors[index % categoryColors.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `${value} tickets`} contentStyle={{ fontSize: "10px", borderRadius: "6px" }} />
              </RechartsPieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Severity Bar Chart */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <AlertCircle className="h-4 w-4 text-blue-600" /> By Severity
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[190px]">
            <ResponsiveContainer width="100%" height="100%">
              <RechartsBarChart data={severityData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ fontSize: "11px", borderRadius: "6px" }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {severityData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Bar>
              </RechartsBarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Sparkline & Trends Row */}
      <Card className="shadow-sm border-slate-200">
        <CardContent className="p-4 flex flex-col md:flex-row items-center gap-6">
          <div className="w-full md:w-1/4 select-none">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">7d Sparkline volume</span>
            <div className="h-10 mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <RechartsLineChart data={sparklineData}>
                  <Line type="monotone" dataKey="count" stroke="#f97316" fill="rgba(249, 115, 22, 0.05)" strokeWidth={2} dot={false} />
                </RechartsLineChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div className="flex-1 text-xs leading-relaxed font-semibold text-slate-500 pl-1 border-t md:border-t-0 md:border-l border-slate-100 pt-4 md:pt-0 md:pl-6">
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block mb-1">AI Trend Summary</span>
            {trends?.summary || "Trend intelligence summaries streaming from AI classification model."}
          </div>
        </CardContent>
      </Card>

      {/* Sentiment Heatmap Summary */}
      <Card className="shadow-sm border-slate-200">
        <CardHeader className="p-4 border-b border-slate-100 bg-slate-50/20">
          <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
            <Search className="h-4 w-4 text-blue-600" /> Omni-Sentiment Triage Heatmap
          </CardTitle>
          <CardDescription className="text-xs pt-1 select-none">
            Color indicates average customer frustration score (green calm, yellow warning, red highly angry). Cells show complaint volumes.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          <SentimentHeatmap complaints={complaints} />
        </CardContent>
      </Card>

      {/* Recent Complaints Section Header */}
      <div className="flex items-center justify-between select-none pt-2">
        <h3 className="text-md font-extrabold text-slate-800 tracking-tight flex items-center gap-2">
          <Clock className="h-5 w-5 text-slate-500" /> Recent Complaints
        </h3>
        <Button 
          onClick={onOpenIngest} 
          className="bg-blue-600 hover:bg-blue-700 font-extrabold text-xs h-9 cursor-pointer text-white gap-1 shadow-sm"
        >
          <Plus className="h-4 w-4" /> New Complaint
        </Button>
      </div>

      {/* Latest 5 Complaints List */}
      <div className="flex flex-col gap-3">
        {sortedComplaints.map((c) => {
          const isBreached = c.sla?.status === "breached" && c.status !== "resolved";
          return (
            <Card 
              key={c.id} 
              onClick={() => onInspect(c)}
              className={`hover:shadow-md hover:border-blue-500 border-slate-200/80 transition-all duration-200 cursor-pointer overflow-hidden ${
                c.cluster?.systemic_alert ? "border-l-4 border-l-rose-500" : isBreached ? "border-l-4 border-l-rose-500" : ""
              }`}
            >
              <CardContent className="p-4 space-y-2">
                <div className="flex items-start justify-between flex-wrap gap-2 text-xs">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant="secondary" className="font-extrabold text-[10px] text-blue-600 bg-blue-50 border border-blue-200 uppercase">{c.ticket_id || "TKT-PENDING"}</Badge>
                    {c.parent_ticket_id && (
                      <Badge variant="secondary" className="bg-rose-50 border border-rose-200 text-rose-700 text-[9px] font-extrabold uppercase select-none">Duplicate of {c.parent_ticket_id}</Badge>
                    )}
                    <span className="flex items-center gap-1.5 text-slate-500 select-none">
                      {channelIcon(c.channel)} {channelLabel(c.channel)}
                    </span>
                    <Badge variant="secondary" className={`text-[9px] font-bold uppercase ${
                      c.triage?.severity === "critical" ? "bg-rose-100 text-rose-700" :
                      c.triage?.severity === "high" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-700"
                    }`}>{c.triage?.severity}</Badge>
                    <Badge variant="secondary" className={`text-[9px] font-bold uppercase ${
                      c.triage?.sentiment === "angry" ? "bg-rose-100 text-rose-700" :
                      c.triage?.sentiment === "frustrated" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-700"
                    }`}>{c.triage?.sentiment}</Badge>
                    <Badge className={`text-[9px] font-extrabold uppercase hover:bg-transparent ${
                      c.status === "resolved" ? "bg-emerald-50 text-emerald-700 border-emerald-200" :
                      c.status === "escalated" ? "bg-rose-50 text-rose-700 border-rose-200 animate-pulse" :
                      "bg-amber-50 text-amber-700 border-amber-200"
                    }`} variant="outline">
                      {c.status.replace("_", " ")}
                    </Badge>
                  </div>
                  <span className="text-[10px] text-slate-400 font-semibold select-none">{timeAgo(c.received_at)}</span>
                </div>

                {c.triage?.key_issue && (
                  <div className="text-xs font-bold text-blue-700 inline-flex items-center gap-1.5 bg-blue-50/50 py-1 px-3 rounded-md select-none">
                    <Search className="h-3 w-3" /> {cleanText(c.triage.key_issue)}
                  </div>
                )}

                <p className="text-xs font-medium leading-relaxed text-slate-700 break-words mt-1 line-clamp-2">
                  {cleanText(c.summary || c.masked_text || "")}
                </p>

                <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 pt-1.5 border-t border-slate-100 select-none">
                  <span className="flex items-center gap-1"><Folder className="h-3 w-3" /> {c.triage?.category || "General"}</span>
                  
                  <div className="flex items-center gap-2">
                    {c.cluster?.systemic_alert && (
                      <Badge className="bg-rose-600 text-white font-extrabold animate-pulse text-[9px]">SYSTEMIC ALERT</Badge>
                    )}
                    {isBreached && (
                      <Badge className="bg-rose-500 text-white font-extrabold animate-pulse text-[9px]">SLA BREACH</Badge>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
