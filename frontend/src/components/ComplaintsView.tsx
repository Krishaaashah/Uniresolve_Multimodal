"use client";

import React, { useState } from "react";
import { Complaint, GroupItem, api, TimelineProgress } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { 
  AlertCircle, ArrowDown, ArrowUp, Building, Calendar, 
  ChevronDown, ChevronUp, Clock, Folder, Globe, Info, Link as LinkIcon, 
  Mail, Network, Phone, RefreshCw, Search, Sparkles, User, PlusCircle, Loader2 
} from "lucide-react";
import { toast } from "sonner";
import SlaProgressBar from "./SlaProgressBar";

interface ComplaintsViewProps {
  complaints: Complaint[];
  groups: GroupItem[];
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  activeFilter: string;
  setActiveFilter: (filter: string) => void;
  viewMode: "single" | "grouped";
  setViewMode: (mode: "single" | "grouped") => void;
  onInspect: (complaint: Complaint) => void;
  onOpenIngest: () => void;
}

export default function ComplaintsView({
  complaints,
  groups,
  searchQuery,
  setSearchQuery,
  activeFilter,
  setActiveFilter,
  viewMode,
  setViewMode,
  onInspect,
  onOpenIngest
}: ComplaintsViewProps) {
  // Local toggles for duplicate sections
  const [openDuplicates, setOpenDuplicates] = useState<Record<string, any[]>>({});
  const [loadingDuplicates, setLoadingDuplicates] = useState<Record<string, boolean>>({});

  // Local toggles for grouping details
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const [groupTimelines, setGroupTimelines] = useState<Record<string, TimelineProgress>>({});
  const [loadingGroupTimelines, setLoadingGroupTimelines] = useState<Record<string, boolean>>({});

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
    return icons[c] || <Mail className="h-3.5 w-3.5" />;
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

  const formatDt = (iso: string) => {
    return new Date(iso).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleToggleDuplicates = async (ticketId: string, id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (openDuplicates[id]) {
      setOpenDuplicates(prev => {
        const copy = { ...prev };
        delete copy[id];
        return copy;
      });
      return;
    }

    setLoadingDuplicates(prev => ({ ...prev, [id]: true }));
    try {
      const data = await api.getDuplicates(ticketId);
      setOpenDuplicates(prev => ({ ...prev, [id]: data.tickets as unknown as Complaint[] }));
    } catch (err) {
      toast.error("Failed to load duplicate tickets.");
    } finally {
      setLoadingDuplicates(prev => ({ ...prev, [id]: false }));
    }
  };

  const handleToggleGroupDetails = async (groupId: string, parentTicketId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const isExpanding = !openGroups[groupId];
    
    setOpenGroups(prev => ({ ...prev, [groupId]: isExpanding }));

    if (isExpanding && parentTicketId && !groupTimelines[groupId]) {
      setLoadingGroupTimelines(prev => ({ ...prev, [groupId]: true }));
      try {
        const timelineData = await api.getTimeline(parentTicketId);
        setGroupTimelines(prev => ({ ...prev, [groupId]: timelineData }));
      } catch (err) {
        toast.error("Failed to load group timeline progress.");
      } finally {
        setLoadingGroupTimelines(prev => ({ ...prev, [groupId]: false }));
      }
    }
  };

  // Filter & Search Individual Complaints
  const filteredComplaints = complaints
    .filter(c => {
      // search query
      if (searchQuery) {
        const s = searchQuery.toLowerCase();
        const matchesText = (c.masked_text || "").toLowerCase().includes(s) ||
                            (c.triage?.key_issue || "").toLowerCase().includes(s) ||
                            (c.triage?.category || "").toLowerCase().includes(s) ||
                            (c.channel || "").toLowerCase().includes(s) ||
                            (c.ticket_id || "").toLowerCase().includes(s) ||
                            (c.customer_id || "").toLowerCase().includes(s);
        if (!matchesText) return false;
      }
      // status filter
      if (activeFilter !== "all" && c.status !== activeFilter) return false;
      return true;
    })
    .sort((a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime());

  // Filter Grouped Items based on searchQuery
  const filteredGroups = viewMode === "grouped" 
    ? groups.filter(g => {
        if (!searchQuery) return true;
        const s = searchQuery.toLowerCase();
        return (g.customer_id || "").toLowerCase().includes(s) ||
               (g.grouping_reason || "").toLowerCase().includes(s) ||
               g.channels.some(c => c.toLowerCase().includes(s)) ||
               (g.transaction_id || "").toLowerCase().includes(s);
      })
    : [];

  const filters = ["all", "pending", "in_review", "escalated", "resolved"];

  return (
    <div className="space-y-6 font-sans">
      {/* Title */}
      <div className="flex items-center justify-between select-none">
        <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
          {viewMode === "grouped" ? <LinkIcon className="h-6 w-6 text-blue-600" /> : <Search className="h-6 w-6 text-blue-600" />}
          All Complaints {viewMode === "grouped" ? `(${filteredGroups.length} Groups)` : `(${filteredComplaints.length} Tickets)`}
        </h2>
        <Button 
          onClick={onOpenIngest} 
          className="bg-blue-600 hover:bg-blue-700 font-extrabold text-xs h-9 cursor-pointer text-white gap-1"
        >
          <PlusCircle className="h-4 w-4" /> New Complaint
        </Button>
      </div>

      {/* Search Input and View Toggle */}
      <div className="flex flex-col sm:flex-row gap-4 items-center justify-between">
        <div className="relative w-full sm:flex-1">
          <Search className="absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by ticket ID, Customer ID, keywords, categories or channels..."
            className="pl-10 pr-4 h-10 border-slate-200 text-xs focus-visible:ring-blue-500 w-full"
          />
        </div>
        {/* Toggle between Individual and Grouped view */}
        <div className="flex bg-slate-100 p-1 rounded-lg select-none">
          <Button
            onClick={() => setViewMode("single")}
            className={`text-xs font-bold py-1.5 px-4 h-8 cursor-pointer shadow-none ${
              viewMode === "single"
                ? "bg-white text-blue-600 hover:bg-white"
                : "bg-transparent text-slate-500 hover:bg-transparent"
            }`}
          >
            Individual
          </Button>
          <Button
            onClick={() => setViewMode("grouped")}
            className={`text-xs font-bold py-1.5 px-4 h-8 cursor-pointer shadow-none ${
              viewMode === "grouped"
                ? "bg-white text-blue-600 hover:bg-white"
                : "bg-transparent text-slate-500 hover:bg-transparent"
            }`}
          >
            Grouped
          </Button>
        </div>
      </div>

      {/* Filter Chips (Only for Individual Mode) */}
      {viewMode === "single" && (
        <div className="flex flex-wrap gap-2 select-none">
          {filters.map((f) => (
            <Button
              key={f}
              onClick={() => setActiveFilter(f)}
              variant="outline"
              className={`text-xs font-semibold py-1.5 px-4 rounded-full h-8 cursor-pointer ${
                activeFilter === f
                  ? "bg-blue-600 border-blue-600 text-white hover:bg-blue-700 hover:text-white"
                  : "border-slate-200 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {f.replace("_", " ").replace(/\b\w/g, x => x.toUpperCase())}
            </Button>
          ))}
        </div>
      )}

      {/* Core Complaints List Card Grid */}
      <div className="flex flex-col gap-4">
        {viewMode === "grouped" ? (
          // Grouped View rendering
          filteredGroups.length > 0 ? (
            filteredGroups.map((g) => {
              const repTicket = g.tickets[0];
              const repId = repTicket?.ticket_id || repTicket?.id;
              const repComplaint = complaints.find(c => c.id === repTicket?.id || c.ticket_id === repTicket?.ticket_id);
              const repText = repComplaint ? (repComplaint.summary || repComplaint.masked_text || "") : "Grouped complaint details";
              const category = repComplaint?.triage?.category || "General";
              
              const isGroupExpanded = !!openGroups[g.group_id];
              const timeline = groupTimelines[g.group_id];
              const isTimelineLoading = !!loadingGroupTimelines[g.group_id];

              return (
                <Card 
                  key={g.group_id} 
                  onClick={(e) => handleToggleGroupDetails(g.group_id, repId, e)}
                  className="hover:shadow-md border-l-4 border-l-blue-600 hover:border-blue-500 cursor-pointer overflow-hidden transition-all duration-200"
                >
                  <CardContent className="p-5 space-y-3">
                    <div className="flex items-start justify-between flex-wrap gap-2 text-xs">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge className="bg-blue-50 border border-blue-200 text-blue-700 font-extrabold uppercase text-[10px] hover:bg-blue-50">
                          Raised {g.count}×
                        </Badge>
                        {g.customer_id && (
                          <Badge variant="secondary" className="bg-slate-100 text-slate-700 text-[10px] font-bold">
                            Customer: {g.customer_id}
                          </Badge>
                        )}
                        {g.transaction_id && g.transaction_id !== "None" && g.transaction_id !== "null" && g.transaction_id !== "" && (
                          <Badge variant="secondary" className="bg-rose-50 text-rose-700 text-[10px] font-bold">
                            Txn: {g.transaction_id}
                          </Badge>
                        )}
                      </div>
                      <span className="text-[10px] text-slate-400 font-semibold select-none">
                        Last Active {timeAgo(g.last_raised)}
                      </span>
                    </div>

                    <p className="text-xs font-semibold leading-relaxed text-slate-700 break-words mt-1 line-clamp-2">
                      {cleanText(repText)}
                    </p>

                    {/* Stepper Timeline & Diagnostics details (Collapsible) */}
                    {isGroupExpanded && (
                      <div 
                        className="mt-3 p-4 bg-slate-50 border border-slate-200 rounded-lg space-y-4 cursor-default"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="space-y-1">
                          <span className="text-[11px] font-bold text-blue-700 flex items-center gap-1">
                            <Info className="h-3.5 w-3.5" /> Grouping Diagnosis (Explainability)
                          </span>
                          <p className="text-xs text-slate-700"><strong>Reason:</strong> {g.grouping_reason}</p>
                        </div>

                        {/* List of individual tickets inside the group */}
                        <div className="space-y-2">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Member Tickets</span>
                          <div className="flex flex-col gap-2 max-h-[220px] overflow-y-auto pr-1">
                            {g.tickets.map((t, idx) => (
                              <div 
                                key={t.id} 
                                className="flex justify-between items-center bg-white border border-slate-150 p-2.5 rounded-md hover:bg-slate-50 cursor-pointer"
                                onClick={() => {
                                  const comp = complaints.find(x => x.id === t.id);
                                  if (comp) onInspect(comp);
                                }}
                              >
                                <span className="text-xs font-bold text-blue-600">Ticket #{idx + 1} ({t.channel})</span>
                                <span className="text-[10px] text-slate-400 font-semibold flex items-center gap-2">
                                  {formatDt(t.timestamp)}
                                  <span className="text-blue-500 font-bold hover:underline ml-2">Open Ticket &rarr;</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>

                        {/* Timeline for Group Earliest ticket */}
                        <div className="pt-2 border-t border-slate-250 select-none">
                          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-3">Group Lifecycle Timeline</span>
                          {isTimelineLoading ? (
                            <div className="py-2 flex items-center justify-center text-xs text-slate-500">
                              <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" /> Loading timeline stepper...
                            </div>
                          ) : timeline ? (
                            <div className="bg-white border border-slate-200 rounded-lg p-4 relative flex justify-between items-start">
                              {/* Connector horizontal line */}
                              <div className="absolute top-7.5 left-[12%] right-[12%] h-0.5 bg-slate-200 z-0">
                                <div 
                                  className="h-full bg-blue-600 transition-all duration-300"
                                  style={{
                                    width: timeline.current_stage === "Seen" ? "33%"
                                         : timeline.current_stage === "In Progress / Escalated" ? "66%"
                                         : timeline.current_stage === "Resolved" ? "100%" : "0%"
                                  }}
                                />
                              </div>
                              {timeline.steps.map((step, idx) => (
                                <div key={idx} className="relative z-10 flex flex-col items-center text-center w-[20%]">
                                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-white font-extrabold text-[10px] ${
                                    step.completed ? "bg-blue-600" : "bg-slate-300"
                                  }`}>
                                    {step.completed ? "✓" : idx + 1}
                                  </div>
                                  <span className="text-[10px] font-bold text-slate-700 mt-2">{step.stage.split(" ")[0]}</span>
                                  {step.timestamp && (
                                    <span className="text-[8px] text-slate-400 mt-0.5 font-bold">
                                      {formatDt(step.timestamp).split(",")[0]}
                                    </span>
                                  )}
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )}

                    <div className="flex items-center justify-between text-[10px] font-bold text-slate-400 pt-1.5 border-t border-slate-100 select-none">
                      <span className="flex items-center gap-1"><Folder className="h-3 w-3" /> {category}</span>
                      
                      <div className="flex items-center gap-3">
                        {g.channels.map((cName) => (
                          <span key={cName} className="flex items-center gap-1">
                            {channelIcon(cName.toLowerCase())} {cName}
                          </span>
                        ))}
                        <span className="text-blue-600 font-extrabold flex items-center gap-1">
                          {isGroupExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                          {isGroupExpanded ? "Hide Details" : "View Details"}
                        </span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })
          ) : (
            <Card className="p-8 text-center border-dashed border-slate-200 bg-slate-50/50">
              <LinkIcon className="h-8 w-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-500">No complaint groups found matching search query</p>
            </Card>
          )
        ) : (
          // Individual View rendering
          filteredComplaints.length > 0 ? (
            filteredComplaints.map((c) => {
              const isBreached = c.sla?.status === "breached" && c.status !== "resolved";
              const dupId = `dup_list_${c.id}`;
              const isDupOpen = !!openDuplicates[dupId];
              const isDupLoading = !!loadingDuplicates[dupId];
              const dups = openDuplicates[dupId] || [];

              return (
                <Card 
                  key={c.id} 
                  onClick={() => onInspect(c)}
                  className={`hover:shadow-md hover:border-blue-500 border-slate-200/80 cursor-pointer overflow-hidden transition-all duration-200 ${
                    c.cluster?.systemic_alert ? "border-l-4 border-l-rose-500" : isBreached ? "border-l-4 border-l-rose-500" : ""
                  }`}
                >
                  <CardContent className="p-5 space-y-2">
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
                          c.status === "escalated" ? "bg-rose-50 text-rose-700 border-rose-200" :
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

                    <div className="flex items-center justify-between flex-wrap gap-3 text-[10px] font-bold text-slate-400 pt-1.5 border-t border-slate-100">
                      <span className="flex items-center gap-1 select-none"><Folder className="h-3 w-3" /> {c.triage?.category || "General"}</span>
                      
                      <div className="flex items-center gap-2 select-none" onClick={(e) => e.stopPropagation()}>
                        {/* Toggle duplicate counts (only if it's the parent node of duplicates) */}
                        {!c.parent_ticket_id && c.duplicate_count && c.duplicate_count > 0 ? (
                          <Button
                            variant="ghost"
                            onClick={(e) => handleToggleDuplicates(c.ticket_id || "", dupId, e)}
                            className="bg-blue-50 hover:bg-blue-100 hover:text-blue-800 text-blue-700 h-6 py-0 px-2 rounded font-extrabold text-[9px] gap-1 cursor-pointer flex items-center shadow-none"
                          >
                            <LinkIcon className="h-2.5 w-2.5" /> Raised {c.duplicate_count + 1}x ({c.duplicate_channels?.join(", ")})
                          </Button>
                        ) : null}

                        {c.cluster?.systemic_alert && (
                          <Badge className="bg-rose-600 text-white font-extrabold animate-pulse text-[9px]">SYSTEMIC ALERT</Badge>
                        )}

                        {c.recurring && (
                          <Badge className="bg-amber-100 text-amber-700 border-amber-300 font-extrabold text-[9px] flex items-center gap-1 select-none" variant="outline">
                            <RefreshCw className="h-2.5 w-2.5" /> Recurring Issue
                            {c.recurring_of && (
                              <span className="font-normal ml-1 text-amber-600">· prev: {c.recurring_of}</span>
                            )}
                          </Badge>
                        )}
                        
                        {c.cluster?.is_duplicate && c.cluster?.duplicate_reason === "exact_id" ? (
                          <Badge className="bg-rose-600 text-white font-extrabold text-[9px] flex items-center gap-1 select-none"><AlertCircle className="h-2.5 w-2.5" /> Duplicate - Same customer/txn</Badge>
                        ) : c.cluster?.is_duplicate ? (
                          <Badge className="bg-violet-100 text-violet-700 border-violet-200 hover:bg-violet-100 text-[9px] font-semibold flex items-center gap-1 select-none" variant="outline"><LinkIcon className="h-2.5 w-2.5" /> Related - Similar issue</Badge>
                        ) : (c.cluster?.cluster_size && c.cluster.cluster_size > 1) ? (
                          <Badge className="bg-violet-100 text-violet-700 border-violet-200 hover:bg-violet-100 text-[9px] font-semibold flex items-center gap-1 select-none" variant="outline"><LinkIcon className="h-2.5 w-2.5" /> {c.cluster.cluster_size} linked</Badge>
                        ) : null}

                        {isBreached && (
                          <Badge className="bg-rose-500 text-white font-extrabold text-[9px]">SLA BREACH</Badge>
                        )}
                      </div>
                    </div>

                    {/* Duplicate list dropdown */}
                    {isDupOpen && (
                      <div 
                        className="mt-3 p-3 bg-slate-50 border border-slate-200 rounded-lg cursor-default"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-2 select-none">Linked Duplicate Tickets</span>
                        {isDupLoading ? (
                          <div className="py-2 flex items-center justify-center text-xs text-slate-500 select-none">
                            <Loader2 className="h-4 w-4 animate-spin text-blue-600 mr-2" /> Fetching duplicates...
                          </div>
                        ) : dups.length > 0 ? (
                          <div className="flex flex-col gap-1.5">
                            {dups.map((t) => (
                              <div 
                                key={t.id} 
                                onClick={() => { const comp = complaints.find(x => x.id === t.id); if (comp) onInspect(comp); }}
                                className="flex justify-between items-center bg-white border border-slate-100 p-2 rounded-md hover:bg-slate-50 cursor-pointer"
                              >
                                <span className="text-xs font-bold text-blue-600">{t.ticket_id}</span>
                                <span className="text-[10px] text-slate-400 font-semibold flex items-center gap-2 select-none">
                                  <span>{t.channel}</span>
                                  <span>&bull;</span>
                                  <span>{formatDt(t.timestamp)}</span>
                                </span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="text-[11px] text-slate-400 pl-1 select-none italic font-semibold">No duplicate tickets found.</p>
                        )}
                      </div>
                    )}

                    {c.status !== "resolved" && <SlaProgressBar complaint={c} compact={true} />}
                  </CardContent>
                </Card>
              );
            })
          ) : (
            <Card className="p-8 text-center border-dashed border-slate-200 bg-slate-50/50">
              <Search className="h-8 w-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm font-medium text-slate-500">No complaints found matching filters</p>
            </Card>
          )
        )}
      </div>
    </div>
  );
}
