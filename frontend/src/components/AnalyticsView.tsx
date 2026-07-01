"use client";

import React from "react";
import { Complaint, Stats } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { 
  BarChart, Bar, Cell, LineChart, Line, PieChart, 
  Pie, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid 
} from "recharts";
import { AlertCircle, Bot, Building, Folder, Globe, Key, Mail, Network, Scale, TrendingUp } from "lucide-react";
import SentimentHeatmap from "./SentimentHeatmap";

interface AnalyticsViewProps {
  complaints: Complaint[];
  stats: Stats;
  trends: any;
}

export default function AnalyticsView({ complaints, stats, trends }: AnalyticsViewProps) {
  // Line chart volume trend
  const dailyTrendData = stats.daily_trend || [];

  // Channel breakdown
  const channelData = Object.entries(stats.by_channel || {}).map(([key, val]) => ({
    name: key.toUpperCase(),
    value: val
  }));
  const channelColors = ["#3b82f6", "#10b981", "#8b5cf6", "#f97316", "#ef4444", "#eab308"];

  // Category breakdown
  const categoryData = Object.entries(stats.by_category || {}).map(([key, val]) => ({
    name: key.replace(/_/g, " ").replace(/\b\w/g, x => x.toUpperCase()),
    value: val
  }));

  // Resolution status Pie
  const pendingCount = stats.pending || 0;
  const inReviewCount = complaints.filter(c => c.status === "in_review").length;
  const resolvedCount = stats.resolved || 0;
  const escalatedCount = stats.escalated || 0;

  const resolutionData = [
    { name: "Pending", value: pendingCount, color: "#f97316" },
    { name: "In Review", value: inReviewCount, color: "#3b82f6" },
    { name: "Resolved", value: resolvedCount, color: "#10b981" },
    { name: "Escalated", value: escalatedCount, color: "#8b5cf6" }
  ];

  return (
    <div className="space-y-6 font-sans">
      {/* Title */}
      <div className="flex items-center justify-between select-none">
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          <TrendingUp className="h-6 w-6 text-blue-600" /> Trend Analysis
        </h2>
      </div>

      {/* Row 1: Volume Trend and Channel Pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Line Chart */}
        <Card className="lg:col-span-2 shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <TrendingUp className="h-4 w-4 text-blue-600" /> 7-Day Complaint Volume Trend
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={dailyTrendData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ fontSize: "11px", borderRadius: "6px" }} />
                <Line type="monotone" dataKey="count" stroke="#2563eb" fill="rgba(37, 99, 235, 0.05)" strokeWidth={2.5} activeDot={{ r: 6 }} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Channel Doughnut */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <Network className="h-4 w-4 text-blue-600" /> By Channel
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={channelData} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={2} dataKey="value">
                  {channelData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={channelColors[index % channelColors.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `${value} tix`} contentStyle={{ fontSize: "10px", borderRadius: "6px" }} />
                <Legend layout="horizontal" align="center" verticalAlign="bottom" iconType="circle" iconSize={8} wrapperStyle={{ fontSize: "9px" }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Category Breakdown, Status Breakdown, Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Category Horizontal Bar */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <Folder className="h-4 w-4 text-blue-600" /> By Category
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categoryData} layout="vertical" margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
                <XAxis type="number" tick={{ fontSize: 9, fill: "#94a3b8" }} axisLine={false} tickLine={false} />
                <YAxis dataKey="name" type="category" tick={{ fontSize: 8, fill: "#64748b" }} axisLine={false} tickLine={false} width={80} />
                <Tooltip contentStyle={{ fontSize: "10px", borderRadius: "6px" }} />
                <Bar dataKey="value" fill="#8b5cf6" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Resolution Pie */}
        <Card className="shadow-sm border-slate-200">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
              <AlertCircle className="h-4 w-4 text-blue-600" /> Resolution Status
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={resolutionData} cx="50%" cy="50%" outerRadius={60} dataKey="value">
                  {resolutionData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip formatter={(value) => `${value} tix`} contentStyle={{ fontSize: "10px", borderRadius: "6px" }} />
                <Legend layout="horizontal" align="center" verticalAlign="bottom" iconType="circle" iconSize={8} wrapperStyle={{ fontSize: "9px" }} />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Key Metrics */}
        <Card className="shadow-sm border-slate-200 select-none">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2">
              <Key className="h-4 w-4 text-blue-600" /> Performance Metrics
            </CardTitle>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3 mt-2">
              <span className="text-xs font-semibold text-slate-500">Triage Automation Rate</span>
              <span className="text-lg font-black text-rose-600">60%</span>
            </div>
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <span className="text-xs font-semibold text-slate-500">Response Speedup (FRT)</span>
              <span className="text-lg font-black text-blue-600">40%</span>
            </div>
            <div className="flex items-center justify-between pb-1">
              <span className="text-xs font-semibold text-slate-500">RBI Compliance SLA</span>
              <span className="text-lg font-black text-emerald-600">100%</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Full Heatmap Panel */}
      <Card className="shadow-sm border-slate-200">
        <CardHeader className="p-4 border-b border-slate-100 bg-slate-50/20">
          <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-widest flex items-center gap-2 select-none">
            <Scale className="h-4 w-4 text-blue-600" /> Category Out-Frustration Heatmap
          </CardTitle>
          <CardDescription className="text-xs pt-1 select-none">
            Each cell represents complaint counts; color gradients show average customer anger/frustration indexes.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          <SentimentHeatmap complaints={complaints} />
        </CardContent>
      </Card>
    </div>
  );
}
