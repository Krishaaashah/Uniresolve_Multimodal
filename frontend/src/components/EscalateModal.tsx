"use client";

import React, { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { ArrowUp, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface EscalateModalProps {
  isOpen: boolean;
  onClose: () => void;
  complaintId: string | null;
  onEscalated: () => void;
}

export default function EscalateModal({ isOpen, onClose, complaintId, onEscalated }: EscalateModalProps) {
  const [level, setLevel] = useState("L2 Supervisor");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setReason("");
      setLevel("L2 Supervisor");
    }
  }, [isOpen]);

  const handleSubmit = async () => {
    if (!complaintId) return;
    if (!reason.trim()) {
      toast.error("Please provide an escalation reason.");
      return;
    }
    setSubmitting(true);
    try {
      await api.escalate(complaintId, level, reason);
      toast.success(`Complaint successfully escalated to ${level}`);
      onEscalated();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to escalate complaint.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md w-full font-sans border-slate-200">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold flex items-center gap-2 text-indigo-700">
            <ArrowUp className="h-5 w-5" /> Escalate Complaint
          </DialogTitle>
          <DialogDescription className="text-slate-500 text-xs">
            Submit a request to escalate this ticket to a senior supervisor or external auditor.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-3">
          <div className="space-y-1">
            <Label htmlFor="level" className="text-xs font-semibold text-slate-700">Escalate To</Label>
            <Select value={level} onValueChange={(val) => setLevel(val || "")}>
              <SelectTrigger id="level" className="border-slate-200 text-sm">
                <SelectValue placeholder="Select level" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="L2 Supervisor">L2 Supervisor</SelectItem>
                <SelectItem value="L3 Manager">L3 Manager</SelectItem>
                <SelectItem value="L4 Regulatory">L4 Regulatory (RBI Ombudsman)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="reason" className="text-xs font-semibold text-slate-700">Reason for Escalation</Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Provide a reason or context for this escalation..."
              className="min-h-[100px] border-slate-200 text-sm resize-none focus-visible:ring-indigo-500"
            />
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button 
            variant="outline" 
            onClick={onClose}
            className="text-xs font-bold border-slate-200 cursor-pointer h-9"
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting}
            className="bg-indigo-600 hover:bg-indigo-700 font-bold text-xs h-9 cursor-pointer text-white"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Escalating...
              </>
            ) : (
              "Confirm Escalation"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
