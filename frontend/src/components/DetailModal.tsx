"use client";

import React, { useState, useEffect } from "react";
import { Complaint, api, CustomerProfile, AuditLog, TimelineProgress, approveComplaintDraft, provideComplaintInfo, verifyComplaintLedger } from "@/lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { 
  Bot, Clock, FileAudio, FileImage, FileText, FileVideo, 
  History, Info, Key, Loader2, Send, Shield, Sparkles, Ticket, User, UserPlus, ShieldAlert, ArrowUp 
} from "lucide-react";
import { toast } from "sonner";
import SlaProgressBar from "./SlaProgressBar";

interface DetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  complaintId: string | null;
  currentUserRole: string;
  onActionCompleted: () => void;
  onOpenEscalate: (id: string) => void;
}

export default function DetailModal({
  isOpen,
  onClose,
  complaintId,
  currentUserRole,
  onActionCompleted,
  onOpenEscalate
}: DetailModalProps) {
  const [complaint, setComplaint] = useState<Complaint | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  
  // Tab loading states
  const [loading, setLoading] = useState(false);
  const [customer, setCustomer] = useState<CustomerProfile | null>(null);
  const [loadingCustomer, setLoadingCustomer] = useState(false);
  const [cbsSearchId, setCbsSearchId] = useState("");
  
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([]);
  const [loadingAudit, setLoadingAudit] = useState(false);
  
  const [timeline, setTimeline] = useState<TimelineProgress | null>(null);
  const [loadingTimeline, setLoadingTimeline] = useState(false);

  const [aiExplanation, setAiExplanation] = useState<string | null>(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);

  // Raw vs Masked text toggle
  const [showRawText, setShowRawText] = useState(false);
  
  // AI Response Draft state
  const [suggestedResponse, setSuggestedResponse] = useState("");

  // History tab reply state
  const [replyText, setReplyText] = useState("");
  const [sendingReply, setSendingReply] = useState(false);

  // Multi-Agent Pipeline states
  const [ledgerValid, setLedgerValid] = useState<boolean | null>(null);
  const [loadingLedger, setLoadingLedger] = useState(false);
  const [approveLoading, setApproveLoading] = useState(false);
  const [infoLoading, setInfoLoading] = useState(false);
  const [infoTxnRef, setInfoTxnRef] = useState("");
  const [infoAmount, setInfoAmount] = useState("");

  const fetchComplaintDetails = async () => {
    if (!complaintId) return;
    setLoading(true);
    try {
      const complaintsList = await api.getComplaints();
      const match = complaintsList.find(c => c.id === complaintId);
      if (match) {
        setComplaint(match);
        setSuggestedResponse(match.triage?.suggested_response || "");
        
        // Auto-fetch secondary details based on active tab
        if (activeTab === "overview") {
          loadOverviewDetails(match);
        } else if (activeTab === "history") {
          // no additional fetch needed
        } else if (activeTab === "sla") {
          // no additional fetch needed
        } else if (activeTab === "escalation") {
          // no additional fetch needed
        } else if (activeTab === "audit") {
          loadAuditDetails(match.id);
        }
      }
    } catch (e) {
      toast.error("Failed to load ticket details.");
    } finally {
      setLoading(false);
    }
  };

  const loadOverviewDetails = async (c: Complaint) => {
    loadTimelineProgress(c.id);
    loadLedgerStatus(c.id);
    if (c.customer_id) {
      loadCustomerCBS(c.customer_id);
    } else {
      setCustomer(null);
    }
  };

  const loadLedgerStatus = async (id: string) => {
    setLoadingLedger(true);
    try {
      const res = await verifyComplaintLedger(id);
      setLedgerValid(res.valid);
    } catch (e) {
      setLedgerValid(null);
    } finally {
      setLoadingLedger(false);
    }
  };

  const handleApprovePipelineDraft = async () => {
    if (!complaint) return;
    setApproveLoading(true);
    try {
      const res = await approveComplaintDraft(complaint.id);
      if (res.success) {
        toast.success("Supervisor approval granted. Pipeline resumed!");
        fetchComplaintDetails();
        onActionCompleted();
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to approve draft.");
    } finally {
      setApproveLoading(false);
    }
  };

  const handleProvideMissingDetails = async () => {
    if (!complaint) return;
    setInfoLoading(true);
    try {
      const amt = parseFloat(infoAmount);
      const res = await provideComplaintInfo(complaint.id, infoTxnRef || undefined, isNaN(amt) ? undefined : amt);
      if (res.success) {
        toast.success("Missing details submitted! Multi-agent pipeline resumed.");
        setInfoTxnRef("");
        setInfoAmount("");
        fetchComplaintDetails();
        onActionCompleted();
      }
    } catch (e: any) {
      toast.error(e.message || "Failed to submit details.");
    } finally {
      setInfoLoading(false);
    }
  };

  const loadCustomerCBS = async (customerId: string) => {
    setLoadingCustomer(true);
    try {
      const profile = await api.getCustomer(customerId);
      setCustomer(profile);
    } catch (e) {
      setCustomer(null);
    } finally {
      setLoadingCustomer(false);
    }
  };

  const loadAuditDetails = async (id: string) => {
    setLoadingAudit(true);
    try {
      const logs = await api.getAudit(id);
      setAuditLogs(logs);
    } catch (e) {
      setAuditLogs([]);
    } finally {
      setLoadingAudit(false);
    }
  };

  const loadTimelineProgress = async (id: string) => {
    setLoadingTimeline(true);
    try {
      const t = await api.getTimeline(id);
      setTimeline(t);
    } catch (e) {
      setTimeline(null);
    } finally {
      setLoadingTimeline(false);
    }
  };

  const triggerAuditExplanation = async () => {
    if (!complaint) return;
    setLoadingExplanation(true);
    setAiExplanation(null);
    try {
      const res = await api.getExplain(complaint.id);
      setAiExplanation(res.explanation);
    } catch (e) {
      setAiExplanation("Failed to load classification audit explanation.");
    } finally {
      setLoadingExplanation(false);
    }
  };

  useEffect(() => {
    if (isOpen && complaintId) {
      setShowRawText(false);
      setAiExplanation(null);
      setReplyText("");
      fetchComplaintDetails();
    } else {
      setComplaint(null);
      setCustomer(null);
      setTimeline(null);
      setAuditLogs([]);
    }
  }, [isOpen, complaintId]);

  // Refetch if tab changes
  useEffect(() => {
    if (complaint) {
      if (activeTab === "overview") {
        loadOverviewDetails(complaint);
      } else if (activeTab === "audit") {
        loadAuditDetails(complaint.id);
      }
    }
  }, [activeTab]);

  const handleAction = async (action: "approve" | "reject") => {
    if (!complaint) return;
    try {
      await api.doAction(complaint.id, action, suggestedResponse);
      const msg = action === "approve" ? "Response approved and sent to customer." : "Complaint marked for further review.";
      toast.success(msg);
      onActionCompleted();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to process action.");
    }
  };

  const handleLinkCustomer = async () => {
    if (!complaint || !cbsSearchId.trim()) return;
    try {
      const res = await api.linkCustomer(complaint.id, cbsSearchId.trim());
      if (res.success) {
        toast.success("Linked complaint to customer CBS profile.");
        setCbsSearchId("");
        fetchComplaintDetails();
      }
    } catch (err) {
      toast.error("Customer ID not found in Core Banking System.");
    }
  };

  const handleUnlinkCustomer = async () => {
    if (!complaint) return;
    try {
      await api.linkCustomer(complaint.id, null);
      toast.success("CBS customer link cleared.");
      setCustomer(null);
      fetchComplaintDetails();
    } catch (err) {
      toast.error("Failed to clear customer link.");
    }
  };

  const handleSendReply = async () => {
    if (!complaint || !replyText.trim()) return;
    setSendingReply(true);
    try {
      await api.sendReply(complaint.id, replyText);
      toast.success("Reply message sent successfully.");
      setReplyText("");
      fetchComplaintDetails();
    } catch (err: any) {
      toast.error(err.message || "Failed to send message.");
    } finally {
      setSendingReply(false);
    }
  };

  const cleanText = (value: string = "") => {
    return value
      .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\uFE0F\u200D]/gu, "")
      .replace(/\*/g, "")
      .replace(/^\s*complaint\s+summary:\s*/i, "")
      .replace(/\s{2,}/g, " ")
      .trim();
  };

  const formatDt = (iso: string) => {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const channelMeta = (c: string) => {
    const metas: Record<string, { label: string }> = {
      app: { label: "Mobile App" },
      email: { label: "Email" },
      social: { label: "Social Media" },
      ivr: { label: "IVR / Phone" },
      branch: { label: "Branch" },
      web: { label: "Web Portal" },
    };
    return metas[c] || { label: "Other" };
  };

  const renderAttachments = (c: Complaint) => {
    const attachments = c.channel_metadata?.attachments || [];
    if (attachments.length === 0) return null;

    return (
      <div className="space-y-2 mt-4 select-none">
        <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Multimodal Evidence / Attachments ({attachments.length})
        </div>
        <div className="grid grid-cols-1 gap-3">
          {attachments.map((att, idx) => {
            const isImage = att.type.startsWith("image/");
            const isAudio = att.type.startsWith("audio/");
            const isVideo = att.type.startsWith("video/");
            const fileUrl = att.url.startsWith("/") || att.url.startsWith("http") ? att.url : `/${att.url}`;

            return (
              <div key={idx} className="p-3 border border-slate-200 rounded-lg bg-white shadow-sm flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                  <div className="flex items-center gap-2">
                    <FileText className="h-4 w-4 text-slate-400" />
                    Evidence File #{idx + 1}
                  </div>
                  {isAudio && (
                    <span className="text-[10px] bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full font-bold border border-blue-100">
                      IVR Speech Note (Audible)
                    </span>
                  )}
                  {isImage && (
                    <span className="text-[10px] bg-amber-50 text-amber-700 px-2 py-0.5 rounded-full font-bold border border-amber-100">
                      OCR Evidence Image
                    </span>
                  )}
                </div>
                {isImage && (
                  <a href={fileUrl} target="_blank" rel="noreferrer" className="block max-w-full">
                    <img src={fileUrl} alt="Evidence" className="max-h-60 rounded border object-contain mx-auto bg-slate-50 cursor-zoom-in hover:scale-[1.01] transition-transform duration-250" />
                  </a>
                )}
                {isAudio && (
                  <div className="bg-slate-50 p-2 rounded border border-slate-200">
                    <audio controls src={fileUrl} className="w-full outline-none" preload="auto" />
                  </div>
                )}
                {isVideo && (
                  <video controls src={fileUrl} className="w-full max-h-72 rounded border bg-black mt-1" />
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (!isOpen || !complaintId) return null;

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-4xl w-full h-[92vh] font-sans border-slate-200 flex flex-col p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-5 pb-3 border-b border-slate-100 flex-shrink-0">
          <DialogTitle className="text-xl font-black text-slate-900 tracking-tight flex items-center gap-2">
            <Ticket className="h-5 w-5 text-blue-600" /> 
            {complaint ? cleanText(complaint.triage?.key_issue || "Complaint details") : "Loading..."}
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center text-slate-500">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600 mb-2" />
            <p className="text-sm font-medium">Fetching complaint lifecycle data...</p>
          </div>
        ) : complaint ? (
          <div className="flex-1 overflow-hidden flex flex-col">
            {/* Tabs Trigger Navigation */}
            <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 overflow-hidden flex flex-col">
              <div className="px-6 bg-slate-50/50 border-b border-slate-100 flex-shrink-0">
                <TabsList className="bg-transparent p-0 gap-6 border-b-0 h-11">
                  <TabsTrigger value="overview" className="border-b-2 rounded-none px-0 py-2.5 h-full font-bold text-xs uppercase tracking-wider text-slate-400 hover:text-slate-800 data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 shadow-none">Overview</TabsTrigger>
                  <TabsTrigger value="history" className="border-b-2 rounded-none px-0 py-2.5 h-full font-bold text-xs uppercase tracking-wider text-slate-400 hover:text-slate-800 data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 shadow-none">History</TabsTrigger>
                  <TabsTrigger value="sla" className="border-b-2 rounded-none px-0 py-2.5 h-full font-bold text-xs uppercase tracking-wider text-slate-400 hover:text-slate-800 data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 shadow-none">SLA Metrics</TabsTrigger>
                  <TabsTrigger value="escalation" className="border-b-2 rounded-none px-0 py-2.5 h-full font-bold text-xs uppercase tracking-wider text-slate-400 hover:text-slate-800 data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 shadow-none">Escalation</TabsTrigger>
                  <TabsTrigger value="audit" className="border-b-2 rounded-none px-0 py-2.5 h-full font-bold text-xs uppercase tracking-wider text-slate-400 hover:text-slate-800 data-[state=active]:border-blue-600 data-[state=active]:text-blue-600 shadow-none">Audit Trail</TabsTrigger>
                </TabsList>
              </div>

              {/* Scrollable Content Panes */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                
                {/* 1. OVERVIEW TAB */}
                <TabsContent value="overview" className="mt-0 space-y-6">
                  {/* Stepper Timeline Progress */}
                  {loadingTimeline ? (
                    <div className="p-4 bg-slate-50 border border-slate-100 rounded-lg flex items-center justify-center text-xs text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" />
                      Querying lifecycle stepper...
                    </div>
                  ) : timeline ? (
                    <Card className="bg-slate-50/50 border-slate-200">
                      <CardContent className="p-4">
                        <div className="flex items-center justify-between mb-4">
                          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest flex items-center gap-1.5 select-none">
                            <Clock className="h-3.5 w-3.5" /> Ticket Lifecycle Progress
                          </span>
                          <span className="text-xs py-1 px-3 bg-blue-50 border border-blue-200 text-blue-700 font-extrabold rounded-md select-none">
                            Active: {timeline.current_stage} (Elapsed: {timeline.elapsed_time})
                          </span>
                        </div>
                        {/* Stepper Layout */}
                        <div className="relative flex justify-between items-start mt-6 px-4">
                          {/* Horizontal connecting track */}
                          <div className="absolute top-3 left-[12%] right-[12%] h-1 bg-slate-200 z-0">
                            <div 
                              className="h-full bg-blue-600 transition-all duration-400" 
                              style={{ 
                                width: timeline.current_stage === "Seen" ? "33%" 
                                     : timeline.current_stage === "In Progress / Escalated" ? "66%"
                                     : timeline.current_stage === "Resolved" ? "100%" : "0%"
                              }} 
                            />
                          </div>
                          {timeline.steps.map((step, idx) => {
                            const isDone = step.completed;
                            const isCurrent = timeline.current_stage === step.stage;
                            return (
                              <div key={idx} className="relative z-10 flex flex-col items-center text-center w-[20%] select-none">
                                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-white font-extrabold text-xs transition-all duration-300 ${
                                  isDone ? "bg-blue-600" : "bg-slate-300"
                                } ${isCurrent ? "ring-4 ring-blue-100" : ""}`}>
                                  {isDone ? "✓" : idx + 1}
                                </div>
                                <span className={`text-[11px] font-bold mt-2 ${isDone ? "text-slate-800" : "text-slate-400"}`}>
                                  {step.stage}
                                </span>
                                {step.timestamp && (
                                  <span className="text-[9px] text-slate-400 mt-1 font-semibold">
                                    {formatDt(step.timestamp).split(",")[0]}
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </CardContent>
                    </Card>
                  ) : null}

                  {/* Metadata Grid */}
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                    <div className="p-3 bg-slate-50/50 rounded-lg border border-slate-100">
                      <Label className="text-[10px] text-slate-400 uppercase font-bold">Ticket ID</Label>
                      <p className="font-extrabold text-slate-800 mt-0.5">{complaint.ticket_id || "TKT-PENDING"}</p>
                    </div>
                    <div className="p-3 bg-slate-50/50 rounded-lg border border-slate-100">
                      <Label className="text-[10px] text-slate-400 uppercase font-bold">Channel</Label>
                      <p className="font-extrabold text-slate-800 mt-0.5">{channelMeta(complaint.channel).label}</p>
                    </div>
                    <div className="p-3 bg-slate-50/50 rounded-lg border border-slate-100">
                      <Label className="text-[10px] text-slate-400 uppercase font-bold">Category</Label>
                      <p className="font-extrabold text-slate-800 mt-0.5">{complaint.triage?.category || "General"}</p>
                    </div>
                    <div className="p-3 bg-slate-50/50 rounded-lg border border-slate-100">
                      <Label className="text-[10px] text-slate-400 uppercase font-bold">Severity</Label>
                      <p className="mt-0.5">
                        <Badge variant="secondary" className={`text-[10px] font-extrabold uppercase ${
                          complaint.triage?.severity === "critical" ? "bg-rose-100 text-rose-700" :
                          complaint.triage?.severity === "high" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-700"
                        }`}>
                          {complaint.triage?.severity || "medium"}
                        </Badge>
                      </p>
                    </div>
                  </div>

                  {/* CBS Integration Profile */}
                  <Card className="shadow-sm border-slate-200">
                    <CardHeader className="py-4 border-b border-slate-100 bg-slate-50/20">
                      <CardTitle className="text-sm font-bold text-slate-700 flex items-center gap-2">
                        <User className="h-4 w-4 text-blue-600" /> Customer 360° Profile (CBS Connection)
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      {loadingCustomer ? (
                        <div className="py-4 flex items-center justify-center text-xs text-slate-500">
                          <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" /> Querying CBS...
                        </div>
                      ) : customer ? (
                        <div className="space-y-4">
                          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-100 pb-3">
                            <div>
                              <div className="font-extrabold text-slate-800 text-sm flex items-center gap-2">
                                {customer.name}
                                <Badge className="bg-emerald-100 text-emerald-800 font-extrabold text-[9px] uppercase hover:bg-emerald-100">{customer.kyc_status} KYC</Badge>
                                <Badge className="bg-amber-100 text-amber-800 font-extrabold text-[9px] uppercase hover:bg-amber-100">{customer.risk_tier} RISK</Badge>
                              </div>
                              <div className="text-slate-400 text-xs mt-1">ID: {customer.id} &nbsp;|&nbsp; Acct: {customer.account_no} ({customer.account_type})</div>
                            </div>
                            <Button 
                              variant="link" 
                              onClick={handleUnlinkCustomer}
                              className="text-slate-400 hover:text-rose-500 font-bold text-xs p-0 h-auto cursor-pointer"
                            >
                              Unlink
                            </Button>
                          </div>
                          <div className="grid grid-cols-2 gap-4 text-xs">
                            <div><span className="text-slate-400 font-semibold">Phone:</span> <strong className="text-slate-700">{customer.phone}</strong></div>
                            <div><span className="text-slate-400 font-semibold">Balance:</span> <strong className="text-emerald-600">{customer.balance}</strong></div>
                          </div>
                          {/* CBS Transaction Logs */}
                          <div className="space-y-2 pt-2">
                            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Recent Transaction Logs</span>
                            <div className="border border-slate-100 rounded-md overflow-hidden">
                              <Table className="text-[11px]">
                                <TableHeader className="bg-slate-50">
                                  <TableRow>
                                    <TableHead className="py-2 h-auto text-slate-500 font-bold">Date</TableHead>
                                    <TableHead className="py-2 h-auto text-slate-500 font-bold">Description</TableHead>
                                    <TableHead className="py-2 h-auto text-slate-500 font-bold">Amount</TableHead>
                                    <TableHead className="py-2 h-auto text-slate-500 font-bold text-right">Status</TableHead>
                                  </TableRow>
                                </TableHeader>
                                <TableBody>
                                  {customer.transactions.map((t, i) => (
                                    <TableRow key={i} className="hover:bg-slate-50/50">
                                      <TableCell className="py-2">{t.date}</TableCell>
                                      <TableCell className="py-2 font-bold text-slate-700">{t.desc}</TableCell>
                                      <TableCell className={`py-2 font-bold ${t.amount.startsWith("-") ? "text-rose-600" : "text-emerald-600"}`}>{t.amount}</TableCell>
                                      <TableCell className="py-2 text-right">
                                        <Badge className={`text-[9px] font-extrabold py-0.5 px-2 hover:bg-transparent ${t.status === "Success" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-rose-50 text-rose-700 border-rose-200"}`} variant="outline">
                                          {t.status}
                                        </Badge>
                                      </TableCell>
                                    </TableRow>
                                  ))}
                                </TableBody>
                              </Table>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          <p className="text-xs text-slate-500 leading-relaxed">
                            No CBS customer profile is currently linked to this complaint. Link manually below:
                          </p>
                          <div className="flex gap-2 max-w-md">
                            <Input
                              value={cbsSearchId}
                              onChange={(e) => setCbsSearchId(e.target.value)}
                              placeholder="Enter Customer ID (e.g. 10010245)"
                              className="border-slate-200 text-xs h-9 focus-visible:ring-blue-500"
                            />
                            <Button 
                              onClick={handleLinkCustomer}
                              className="bg-blue-600 hover:bg-blue-700 font-bold text-xs h-9 cursor-pointer text-white gap-1"
                            >
                              <UserPlus className="h-3.5 w-3.5" /> Link CBS
                            </Button>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Multi-modal evidence attachments */}
                  {renderAttachments(complaint)}

                  {/* AI Summary Box */}
                  <div className="p-4 bg-blue-50/50 border border-blue-200/60 rounded-xl leading-relaxed">
                    <span className="text-[10px] font-bold uppercase tracking-widest text-blue-700 flex items-center gap-1.5 mb-1 select-none">
                      <Bot className="h-4 w-4" /> AI Summary & Triage Description
                    </span>
                    <p className="text-xs text-slate-700 font-medium leading-relaxed">
                      {cleanText(complaint.summary || "Complaint summary processing...")}
                    </p>
                  </div>

                  {/* Raw Text / Masked PII toggle */}
                  <Card className="shadow-sm border-slate-200">
                    <CardHeader className="py-3 bg-slate-50/20 border-b border-slate-100">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest select-none">Complaint Body Text</span>
                        <Button
                          variant="outline"
                          onClick={() => setShowRawText(!showRawText)}
                          className="h-7 px-3 border-slate-200 text-[10px] font-bold text-indigo-700 hover:bg-indigo-50/50 gap-1.5 cursor-pointer"
                        >
                          <Key className="h-3.5 w-3.5" /> {showRawText ? "Hide PII Data" : "Authorised View"}
                        </Button>
                      </div>
                    </CardHeader>
                    <CardContent className="pt-4 space-y-4">
                      <div>
                        <Label className="text-[9px] text-slate-400 font-bold uppercase select-none">Active Text Content</Label>
                        <div className="mt-1.5 p-3 rounded-lg border border-slate-100 bg-slate-50/50 text-xs text-slate-700 font-medium leading-relaxed break-words whitespace-pre-wrap">
                          {showRawText ? cleanText(complaint.raw_text) : cleanText(complaint.masked_text)}
                        </div>
                      </div>
                      {!showRawText && (
                        <div>
                          <Label className="text-[9px] text-slate-400 font-bold uppercase select-none">Masked Text (PII scrubbed)</Label>
                          <div className="mt-1.5 p-3 rounded-lg border border-slate-100 bg-slate-50/20 text-xs text-slate-400 font-medium leading-relaxed break-words whitespace-pre-wrap italic select-none">
                            {cleanText(complaint.masked_text)}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Multi-Agent LangGraph Pipeline Trace Stepper */}
                  <Card className="shadow-sm border-slate-200 bg-slate-50/20">
                    <CardHeader className="py-3 bg-slate-50/50 border-b border-slate-100 flex flex-row items-center justify-between">
                      <CardTitle className="text-xs font-black uppercase text-slate-700 flex items-center gap-2 select-none">
                        <Sparkles className="h-4 w-4 text-purple-600" /> Multi-Agent Redressal Execution Trace
                      </CardTitle>
                      {loadingLedger ? (
                        <span className="text-[10px] text-slate-400 animate-pulse">Checking Ledger...</span>
                      ) : ledgerValid === true ? (
                        <Badge className="bg-emerald-100 text-emerald-800 border-emerald-200 font-extrabold text-[9px] uppercase hover:bg-emerald-100 flex items-center gap-1">
                          <Shield className="h-3 w-3 text-emerald-600" /> Ledger Verified 🔒
                        </Badge>
                      ) : ledgerValid === false ? (
                        <Badge className="bg-rose-100 text-rose-800 border-rose-200 font-extrabold text-[9px] uppercase hover:bg-rose-100 flex items-center gap-1">
                          <ShieldAlert className="h-3 w-3 text-rose-600" /> Ledger Tampered
                        </Badge>
                      ) : null}
                    </CardHeader>
                    <CardContent className="pt-4 space-y-3">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
                        {[
                          { name: "Outage Interceptor", key: "outage_check_node", desc: complaint.linked_incident ? `Linked #${complaint.linked_incident.slice(0, 8)}` : "No Outage" },
                          { name: "Language Check", key: "language_node", desc: complaint.detected_language || "English" },
                          { name: "NLP Triage", key: "triage_node", desc: complaint.triage?.category || "Triaged" },
                          { name: "Missing Details Check", key: "info_check_node", desc: complaint.needs_info ? "Missing Info" : "Complete" },
                          { name: "CBS Verification", key: "cbs_verification_node", desc: complaint.customer_id ? "Verified" : "Unverified" },
                          { name: "SLA Compliance", key: "compliance_node", desc: complaint.rbi_status || "On Track" },
                          { name: "Supervisor Review", key: "human_approval_node", desc: complaint.needs_human ? "Paused for Review" : "Passed" },
                          { name: "RAG & Drafting", key: "drafting_node", desc: complaint.triage?.suggested_response ? "Draft Ready" : "Pending" }
                        ].map((node, i) => {
                          const isExecuted = complaint.agent_trace?.some(t => t.node === node.key);
                          const isPaused = (node.key === "human_approval_node" && complaint.needs_human) || (node.key === "info_check_node" && complaint.needs_info);
                          return (
                            <div key={i} className={`p-2.5 rounded-lg border text-xs flex flex-col justify-between ${
                              isPaused ? "bg-amber-50/80 border-amber-300 text-amber-900" :
                              isExecuted ? "bg-white border-slate-200 text-slate-800" : "bg-slate-50 border-slate-100 text-slate-400"
                            }`}>
                              <div className="flex items-center justify-between font-bold text-[11px]">
                                <span className="truncate">{node.name}</span>
                                <span className="text-[10px]">{isExecuted ? "✓" : isPaused ? "⏸" : "○"}</span>
                              </div>
                              <span className="text-[9px] font-medium text-slate-500 mt-1 truncate">{node.desc}</span>
                            </div>
                          );
                        })}
                      </div>

                      {/* Human Approval Interrupt Banner */}
                      {complaint.needs_human && (
                        <div className="mt-3 p-3 bg-amber-50 border border-amber-200 rounded-lg flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                          <div className="flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-amber-600 flex-shrink-0" />
                            <div>
                              <div className="font-extrabold text-amber-900 text-xs">Supervisor Approval Required</div>
                              <div className="text-[11px] text-amber-700 font-medium">High Severity/Amount detected. Pipeline paused prior to dispatch.</div>
                            </div>
                          </div>
                          <Button
                            onClick={handleApprovePipelineDraft}
                            disabled={approveLoading}
                            className="bg-amber-600 hover:bg-amber-700 text-white font-bold text-xs h-8 px-4 flex-shrink-0 cursor-pointer"
                          >
                            {approveLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Sparkles className="h-3.5 w-3.5 mr-1" />}
                            Approve AI Response
                          </Button>
                        </div>
                      )}

                      {/* Missing Info Form Banner */}
                      {complaint.needs_info && (
                        <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg space-y-3">
                          <div className="flex items-center gap-2">
                            <Info className="h-5 w-5 text-blue-600 flex-shrink-0" />
                            <div>
                              <div className="font-extrabold text-blue-900 text-xs">Missing Transaction Details</div>
                              <div className="text-[11px] text-blue-700 font-medium">{complaint.missing_fields_question || "Please provide reference ID and debited amount."}</div>
                            </div>
                          </div>
                          <div className="flex flex-col sm:flex-row gap-2 pt-1">
                            <Input
                              value={infoTxnRef}
                              onChange={(e) => setInfoTxnRef(e.target.value)}
                              placeholder="Txn Ref ID (e.g. UPI657483)"
                              className="h-8 text-xs bg-white border-blue-200"
                            />
                            <Input
                              value={infoAmount}
                              onChange={(e) => setInfoAmount(e.target.value)}
                              placeholder="Amount (e.g. 3000)"
                              className="h-8 text-xs bg-white border-blue-200"
                            />
                            <Button
                              onClick={handleProvideMissingDetails}
                              disabled={infoLoading || (!infoTxnRef.trim() && !infoAmount.trim())}
                              className="bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs h-8 px-4 flex-shrink-0 cursor-pointer"
                            >
                              {infoLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" /> : <Send className="h-3.5 w-3.5 mr-1" />}
                              Submit Details
                            </Button>
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* AI Triage and Response editing */}
                  <Card className="shadow-sm border-slate-200 bg-slate-50/20">
                    <CardHeader className="py-4 border-b border-slate-100 flex flex-row items-center justify-between">
                      <CardTitle className="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                        <Bot className="h-4 w-4 text-blue-600" /> AI Classification Diagnostics
                      </CardTitle>
                      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider select-none">
                        Confidence: {Math.round((complaint.triage?.confidence || 0) * 100)}%
                      </div>
                    </CardHeader>
                    <CardContent className="pt-4 space-y-4">
                      <div>
                        <Label className="text-[10px] text-slate-400 font-bold uppercase select-none">Isolated Key Issue</Label>
                        <p className="text-sm font-bold text-indigo-700 mt-0.5">{cleanText(complaint.triage?.key_issue || "-")}</p>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <Label htmlFor="suggested_response" className="text-[10px] text-slate-400 font-bold uppercase select-none">Suggested AI Response Draft</Label>
                          <Button
                            variant="ghost"
                            onClick={() => {
                              navigator.clipboard.writeText(suggestedResponse);
                              toast.success("Suggested response copied to clipboard.");
                            }}
                            className="text-xs text-blue-600 hover:text-blue-700 font-bold p-0 h-auto cursor-pointer"
                          >
                            Copy Draft
                          </Button>
                        </div>
                        <Textarea
                          id="suggested_response"
                          value={suggestedResponse}
                          onChange={(e) => setSuggestedResponse(e.target.value)}
                          className="min-h-[110px] border-slate-200 text-xs font-semibold bg-white resize-none leading-relaxed focus-visible:ring-blue-500"
                        />
                      </div>

                      {/* AI Confidence Meter */}
                      <div className="space-y-1 pt-1 select-none">
                        <div className="flex justify-between text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                          <span>Classification Confidence</span>
                          <span className="text-emerald-600">{Math.round((complaint.triage?.confidence || 0) * 100)}%</span>
                        </div>
                        <div className="relative">
                          <div className="h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500" style={{ width: `${Math.round((complaint.triage?.confidence || 0) * 100)}%` }} />
                          </div>
                        </div>
                      </div>

                      {/* Explainability Section */}
                      <div className="border-t border-slate-200/80 pt-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider select-none">Explainable AI Audit Log</span>
                          <Button
                            variant="outline"
                            onClick={triggerAuditExplanation}
                            disabled={loadingExplanation}
                            className="h-7 px-3 border-blue-200 text-[10px] font-bold text-blue-700 hover:bg-blue-50/50 gap-1.5 cursor-pointer"
                          >
                            <Key className="h-3.5 w-3.5" /> Audit Reason
                          </Button>
                        </div>
                        {loadingExplanation ? (
                          <div className="p-3 border border-slate-100 rounded-lg bg-white flex items-center justify-center text-xs text-slate-500 select-none">
                            <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" /> Auditing classification...
                          </div>
                        ) : aiExplanation ? (
                          <div className="p-3 border border-slate-100 rounded-lg bg-white text-xs font-medium text-slate-700 leading-relaxed break-words whitespace-pre-wrap">
                            <strong>Audit Verdict:</strong> {cleanText(aiExplanation)}
                          </div>
                        ) : (
                          <p className="text-[11px] text-slate-400 font-semibold italic pl-1 select-none">
                            Click &apos;Audit Reason&apos; to query the Gemini explainability logs for this classification.
                          </p>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* 2. HISTORY / CHAT TIMELINE TAB */}
                <TabsContent value="history" className="mt-0 flex flex-col h-full space-y-4">
                  <div className="space-y-4 max-h-[420px] overflow-y-auto pr-1">
                    {complaint.communication_history?.map((msg) => {
                      const isCustomer = msg.author === "customer";
                      const isSystem = msg.author === "system";
                      
                      let avatarText = "SY";
                      let avatarStyle = "bg-slate-200 text-slate-600";
                      
                      if (isCustomer) {
                        avatarText = "CU";
                        avatarStyle = "bg-sky-100 text-sky-700";
                      } else if (msg.author === "agent") {
                        avatarText = "AG";
                        avatarStyle = "bg-emerald-100 text-emerald-700";
                      }

                      return (
                        <div key={msg.id} className="flex gap-3">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs flex-shrink-0 select-none ${avatarStyle}`}>
                            {avatarText}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 select-none">
                              <span className="text-xs font-bold text-slate-800">{msg.author_name}</span>
                              {msg.is_ai_draft && (
                                <Badge className="bg-yellow-50 text-yellow-800 border-yellow-200 hover:bg-yellow-50 text-[9px] font-extrabold uppercase py-0 px-2">AI Draft</Badge>
                              )}
                              <span className="text-[10px] text-slate-400 font-medium ml-auto">{formatDt(msg.timestamp)}</span>
                            </div>
                            <div className={`mt-1.5 p-3 rounded-lg text-xs leading-relaxed font-semibold break-words whitespace-pre-wrap max-w-full ${
                              msg.is_ai_draft ? "bg-amber-50/50 border border-dashed border-amber-200 text-slate-700" :
                              isCustomer ? "bg-slate-50 text-slate-700 border border-slate-100" :
                              isSystem ? "bg-emerald-50/40 text-emerald-700 border border-emerald-100 italic" :
                              "bg-blue-50 text-blue-800 border border-blue-100"
                            }`}>
                              {cleanText(msg.content)}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Reply Editor */}
                  {complaint.status !== "resolved" ? (
                    <div className="space-y-3 pt-3 border-t border-slate-200">
                      <Label htmlFor="replyText" className="text-[10px] text-slate-400 font-bold uppercase select-none">Send Customer Response</Label>
                      <Textarea
                        id="replyText"
                        value={replyText}
                        onChange={(e) => setReplyText(e.target.value)}
                        placeholder="Type your response to the customer here..."
                        className="min-h-[90px] border-slate-200 text-xs font-semibold resize-none focus-visible:ring-blue-500"
                      />
                      <div className="flex gap-2">
                        <Button
                          onClick={handleSendReply}
                          disabled={sendingReply || !replyText.trim()}
                          className="bg-blue-600 hover:bg-blue-700 font-bold text-xs h-9 cursor-pointer text-white gap-2"
                        >
                          {sendingReply ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                          Send Response
                        </Button>
                        <Button
                          variant="outline"
                          onClick={() => {
                            if (complaint.triage?.suggested_response) {
                              setReplyText(complaint.triage.suggested_response);
                              toast.info("Copied suggested AI response into composer.");
                            }
                          }}
                          className="border-amber-300 text-amber-700 hover:bg-amber-50/50 font-bold text-xs h-9 gap-1 cursor-pointer"
                        >
                          <Bot className="h-3.5 w-3.5" /> Use AI Draft
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4 bg-emerald-50 text-emerald-800 font-extrabold text-xs text-center rounded-lg select-none">
                      Complaint resolved - conversation closed.
                    </div>
                  )}
                </TabsContent>

                {/* 3. SLA TAB */}
                <TabsContent value="sla" className="mt-0">
                  <Card className="shadow-sm border-slate-200">
                    <CardHeader className="bg-slate-50/20 border-b border-slate-100 py-4">
                      <CardTitle className="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                        <Clock className="h-4 w-4 text-blue-600" /> Response Compliance Metrics
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      <SlaProgressBar complaint={complaint} />
                      {complaint.sla ? (
                        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-xs pt-6">
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">Deadline</span>
                            <span className="font-extrabold text-slate-800 mt-1 block">{formatDt(complaint.sla.deadline)}</span>
                          </div>
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">Hours Allowed</span>
                            <span className="font-extrabold text-slate-800 mt-1 block">{complaint.sla.hours_allowed} hrs</span>
                          </div>
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">Hours Elapsed</span>
                            <span className="font-extrabold text-slate-800 mt-1 block">{complaint.sla.hours_elapsed.toFixed(1)} hrs</span>
                          </div>
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">Hours Remaining</span>
                            <span className={`font-extrabold mt-1 block ${complaint.sla.hours_remaining < 0 ? "text-rose-600" : "text-slate-800"}`}>
                              {complaint.sla.hours_remaining.toFixed(1)} hrs
                            </span>
                          </div>
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">SLA Used</span>
                            <span className="font-extrabold text-slate-800 mt-1 block">{complaint.sla.percent_used}%</span>
                          </div>
                          <div className="p-3 bg-slate-50/50 border border-slate-100 rounded-lg">
                            <span className="text-[10px] text-slate-400 font-bold uppercase block select-none">Compliance Risk</span>
                            <span className={`font-extrabold uppercase mt-1 block ${complaint.sla.breached ? "text-rose-600" : "text-emerald-600"}`}>
                              {complaint.sla.breached ? "YES" : "NO"}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 mt-2 select-none italic pl-1 font-semibold">No active SLA timer linked to this complaint.</p>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

                {/* 4. ESCALATION TAB */}
                <TabsContent value="escalation" className="mt-0 space-y-6">
                  {/* Stepper timeline path */}
                  <Card className="shadow-sm border-slate-200">
                    <CardContent className="p-5 space-y-4">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block select-none">Stepping Levels</span>
                      <div className="flex flex-col gap-0 select-none">
                        {["L1 Agent", "L2 Supervisor", "L3 Manager", "L4 Regulatory"].map((lvl, idx) => {
                          const levels = ["L1 Agent", "L2 Supervisor", "L3 Manager", "L4 Regulatory"];
                          const currentIdx = levels.indexOf(complaint.escalation_level || "L1 Agent");
                          
                          const isDone = idx < currentIdx;
                          const isCurrent = idx === currentIdx;
                          
                          return (
                            <div key={idx} className="flex flex-col gap-0">
                              {idx > 0 && <div className="h-6 w-0.5 bg-slate-200 ml-3.5" />}
                              <div className="flex items-center gap-3">
                                <div className={`w-7.5 h-7.5 rounded-full flex items-center justify-center font-bold text-xs text-white ${
                                  isDone ? "bg-emerald-500" : isCurrent ? "bg-indigo-600" : "bg-slate-300"
                                }`}>
                                  {idx + 1}
                                </div>
                                <div>
                                  <span className={`text-xs font-bold ${
                                    isDone ? "text-emerald-700" : isCurrent ? "text-indigo-700 font-extrabold" : "text-slate-400"
                                  }`}>{lvl}</span>
                                  <span className="text-[10px] text-slate-400 block font-semibold mt-0.5">
                                    {isDone ? "Completed" : isCurrent ? "Active Tier" : "Inactive"}
                                  </span>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </CardContent>
                  </Card>

                  {/* Escalation history logs */}
                  {complaint.escalation_history && complaint.escalation_history.length > 0 && (
                    <Card className="shadow-sm border-slate-200">
                      <CardHeader className="py-3 bg-slate-50/20 border-b border-slate-100">
                        <CardTitle className="text-xs font-bold text-slate-700 uppercase tracking-wider select-none">Escalation Audit history</CardTitle>
                      </CardHeader>
                      <CardContent className="pt-4 space-y-3">
                        {complaint.escalation_history.map((e) => (
                          <div key={e.id} className="p-3 border border-slate-100 rounded-lg bg-slate-50/50 text-xs">
                            <div className="font-extrabold text-slate-800">{e.from_level} &rarr; {e.to_level}</div>
                            <p className="text-slate-600 font-medium mt-1 leading-relaxed">{cleanText(e.reason)}</p>
                            <div className="text-[10px] text-slate-400 font-bold mt-2">By {e.escalated_by} &middot; {formatDt(e.escalated_at)}</div>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )}

                  {/* Action buttons */}
                  {complaint.status !== "resolved" && (
                    <div className="flex gap-2 select-none">
                      <Button
                        onClick={() => onOpenEscalate(complaint.id)}
                        className="bg-indigo-600 hover:bg-indigo-700 font-bold text-xs h-9 cursor-pointer text-white gap-1.5"
                      >
                        <ArrowUp className="h-4 w-4" /> Escalate to Next Level
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          toast.success("RBI escalation triggered.");
                        }}
                        className="border-rose-200 text-rose-700 hover:bg-rose-50/50 font-bold text-xs h-9 gap-1.5 cursor-pointer"
                      >
                        <ShieldAlert className="h-4 w-4" /> Escalate to RBI
                      </Button>
                    </div>
                  )}
                </TabsContent>

                {/* 5. AUDIT TAB */}
                <TabsContent value="audit" className="mt-0">
                  <Card className="shadow-sm border-slate-200">
                    <CardHeader className="bg-slate-50/20 border-b border-slate-100 py-4">
                      <CardTitle className="text-sm font-bold text-slate-700 flex items-center gap-2 select-none">
                        <Shield className="h-4 w-4 text-blue-600" /> Compliance Audit Trail
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="pt-4">
                      {loadingAudit ? (
                        <div className="py-4 flex items-center justify-center text-xs text-slate-500 select-none">
                          <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" /> Loading audit logs...
                        </div>
                      ) : auditLogs.length > 0 ? (
                        <div className="space-y-3">
                          {auditLogs.map((log) => (
                            <div key={log.id} className="p-3 border border-slate-100 rounded-lg bg-slate-50/30 text-xs">
                              <div className="flex justify-between items-center">
                                <span className="font-extrabold text-slate-800 text-xs uppercase tracking-wider">{cleanText(log.action)}</span>
                                <span className="text-[10px] text-slate-400 font-bold">{formatDt(log.timestamp)}</span>
                              </div>
                              <p className="text-slate-500 font-medium mt-1">
                                Actor: <strong className="text-slate-700">{cleanText(log.actor)}</strong> &nbsp;|&nbsp; Role: <strong className="text-slate-700">{cleanText(log.role.toUpperCase())}</strong>
                              </p>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <p className="text-xs text-slate-500 italic pl-1 font-semibold select-none">No audit logs recorded for this complaint.</p>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>

              </div>
            </Tabs>

            {/* Action Bar Footer */}
            <div className="px-6 py-4 border-t border-slate-100 bg-slate-50/50 flex-shrink-0 flex items-center justify-between gap-3 select-none">
              {complaint.status === "pending" || complaint.status === "in_review" ? (
                <>
                  <Button
                    onClick={() => handleAction("approve")}
                    className="flex-1 bg-emerald-600 hover:bg-emerald-700 font-extrabold text-xs h-10 gap-1.5 cursor-pointer text-white"
                  >
                    Approve & Send
                  </Button>
                  <Button
                    onClick={() => onOpenEscalate(complaint.id)}
                    className="flex-1 bg-indigo-600 hover:bg-indigo-700 font-extrabold text-xs h-10 gap-1.5 cursor-pointer text-white"
                  >
                    Escalate
                  </Button>
                  <Button
                    onClick={() => handleAction("reject")}
                    variant="outline"
                    className="flex-1 border-slate-200 font-extrabold text-xs h-10 gap-1.5 cursor-pointer hover:bg-slate-100"
                  >
                    Mark In Review
                  </Button>
                </>
              ) : (
                <div className="w-full text-center text-xs font-extrabold text-slate-500 uppercase tracking-wider py-1 select-none">
                  Complaint Status is currently: <span className="text-blue-600">{complaint.status}</span>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
