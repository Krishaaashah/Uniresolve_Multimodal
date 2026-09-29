"use client";

import React from "react";
import { Complaint } from "@/lib/api";

interface SentimentHeatmapProps {
  complaints: Complaint[];
}

export default function SentimentHeatmap({ complaints }: SentimentHeatmapProps) {
  const channels = ['app', 'web', 'email', 'ivr', 'branch', 'social'];
  const categories = ['upi', 'atm', 'credit_card', 'loan', 'account', 'netbanking', 'fraud', 'kyc', 'general'];
  
  const chanLabels: Record<string, string> = {
    app: 'Mobile App',
    web: 'Web Portal',
    email: 'Email',
    ivr: 'IVR / Voice',
    branch: 'Branch Visit',
    social: 'Social Media'
  };

  const catLabels: Record<string, string> = {
    upi: 'UPI Payments',
    atm: 'ATM & Cash',
    credit_card: 'Cards',
    loan: 'Loans & EMI',
    account: 'Account & Branch',
    netbanking: 'NetBanking',
    fraud: 'Fraud & Sec',
    kyc: 'KYC Services',
    general: 'General'
  };

  const scores: Record<string, number> = {
    angry: 1.0,
    frustrated: 0.7,
    neutral: 0.3,
    satisfied: 0.0
  };

  const normalizeCategory = (rawCat?: string): string => {
    if (!rawCat) return 'general';
    const c = rawCat.toLowerCase();
    if (c.includes('upi')) return 'upi';
    if (c.includes('atm') || c.includes('cash')) return 'atm';
    if (c.includes('card') || c.includes('pos')) return 'credit_card';
    if (c.includes('loan') || c.includes('emi') || c.includes('foreclosure') || c.includes('deduction')) return 'loan';
    if (c.includes('netbanking') || c.includes('portal') || c.includes('login') || c.includes('password')) return 'netbanking';
    if (c.includes('fraud') || c.includes('unauthorized') || c.includes('phishing')) return 'fraud';
    if (c.includes('kyc') || c.includes('aadhaar') || c.includes('pan')) return 'kyc';
    if (c.includes('account') || c.includes('signature') || c.includes('passbook') || c.includes('fd') || c.includes('deposit') || c.includes('cheque') || c.includes('locker') || c.includes('branch') || c.includes('staff')) return 'account';
    return 'general';
  };

  // Build grid data
  const grid: Record<string, number> = {};
  const counts: Record<string, number> = {};

  complaints.forEach((c) => {
    if (!c.triage) return;
    const ch = c.channel;
    const cat = normalizeCategory(c.triage.category);
    const key = `${ch}|${cat}`;
    
    const sentiment = c.triage.sentiment || 'neutral';
    grid[key] = (grid[key] || 0) + (scores[sentiment] ?? 0.3);
    counts[key] = (counts[key] || 0) + 1;
  });

  const getHeatmapColor = (ch: string, cat: string) => {
    const key = `${ch}|${cat}`;
    const cnt = counts[key] || 0;
    if (cnt === 0) return 'rgb(248, 250, 252)'; // slate-50
    
    const val = grid[key] / cnt; // average sentiment score [0..1]
    
    // Smooth interpolations: calm (emerald) -> warning (amber) -> angry (rose/red)
    const r = Math.round(56 + (225 - 56) * val);
    const g = Math.round(161 + (45 - 161) * val);
    const b = Math.round(105 + (57 - 105) * val);
    return `rgb(${r}, ${g}, ${b})`;
  };

  return (
    <div className="w-full space-y-4">
      <div className="overflow-x-auto rounded-lg border border-slate-200 shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-xs border-collapse">
          <thead>
            <tr className="bg-slate-100/70">
              <th className="px-3 py-2.5 text-left font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200">
                Channel
              </th>
              {categories.map((cat) => (
                <th
                  key={cat}
                  className="px-2 py-2.5 text-center font-bold text-slate-600 uppercase tracking-wider border-b border-slate-200 whitespace-nowrap"
                >
                  {catLabels[cat] || cat}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-slate-100">
            {channels.map((ch) => (
              <tr key={ch} className="hover:bg-slate-50/50 transition-colors">
                <td className="px-3 py-2.5 font-bold text-slate-800 bg-slate-50/70 border-r border-slate-200 whitespace-nowrap">
                  {chanLabels[ch] || ch}
                </td>
                {categories.map((cat) => {
                  const key = `${ch}|${cat}`;
                  const cnt = counts[key] || 0;
                  const bgColor = getHeatmapColor(ch, cat);
                  const isPopulated = cnt > 0;
                  const averageVal = isPopulated ? grid[key] / cnt : 0;
                  const textCol = isPopulated && averageVal > 0.4 ? 'text-white' : 'text-slate-800';

                  return (
                    <td
                      key={cat}
                      style={{ backgroundColor: bgColor }}
                      title={`${chanLabels[ch]} × ${catLabels[cat] || cat}: ${cnt} complaints (avg sentiment: ${averageVal.toFixed(2)})`}
                      className={`px-2 py-2 text-center font-extrabold border-r border-slate-200/60 last:border-r-0 cursor-default select-none transition-all duration-200 ${textCol}`}
                    >
                      {cnt > 0 ? cnt : <span className="text-slate-300 font-normal">-</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 text-xs text-slate-500 px-1">
        <span className="font-semibold text-emerald-600">Calm / Satisfied</span>
        <div className="flex-1 h-2 rounded-full bg-gradient-to-r from-emerald-500 via-amber-400 to-rose-600 border border-slate-200" />
        <span className="font-semibold text-rose-600">Frustrated / Escalated</span>
      </div>
    </div>
  );
}
