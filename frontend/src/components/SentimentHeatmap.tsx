"use client";

import React from "react";
import { Complaint } from "@/lib/api";

interface SentimentHeatmapProps {
  complaints: Complaint[];
}

export default function SentimentHeatmap({ complaints }: SentimentHeatmapProps) {
  const channels = ['app', 'email', 'social', 'ivr', 'branch', 'web'];
  const categories = ['mobile_banking', 'account', 'loan', 'credit_card', 'insurance', 'investment', 'fraud', 'general'];
  
  const chanLabels: Record<string, string> = {
    app: 'Mobile App',
    email: 'Email',
    social: 'Social',
    ivr: 'IVR / Phone',
    branch: 'Branch',
    web: 'Web Portal'
  };

  const catLabels: Record<string, string> = {
    mobile_banking: 'Mobile Banking',
    account: 'Account',
    loan: 'Loan & EMI',
    credit_card: 'Credit Card',
    insurance: 'Insurance',
    investment: 'Investment',
    fraud: 'Fraud / Sec',
    general: 'General'
  };

  const scores: Record<string, number> = {
    angry: 1.0,
    frustrated: 0.7,
    neutral: 0.3,
    satisfied: 0.0
  };

  // Build grid data
  const grid: Record<string, number> = {};
  const counts: Record<string, number> = {};

  complaints.forEach((c) => {
    if (!c.triage) return;
    const ch = c.channel;
    const cat = c.triage.category?.toLowerCase().replace(/ \/ /g, '_').replace(/ & /g, '_').replace(/ /g, '_') || 'general';
    const key = `${ch}|${cat}`;
    
    const sentiment = c.triage.sentiment || 'neutral';
    grid[key] = (grid[key] || 0) + (scores[sentiment] ?? 0.3);
    counts[key] = (counts[key] || 0) + 1;
  });

  const getHeatmapColor = (ch: string, cat: string) => {
    const key = `${ch}|${cat}`;
    const cnt = counts[key] || 0;
    if (cnt === 0) return 'var(--color-bg-secondary, rgb(241, 245, 249))'; // default slate-100 fallback
    
    const val = grid[key] / cnt; // average sentiment score [0..1]
    
    // Smooth interpolations: calm (green) -> warning (yellow) -> angry (red)
    // We'll use nice modern HSL/RGB colors
    const r = Math.round(56 + (227 - 56) * val);
    const g = Math.round(161 + (62 - 161) * val);
    const b = Math.round(105 + (62 - 105) * val);
    return `rgb(${r}, ${g}, ${b})`;
  };

  return (
    <div className="w-full space-y-4">
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50">
              <th className="px-3 py-2 text-left font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                Channel
              </th>
              {categories.map((cat) => (
                <th
                  key={cat}
                  className="px-2 py-2 text-center font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200"
                >
                  {catLabels[cat] || cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-100">
            {channels.map((ch) => (
              <tr key={ch} className="hover:bg-slate-50 transition-colors">
                <td className="px-3 py-2.5 font-medium text-slate-800 bg-slate-50/50 border-r border-slate-200 whitespace-nowrap">
                  {chanLabels[ch] || ch}
                </td>
                {categories.map((cat) => {
                  const key = `${ch}|${cat}`;
                  const cnt = counts[key] || 0;
                  const bgColor = getHeatmapColor(ch, cat);
                  const isPopulated = cnt > 0;
                  const averageVal = isPopulated ? grid[key] / cnt : 0;
                  const textCol = isPopulated && averageVal > 0.5 ? 'text-white' : 'text-slate-900';

                  return (
                    <td
                      key={cat}
                      style={{ backgroundColor: bgColor }}
                      title={`${chanLabels[ch]} / ${catLabels[cat] || cat}: ${cnt} complaints (avg sentiment value: ${averageVal.toFixed(2)})`}
                      className={`px-2 py-2 text-center font-bold border-r border-slate-100 last:border-r-0 cursor-default select-none transition-all duration-300 ${textCol}`}
                    >
                      {cnt || ""}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-500 px-1">
        <span className="font-semibold text-emerald-600">Calm (Satisfied)</span>
        <div className="flex-1 h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-600 border border-slate-200" />
        <span className="font-semibold text-rose-600">Angry (Escalated)</span>
      </div>
    </div>
  );
}
