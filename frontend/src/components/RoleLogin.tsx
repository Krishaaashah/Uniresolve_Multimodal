"use client";

import React, { useState } from "react";
import { api } from "@/lib/api";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2, ShieldCheck, UserCheck, Users } from "lucide-react";
import { toast } from "sonner";

interface RoleLoginProps {
  onLoginSuccess: (username: string, role: string, token: string) => void;
}

export default function RoleLogin({ onLoginSuccess }: RoleLoginProps) {
  const [loadingRole, setLoadingRole] = useState<string | null>(null);

  const handleRoleLogin = async (role: "agent" | "supervisor" | "admin") => {
    setLoadingRole(role);
    const credentials = {
      agent: { username: "agent", password: "agent123" },
      supervisor: { username: "supervisor", password: "supervisor123" },
      admin: { username: "admin", password: "admin123" },
    }[role];

    try {
      const res = await api.login(credentials);
      localStorage.setItem("auth_token", res.access_token);
      localStorage.setItem("auth_role", res.role);
      localStorage.setItem("auth_username", res.username);
      
      toast.success(`Logged in as ${res.role.toUpperCase()}`);
      onLoginSuccess(res.username, res.role, res.access_token);
    } catch (err: any) {
      toast.error(err.message || "Authentication failed. Backend might be offline.");
    } finally {
      setLoadingRole(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 font-sans">
      <Card className="w-full max-w-md border-slate-800 bg-slate-900 text-slate-100 shadow-2xl relative overflow-hidden">
        <div className="absolute top-0 inset-x-0 h-1.5 bg-gradient-to-r from-blue-500 via-indigo-600 to-sky-400" />
        <CardHeader className="text-center pt-8">
          <span className="text-xs font-bold tracking-widest text-blue-400 uppercase">Union Bank · Idea 2.0</span>
          <CardTitle className="text-3xl font-extrabold tracking-tight text-white mt-1">UniResolve</CardTitle>
          <CardDescription className="text-slate-400 text-sm mt-1">
            Unified Customer Complaint Communication Dashboard
          </CardDescription>
        </CardHeader>
        <CardContent className="px-6 pb-8 space-y-6">
          <div className="text-center text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Select your role to continue
          </div>
          <div className="flex flex-col gap-3">
            {/* Agent Button */}
            <Button
              variant="outline"
              disabled={loadingRole !== null}
              onClick={() => handleRoleLogin("agent")}
              className="flex items-center gap-4 p-5 h-auto text-left justify-start border-slate-700 bg-slate-800/50 hover:bg-blue-950/30 hover:border-blue-700 hover:text-white transition-all text-slate-200"
            >
              <div className="p-2.5 rounded-lg bg-blue-900/40 text-blue-400">
                <UserCheck className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <div className="font-bold text-sm text-slate-200">Customer Service Agent</div>
                <div className="text-xs font-normal text-slate-400 mt-0.5">Handle and resolve incoming complaints</div>
              </div>
              {loadingRole === "agent" && <Loader2 className="h-4 w-4 animate-spin text-blue-400 ml-auto" />}
            </Button>

            {/* Supervisor Button */}
            <Button
              variant="outline"
              disabled={loadingRole !== null}
              onClick={() => handleRoleLogin("supervisor")}
              className="flex items-center gap-4 p-5 h-auto text-left justify-start border-slate-700 bg-slate-800/50 hover:bg-indigo-950/30 hover:border-indigo-700 hover:text-white transition-all text-slate-200"
            >
              <div className="p-2.5 rounded-lg bg-indigo-900/40 text-indigo-400">
                <Users className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <div className="font-bold text-sm text-slate-200">L2/L3 Supervisor</div>
                <div className="text-xs font-normal text-slate-400 mt-0.5">Manage escalations and team oversight</div>
              </div>
              {loadingRole === "supervisor" && <Loader2 className="h-4 w-4 animate-spin text-indigo-400 ml-auto" />}
            </Button>

            {/* Admin Button */}
            <Button
              variant="outline"
              disabled={loadingRole !== null}
              onClick={() => handleRoleLogin("admin")}
              className="flex items-center gap-4 p-5 h-auto text-left justify-start border-slate-700 bg-slate-800/50 hover:bg-rose-950/20 hover:border-rose-800 hover:text-white transition-all text-slate-200"
            >
              <div className="p-2.5 rounded-lg bg-rose-950/40 text-rose-400">
                <ShieldCheck className="h-6 w-6" />
              </div>
              <div className="flex-1">
                <div className="font-bold text-sm text-slate-200">System Administrator</div>
                <div className="text-xs font-normal text-slate-400 mt-0.5">Full audit access, seed controls and report filings</div>
              </div>
              {loadingRole === "admin" && <Loader2 className="h-4 w-4 animate-spin text-rose-400 ml-auto" />}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
