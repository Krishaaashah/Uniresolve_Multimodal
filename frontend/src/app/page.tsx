"use client";

import React, { useState, useEffect, useRef } from "react";
import { api, Complaint, Stats, GroupItem } from "@/lib/api";
import { toast, Toaster } from "sonner";
import { 
  Scale, AlertTriangle, ShieldCheck, Play, Pause, LogOut, 
  LayoutDashboard, Layers, Timer, Activity, Network, FileText, PlusCircle, RotateCcw, HelpCircle, Loader2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import RoleLogin from "@/components/RoleLogin";
import DashboardView from "@/components/DashboardView";
import ComplaintsView from "@/components/ComplaintsView";
import SlaView from "@/components/SlaView";
import AlertsView from "@/components/AlertsView";
import AnalyticsView from "@/components/AnalyticsView";
import ClustersView from "@/components/ClustersView";
import RegulatoryView from "@/components/RegulatoryView";

import DetailModal from "@/components/DetailModal";
import IngestModal from "@/components/IngestModal";
import EscalateModal from "@/components/EscalateModal";

const DEMO_POOL = [
  { channel: "app", text: "My UPI payment of Rs 3000 failed but amount was debited from my account." },
  { channel: "email", text: "Home loan EMI deducted twice this month from my account. Need immediate refund." },
  { channel: "social", text: "Credit card blocked without any notice! This is unacceptable. Urgent help needed." },
  { channel: "ivr", text: "OTP not received on registered mobile number for last 3 attempts. Cannot login." },
  { channel: "branch", text: "Branch staff refused to update my nominee details despite proper documentation." },
  { channel: "web", text: "Account statement download failing from web portal for the past 3 days." },
  { channel: "app", text: "Investment portfolio value not refreshing in the mobile app since yesterday." },
  { channel: "email", text: "Insurance claim pending for 25 days with no update or response from team." },
  { channel: "social", text: "ATM swallowed my card and did not dispense cash. Very frustrated!" },
  { channel: "ivr", text: "IVR keeps disconnecting before connecting to human agent. Called 4 times today." },
  { channel: "web", text: "Fraud alert: suspicious transaction of Rs 8500 on my debit card I did not make." },
  { channel: "app", text: "Mobile banking fingerprint login stopped working after app update yesterday." },
  { channel: "email", text: "Mutual fund SIP not executed this month despite sufficient balance in account." },
  { channel: "branch", text: "Loan foreclosure letter not available at branch after requesting 2 weeks ago." },
  { channel: "social", text: "Net banking password reset link expired immediately. Cannot access account." },
  { channel: "web", text: "Credit card reward points vanished after last statement generation cycle." },
  { channel: "app", text: "UPI transfer shows pending for 6 hours. Beneficiary not received. Help urgently." },
  { channel: "email", text: "KYC documents submitted 3 weeks ago but account still showing verification pending." },
  { channel: "ivr", text: "Wrong EMI amount debited this month compared to my loan agreement schedule." },
  { channel: "branch", text: "Fixed deposit renewal not processed even after submitting physical form at branch." },
  { channel: "social", text: "Debit card declined at POS terminal three times. Balance is sufficient." },
  { channel: "app", text: "Cheque book request raised 15 days ago. Not received. No status update either." },
  { channel: "web", text: "Unable to add beneficiary in net banking. Getting error code 500 repeatedly." },
  { channel: "email", text: "Insurance premium auto-debit failed but policy showing lapsed. Please fix urgently." },
  { channel: "app", text: "International transaction blocked even though I activated travel mode in app." },
  { channel: "social", text: "FRAUD! Someone made 3 transactions of Rs 2000 each from my account tonight." },
  { channel: "branch", text: "Account closure request submitted 1 month ago. Still not processed at branch." },
  { channel: "web", text: "Loan statement not reflecting latest payment made 5 days ago on portal." },
  { channel: "ivr", text: "Recurring payment to utility company failed silently. Got disconnection notice." },
  { channel: "email", text: "Joint account holder addition rejected without explanation after 2 week wait." },
];

export default function Page() {
  const [authenticated, setAuthenticated] = useState(false);
  const [userRole, setUserRole] = useState("");
  const [username, setUsername] = useState("");

  const [currentView, setCurrentView] = useState("dashboard");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState("all");
  const [viewMode, setViewMode] = useState<"single" | "grouped">("single");

  // Core backend state variables
  const [complaints, setComplaints] = useState<Complaint[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [alerts, setAlerts] = useState<Complaint[]>([]);
  const [trends, setTrends] = useState<any>(null);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [isDedupHealthy, setIsDedupHealthy] = useState(true);
  const [isLlmReachable, setIsLlmReachable] = useState(false);
  const [isWarmingUp, setIsWarmingUp] = useState(false);

  // Modals controllers
  const [inspectComplaintId, setInspectComplaintId] = useState<string | null>(null);
  const [isIngestOpen, setIsIngestOpen] = useState(false);
  const [escalateComplaintId, setEscalateComplaintId] = useState<string | null>(null);

  // Live Demo Streaming state
  const [liveMode, setLiveMode] = useState(false);
  const liveCountRef = useRef(0);
  const liveIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Current system clock
  const [clock, setClock] = useState("");

  useEffect(() => {
    // 1. Clock interval
    const clockTimer = setInterval(() => {
      setClock(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }));
    }, 1000);

    // 2. Auth load checks
    const token = localStorage.getItem("auth_token");
    const role = localStorage.getItem("auth_role");
    const uname = localStorage.getItem("auth_username");

    if (token && role && uname) {
      setAuthenticated(true);
      setUserRole(role);
      setUsername(uname);
      loadAllData();
      checkBackendHealth();
    }

    // 3. API forced logouts listener
    const handleLogoutEvent = () => {
      logout();
    };
    window.addEventListener("auth-logout", handleLogoutEvent);

    return () => {
      clearInterval(clockTimer);
      window.removeEventListener("auth-logout", handleLogoutEvent);
      if (liveIntervalRef.current) clearInterval(liveIntervalRef.current);
    };
  }, []);

  // Sync refresh intervals (every 60 seconds)
  useEffect(() => {
    if (!authenticated) return;
    const syncTimer = setInterval(() => {
      loadAllData();
    }, 60000);
    return () => clearInterval(syncTimer);
  }, [authenticated]);

  // Reseed Hotkey Trigger Listener (Ctrl + Shift + D)
  useEffect(() => {
    const handleHotkey = async (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === "D") {
        e.preventDefault();
        if (userRole !== "admin") {
          toast.error("Seed failed - administrator permissions required.");
          return;
        }
        toast.warning("Reseeding demo database...");
        try {
          await api.reseedData();
          toast.success("Demo database reseeded. 24 fresh complaints loaded.");
          loadAllData();
        } catch (err) {
          toast.error("Failed to reseed database.");
        }
      }
    };
    window.addEventListener("keydown", handleHotkey);
    return () => window.removeEventListener("keydown", handleHotkey);
  }, [userRole]);

  const loadAllData = async () => {
    try {
      const allComplaints = await api.getComplaints();
      setComplaints(allComplaints);
    } catch (e) {}

    try {
      const statsData = await api.getStats();
      setStats(statsData);
    } catch (e) {}

    try {
      const alertsData = await api.getAlerts();
      setAlerts(alertsData.alerts || []);
    } catch (e) {}

    try {
      const trendsData = await api.getTrends();
      setTrends(trendsData);
    } catch (e) {}

    try {
      const groupsData = await api.getGroups();
      setGroups(groupsData);
    } catch (e) {}
  };

  const checkBackendHealth = async () => {
    try {
      const h = await api.getHealth();
      setIsDedupHealthy(h.dedup_healthy);
      setIsLlmReachable(h.ready);
      
      if (!h.ready) {
        setIsWarmingUp(true);
        // poll health more frequently during warm-up
        setTimeout(checkBackendHealth, 5000);
      } else {
        setIsWarmingUp(false);
      }
    } catch (e) {
      setTimeout(checkBackendHealth, 10000);
    }
  };

  const handleLoginSuccess = (uname: string, role: string, token: string) => {
    setAuthenticated(true);
    setUserRole(role);
    setUsername(uname);
    loadAllData();
    checkBackendHealth();
  };

  const logout = () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_role");
    localStorage.removeItem("auth_username");
    setAuthenticated(false);
    setUserRole("");
    setUsername("");
    if (liveMode) toggleLiveMode();
    toast.warning("Logged out successfully.");
  };

  const toggleLiveMode = () => {
    if (!liveMode) {
      setLiveMode(true);
      liveCountRef.current = 0;
      toast.success("Live demo mode started - complaints streaming every 12s");

      liveIntervalRef.current = setInterval(async () => {
        const item = DEMO_POOL[Math.floor(Math.random() * DEMO_POOL.length)];
        try {
          await api.ingest({ channel: item.channel, raw_text: item.text });
          liveCountRef.current += 1;
          toast.success(`Live Stream: Ingested new ${item.channel.toUpperCase()} complaint (#${liveCountRef.current})`);
          loadAllData();
        } catch (e) {
          toast.error("Live streaming degraded - backend unreachable.");
        }
      }, 12000);
    } else {
      setLiveMode(false);
      if (liveIntervalRef.current) {
        clearInterval(liveIntervalRef.current);
        liveIntervalRef.current = null;
      }
      toast.info("Live streaming disabled.");
    }
  };

  const handleSelectCategoryFromCluster = (category: string) => {
    setSearchQuery(category);
    setActiveFilter("all");
    setViewMode("single");
    setCurrentView("complaints");
  };

  const handleTriggerReseedFromHeader = async () => {
    if (userRole !== "admin") {
      toast.error("Seed failed - administrator permissions required.");
      return;
    }
    toast.warning("Reseeding database...");
    try {
      await api.reseedData();
      toast.success("Database reseeded successfully.");
      loadAllData();
    } catch (e) {
      toast.error("Reseed request failed.");
    }
  };

  // Nav menu definition
  const menuItems = [
    { id: "dashboard", label: "Dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
    { id: "complaints", label: "All Complaints", icon: <Layers className="h-4 w-4" /> },
    { id: "sla", label: "SLA Tracker", icon: <Timer className="h-4 w-4" /> },
    { id: "alerts", label: "Systemic Alerts", icon: <AlertTriangle className="h-4 w-4" /> },
    { id: "analytics", label: "Trend Analysis", icon: <Activity className="h-4 w-4" /> },
    { id: "clusters", label: "Cluster Analysis", icon: <Network className="h-4 w-4" /> },
    { id: "regulatory", label: "Regulatory Report", icon: <FileText className="h-4 w-4" /> },
  ];

  if (!authenticated) {
    return (
      <>
        <RoleLogin onLoginSuccess={handleLoginSuccess} />
        <Toaster position="bottom-right" richColors />
      </>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-50 font-sans">
      {/* 1. LEFT SIDEBAR (Premium Slate Navy) */}
      <aside className="w-56 bg-slate-900 border-r border-slate-800 text-slate-300 flex flex-col flex-shrink-0 select-none">
        {/* Brand Logo */}
        <div className="h-16 flex items-center px-5 border-b border-slate-800 gap-2.5">
          <div className="w-7.5 h-7.5 rounded bg-blue-600 flex items-center justify-center text-white font-black text-sm">
            UR
          </div>
          <span className="text-md font-black tracking-tight text-white">
            Uni<span className="text-blue-500">Resolve</span>
          </span>
        </div>

        {/* Menu Navigation */}
        <nav className="flex-1 py-4 space-y-1 overflow-y-auto">
          {menuItems.map((item) => {
            const active = currentView === item.id;
            return (
              <button
                key={item.id}
                onClick={() => {
                  setCurrentView(item.id);
                  if (item.id === "complaints") {
                    setSearchQuery("");
                    setActiveFilter("all");
                    setViewMode("single");
                  }
                }}
                className={`w-full flex items-center gap-3 px-5 py-2.5 text-xs font-bold transition-all border-l-3 border-l-transparent text-left cursor-pointer ${
                  active 
                    ? "bg-slate-800 text-white border-l-blue-500" 
                    : "hover:bg-slate-800/40 hover:text-slate-100"
                }`}
              >
                {item.icon}
                {item.label}
              </button>
            );
          })}
          
          <div className="h-px bg-slate-800 my-4" />
          
          <button
            onClick={() => setIsIngestOpen(true)}
            className="w-[calc(100%-32px)] mx-4 flex items-center justify-center gap-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-extrabold text-xs transition-colors cursor-pointer"
          >
            <PlusCircle className="h-4 w-4" />
            New Complaint
          </button>
        </nav>

        {/* User profile sidebar footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-950/30 flex items-center justify-between text-xs font-semibold text-slate-400">
          <div className="truncate pr-2">
            <span className="block text-[10px] text-slate-500 font-bold uppercase select-none">Acting User</span>
            <span className="text-slate-200 block truncate">{username}</span>
          </div>
          <Button
            size="icon"
            variant="ghost"
            onClick={logout}
            title="Log Out"
            className="h-8 w-8 text-slate-500 hover:text-rose-500 hover:bg-slate-800/50 cursor-pointer"
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </aside>

      {/* 2. MAIN LAYOUT CONTAINER */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header bar (Refined slate-navy/glassmorphic look) */}
        <header className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-6 flex-shrink-0 select-none">
          {/* Left: Badges */}
          <div className="flex items-center gap-3">
            {/* Systemic Alert Badge */}
            {alerts.length > 0 && (
              <Badge className="bg-rose-50 border border-rose-200 text-rose-700 font-extrabold text-[10px] animate-pulse flex items-center gap-1 hover:bg-rose-50">
                <AlertTriangle className="h-3.5 w-3.5" /> Systemic Alert Active
              </Badge>
            )}

            {/* Dedup Health indicator */}
            <Badge 
              variant="outline"
              className={`text-[10px] font-bold py-0.5 px-2 flex items-center gap-1.5 ${
                isDedupHealthy 
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200" 
                  : "bg-rose-50 text-rose-700 border-rose-200 animate-pulse"
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isDedupHealthy ? "bg-emerald-500" : "bg-rose-500 animate-ping"}`} />
              Dedup: {isDedupHealthy ? "Healthy" : "Degraded"}
            </Badge>

            {/* LLM Status badge */}
            {isWarmingUp ? (
              <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200 text-[10px] font-semibold animate-pulse flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin text-blue-600" /> AI Warming up...
              </Badge>
            ) : isLlmReachable ? (
              <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px] font-bold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> AI Engine: Active
              </Badge>
            ) : (
              <Badge variant="outline" className="bg-rose-50 text-rose-700 border-rose-200 text-[10px] font-bold flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-ping" /> AI: Offline
              </Badge>
            )}
          </div>

          {/* Right: Live switch & role representation info */}
          <div className="flex items-center gap-4 text-xs font-semibold text-slate-400">
            {/* Live Streaming Toggle */}
            <Button
              onClick={toggleLiveMode}
              variant="outline"
              disabled={isWarmingUp}
              className={`h-8 font-extrabold text-[10px] px-3.5 rounded-full cursor-pointer flex items-center gap-1.5 border transition-all ${
                liveMode
                  ? "bg-emerald-50 text-emerald-700 border-emerald-500 hover:bg-emerald-100 hover:text-emerald-800"
                  : "border-slate-200 text-slate-600 hover:bg-slate-50"
              } ${isWarmingUp ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${liveMode ? "bg-emerald-500 animate-ping" : "bg-slate-400"}`} />
              {liveMode ? "Live: Streaming" : "Live Streaming"}
            </Button>

            {/* Admin Seed Database */}
            {userRole === "admin" && (
              <Button
                variant="outline"
                size="icon"
                onClick={handleTriggerReseedFromHeader}
                title="Reseed database with 24 fresh complaints"
                className="h-8 w-8 text-slate-500 border-slate-200 hover:bg-slate-50 cursor-pointer"
              >
                <RotateCcw className="h-4 w-4" />
              </Button>
            )}

            {/* User role display */}
            <span className="hidden sm:inline-flex items-center gap-1.5 border-l border-slate-200 pl-4 py-1 select-none">
              Role: <strong className="text-slate-700 uppercase font-black">{userRole}</strong>
            </span>

            {/* Current clock */}
            <span className="hidden md:inline-flex items-center border-l border-slate-200 pl-4 py-1 select-none font-bold text-slate-600">
              {clock}
            </span>
          </div>
        </header>

        {/* 3. SCROLLABLE VIEWS WRAPPER */}
        <main className="flex-1 overflow-y-auto p-6">
          
          {/* Active Systemic Alerts Warning banner */}
          {alerts.length > 0 && localStorage.getItem("dismissSystemicAlert") !== "1" && (
            <div 
              onClick={() => setCurrentView("alerts")}
              className="bg-rose-50 border border-rose-200 hover:bg-rose-100/50 transition-all rounded-lg p-3 px-4 mb-4 text-xs font-bold text-rose-800 flex justify-between items-center cursor-pointer select-none"
            >
              <span>
                🚨 Systemic Outage Alert: {alerts[0].cluster?.cluster_size || alerts.length} similar complaints detected in &quot;{alerts[0].triage?.category || "related complaints"}&quot;. Possible root-cause isolated.
              </span>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  localStorage.setItem("dismissSystemicAlert", "1");
                  loadAllData();
                }}
                className="text-rose-500 hover:text-rose-700 font-extrabold text-sm px-1"
              >
                &times;
              </button>
            </div>
          )}

          {/* Model Warm-up Banner */}
          {isWarmingUp && (
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 px-4 mb-4 text-xs font-bold text-blue-800 flex items-center gap-2 select-none">
              <Loader2 className="h-4 w-4 animate-spin text-blue-600" />
              AI classification model and vector indexing databases warming up...
            </div>
          )}

          {/* Render Active View component */}
          {stats === null ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <Loader2 className="h-8 w-8 animate-spin text-blue-600 mb-4" />
              <p className="text-sm font-medium">Connecting to UniResolve secure portal...</p>
            </div>
          ) : (
            <>
              {currentView === "dashboard" && (
                <DashboardView
                  complaints={complaints}
                  stats={stats}
                  trends={trends}
                  onNavigate={setCurrentView}
                  onInspect={(c) => setInspectComplaintId(c.id)}
                  onOpenIngest={() => setIsIngestOpen(true)}
                />
              )}
              
              {currentView === "complaints" && (
                <ComplaintsView
                  complaints={complaints}
                  groups={groups}
                  searchQuery={searchQuery}
                  setSearchQuery={setSearchQuery}
                  activeFilter={activeFilter}
                  setActiveFilter={setActiveFilter}
                  viewMode={viewMode}
                  setViewMode={setViewMode}
                  onInspect={(c) => setInspectComplaintId(c.id)}
                  onOpenIngest={() => setIsIngestOpen(true)}
                />
              )}

              {currentView === "sla" && (
                <SlaView
                  complaints={complaints}
                  stats={stats}
                  onInspect={(c) => setInspectComplaintId(c.id)}
                />
              )}

              {currentView === "alerts" && (
                <AlertsView
                  complaints={complaints}
                  onInspect={(c) => setInspectComplaintId(c.id)}
                />
              )}

              {currentView === "analytics" && (
                <AnalyticsView
                  complaints={complaints}
                  stats={stats}
                  trends={trends}
                />
              )}

              {currentView === "clusters" && (
                <ClustersView
                  complaints={complaints}
                  onSelectCategory={handleSelectCategoryFromCluster}
                />
              )}

              {currentView === "regulatory" && (
                <RegulatoryView />
              )}
            </>
          )}
        </main>
      </div>

      {/* 4. DIALOG MODALS OVERLAYS */}
      
      {/* Detail Overlay Drawer Modal */}
      <DetailModal
        isOpen={inspectComplaintId !== null}
        onClose={() => setInspectComplaintId(null)}
        complaintId={inspectComplaintId}
        currentUserRole={userRole}
        onActionCompleted={loadAllData}
        onOpenEscalate={(id) => {
          setEscalateComplaintId(id);
        }}
      />

      {/* Ingest Modal */}
      <IngestModal
        isOpen={isIngestOpen}
        onClose={() => setIsIngestOpen(false)}
        onIngested={loadAllData}
      />

      {/* Escalate Modal */}
      <EscalateModal
        isOpen={escalateComplaintId !== null}
        onClose={() => setEscalateComplaintId(null)}
        complaintId={escalateComplaintId}
        onEscalated={() => {
          loadAllData();
          setInspectComplaintId(null);
        }}
      />

      <Toaster position="bottom-right" richColors />
    </div>
  );
}
