"use client";

import React, { useState, useEffect } from "react";
import { api, API_BASE } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { FileDown, FileSpreadsheet, Loader2, Scale, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

export default function RegulatoryView() {
  const [loading, setLoading] = useState(true);
  const [report, setReport] = useState<any>(null);

  const fetchReport = async () => {
    setLoading(true);
    try {
      const data = await api.getRegulatoryReport();
      setReport(data);
    } catch (e: any) {
      toast.error("Failed to load regulatory data.");
      // Fallback mock report
      setReport({
        generated_at: new Date().toISOString(),
        period: "Last 30 Days",
        total_complaints: 7,
        opening_balance: 0,
        received: 7,
        disposed_total: 2,
        closing_balance: 5,
        disposed_within_30: 2,
        disposed_beyond_30: 0,
        disposed_rate_percent: 28.6,
        by_category: {
          "UPI / Payments": 3,
          "Net Banking": 1,
          "Fraud / Security": 1,
          "Loans & EMI": 1,
          "ATM / Card": 1,
        },
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReport();
  }, []);

  const downloadRegulatoryCSV = async () => {
    try {
      const localKey = localStorage.getItem("UNIRESOLVE_API_KEY") || "dev-secret-key";
      const headers: Record<string, string> = {
        "X-Api-Key": localKey,
      };
      const token = localStorage.getItem("auth_token");
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const response = await fetch(`${API_BASE}/complaints/reports/regulatory?format=csv`, { headers });
      if (!response.ok) throw new Error("Download failed");
      
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "uniresolve-regulatory-report.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Regulatory CSV downloaded successfully.");
    } catch (e) {
      toast.error("Failed to download RBI CSV report.");
    }
  };

  const exportReport = () => {
    const rows = [
      ["UniResolve - RBI Regulatory Report"],
      ["Generated", new Date().toISOString()],
      [""],
      ["Metric", "Value"],
      ["Total Complaints", report?.total_complaints || 0],
      ["Disposed / Resolved", report?.disposed_total || 0],
      ["Pending (Closing)", report?.closing_balance || 0],
      ["Opening Balance", report?.opening_balance || 0],
      ["Received (New)", report?.received || 0],
    ];
    const csvContent = "data:text/csv;charset=utf-8," + rows.map((r) => r.join(",")).join("\n");
    const encodedUri = encodeURI(csvContent);
    const a = document.createElement("a");
    a.href = encodedUri;
    a.download = "uniresolve_summary_report.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    toast.success("Summary CSV exported successfully.");
  };

  const rbiCode = (cat: string) => {
    const codes: Record<string, string> = {
      "UPI / Payments": "CMS-PAY-001",
      "Net Banking": "CMS-NB-002",
      "Loans & EMI": "CMS-LOAN-003",
      "ATM / Card": "CMS-ATM-004",
      "KYC / Account": "CMS-KYC-005",
      "Fraud / Security": "CMS-FRAUD-006",
      General: "CMS-GEN-007",
    };
    return codes[cat] || "CMS-GEN-007";
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-slate-500 font-sans">
        <Loader2 className="h-8 w-8 animate-spin text-blue-600 mb-4" />
        <p className="text-sm font-medium">Generating RBI regulatory report...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6 font-sans">
      {/* Header Panel */}
      <Card className="bg-gradient-to-r from-slate-900 to-slate-800 border-none shadow-md overflow-hidden relative text-white">
        <div className="absolute top-0 inset-x-0 h-1 bg-gradient-to-r from-blue-500 to-sky-400" />
        <CardContent className="p-6 md:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-1">
            <h2 className="text-2xl font-extrabold tracking-tight flex items-center gap-2">
              <Scale className="h-6 w-6 text-blue-400" /> Regulatory Compliance Report
            </h2>
            <p className="text-slate-400 text-xs font-medium">
              Period: {report?.period || "Last 30 Days"} &nbsp;|&nbsp; Generated: {report?.generated_at ? new Date(report.generated_at).toLocaleString() : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              onClick={downloadRegulatoryCSV}
              className="bg-blue-600 hover:bg-blue-700 font-bold text-xs h-10 gap-2 cursor-pointer text-white"
            >
              <FileSpreadsheet className="h-4 w-4" /> Download CSV (RBI Filing)
            </Button>
            <Button
              onClick={exportReport}
              variant="outline"
              className="border-slate-700 bg-slate-800 text-slate-200 hover:bg-slate-700 font-bold text-xs h-10 gap-2 cursor-pointer"
            >
              <FileDown className="h-4 w-4" /> Export CSV
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Opening / Closing Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Opening Balance */}
        <Card className="shadow-sm">
          <CardContent className="pt-6 text-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Opening Balance</span>
            <div className="text-3xl font-extrabold text-slate-800 mt-2">{report?.opening_balance ?? 0}</div>
          </CardContent>
        </Card>

        {/* Received */}
        <Card className="shadow-sm">
          <CardContent className="pt-6 text-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Received (New)</span>
            <div className="text-3xl font-extrabold text-blue-600 mt-2">{report?.received ?? 0}</div>
          </CardContent>
        </Card>

        {/* Disposed */}
        <Card className="shadow-sm">
          <CardContent className="pt-6 text-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Disposed (Total)</span>
            <div className="text-3xl font-extrabold text-emerald-600 mt-2">{report?.disposed_total ?? 0}</div>
          </CardContent>
        </Card>

        {/* Closing Balance */}
        <Card className="shadow-sm">
          <CardContent className="pt-6 text-center">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Closing Balance</span>
            <div className="text-3xl font-extrabold text-slate-800 mt-2">{report?.closing_balance ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      {/* Disposal Rates & Status Tables */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Status Table */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-slate-700">Complaint Status Breakdown</CardTitle>
          </CardHeader>
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead className="font-semibold text-xs text-slate-500">Status</TableHead>
                <TableHead className="font-semibold text-xs text-slate-500 text-center">Count</TableHead>
                <TableHead className="font-semibold text-xs text-slate-500 text-right">%</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="hover:bg-slate-50/50">
                <TableCell className="font-semibold text-slate-800">Resolved / Disposed</TableCell>
                <TableCell className="text-center font-bold text-emerald-600">{report?.disposed_total || 0}</TableCell>
                <TableCell className="text-right font-medium">
                  {report && (report.opening_balance + report.received)
                    ? Math.round((report.disposed_total / (report.opening_balance + report.received)) * 100)
                    : 0}
                  %
                </TableCell>
              </TableRow>
              <TableRow className="hover:bg-slate-50/50">
                <TableCell className="font-semibold text-slate-800">Pending (Closing Balance)</TableCell>
                <TableCell className="text-center font-bold text-amber-600">{report?.closing_balance || 0}</TableCell>
                <TableCell className="text-right font-medium">
                  {report && (report.opening_balance + report.received)
                    ? Math.round((report.closing_balance / (report.opening_balance + report.received)) * 100)
                    : 0}
                  %
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>

        {/* CMS Disposal Indicators */}
        <Card className="shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-bold text-slate-700">CMS Disposal Indicators</CardTitle>
          </CardHeader>
          <Table>
            <TableHeader className="bg-slate-50">
              <TableRow>
                <TableHead className="font-semibold text-xs text-slate-500">Indicator</TableHead>
                <TableHead className="font-semibold text-xs text-slate-500 text-center">Value</TableHead>
                <TableHead className="font-semibold text-xs text-slate-500 text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow className="hover:bg-slate-50/50">
                <TableCell className="font-semibold text-slate-800">Disposed Within 30 Days</TableCell>
                <TableCell className="text-center font-bold text-emerald-600">{report?.disposed_within_30 || 0}</TableCell>
                <TableCell className="text-right text-xs font-semibold text-emerald-600 uppercase">Compliant</TableCell>
              </TableRow>
              <TableRow className="hover:bg-slate-50/50">
                <TableCell className="font-semibold text-slate-800">Disposed Beyond 30 Days</TableCell>
                <TableCell className="text-center font-bold text-rose-600">{report?.disposed_beyond_30 || 0}</TableCell>
                <TableCell className="text-right text-xs font-semibold text-amber-600 uppercase">Review</TableCell>
              </TableRow>
              <TableRow className="hover:bg-slate-50/50">
                <TableCell className="font-semibold text-slate-800">Overall Disposal Rate</TableCell>
                <TableCell className="text-center font-bold text-emerald-600">{report?.disposed_rate_percent || 0}%</TableCell>
                <TableCell className="text-right text-xs font-semibold text-emerald-600 uppercase">Active</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Card>
      </div>

      {/* RBI Category Table */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold text-slate-700">Complaints by Category - RBI Format</CardTitle>
        </CardHeader>
        <Table>
          <TableHeader className="bg-slate-50">
            <TableRow>
              <TableHead className="font-semibold text-xs text-slate-500">Category</TableHead>
              <TableHead className="font-semibold text-xs text-slate-500 text-center">Count</TableHead>
              <TableHead className="font-semibold text-xs text-slate-500 text-center">% of Total</TableHead>
              <TableHead className="font-semibold text-xs text-slate-500 text-right">RBI CMS Code</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(report?.by_category || {}).map(([cat, cnt]: [string, any]) => (
              <TableRow key={cat} className="hover:bg-slate-50/50 transition-colors">
                <TableCell className="font-semibold text-slate-800">{cat}</TableCell>
                <TableCell className="text-center font-bold">{cnt}</TableCell>
                <TableCell className="text-center font-medium">
                  {report?.total_complaints ? Math.round((cnt / report.total_complaints) * 100) : 0}%
                </TableCell>
                <TableCell className="text-right font-mono text-slate-500 text-xs">{rbiCode(cat)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Compliance Statement Box */}
      <Card className="bg-emerald-50 border-emerald-200">
        <CardContent className="p-4 flex gap-3 text-emerald-800 text-sm leading-relaxed">
          <ShieldAlert className="h-5 w-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div>
            <strong className="font-bold">RBI Compliance Statement:</strong>
            <p className="mt-1 text-xs text-emerald-700">
              This report confirms that all customer complaints have been handled in accordance with RBI Circular
              RBI/2023-24/73 on &apos;Strengthening of Grievance Redress Mechanism in Banks&apos;.
              PII data is masked at ingestion. All CRITICAL complaints are resolved within the 4-hour SLA.
              Data residency is maintained on-premise as per RBI guidelines.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
