"use client";

import React, { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PlusCircle, Loader2, Sparkles, AlertCircle, FileAudio, FileImage, FileVideo, Mic, MicOff } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngested: () => void;
}

export default function IngestModal({ isOpen, onClose, onIngested }: IngestModalProps) {
  const [channel, setChannel] = useState("app");
  const [customerId, setCustomerId] = useState("");
  const [transactionId, setTransactionId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isSupported, setIsSupported] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        setIsSupported(true);
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = false;
        rec.lang = "en-US";

        rec.onresult = (event: any) => {
          let finalTranscript = "";
          for (let i = event.resultIndex; i < event.results.length; ++i) {
            if (event.results[i].isFinal) {
              finalTranscript += event.results[i][0].transcript;
            }
          }
          if (finalTranscript) {
            setText((prev) => {
              const trimmed = prev.trim();
              return trimmed ? `${trimmed} ${finalTranscript.trim()}` : finalTranscript.trim();
            });
          }
        };

        rec.onend = () => {
          setIsListening(false);
        };

        rec.onerror = (event: any) => {
          console.error("Speech recognition error", event.error);
          setIsListening(false);
          if (event.error === "not-allowed") {
            toast.error("Microphone access denied. Please enable permission in your browser settings.");
          } else if (event.error === "network") {
            toast.error("Speech recognition network error. Ensure your internet connection is stable and Google's speech recognition servers are reachable.");
          } else if (event.error !== "no-speech") {
            toast.error(`Speech recognition: ${event.error}`);
          }
        };

        recognitionRef.current = rec;
      }
    }
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      toast.error("Speech recognition is not supported in this browser.");
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
        toast.success("Speech recognition active. Speak into your microphone.", {
          duration: 3000,
        });
      } catch (err: any) {
        console.error(err);
        toast.error("Failed to start speech recognition.");
      }
    }
  };

  useEffect(() => {
    if (isOpen) {
      setChannel("app");
      setCustomerId("");
      setTransactionId("");
      setText("");
      setFile(null);
      setFilePreview(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } else {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    }
  }, [isOpen]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    if (selectedFile) {
      const reader = new FileReader();
      reader.onload = () => {
        setFilePreview(reader.result as string);
      };
      reader.readAsDataURL(selectedFile);
    } else {
      setFilePreview(null);
    }
  };

  const handleSubmit = async () => {
    // Validation — Customer ID is always required; Transaction ID is optional
    if (!file && !customerId.trim()) {
      toast.error("Customer ID is required");
      return;
    }
    if (!text.trim() && !file) {
      toast.error("Please enter complaint text or attach an evidence file.");
      return;
    }

    setSubmitting(true);
    let mediaFile: string | null = null;
    let mediaType: string | null = null;

    if (file && filePreview) {
      mediaFile = filePreview;
      mediaType = file.type;
    }

    try {
      await api.ingest({
        channel,
        raw_text: text,
        media_file: mediaFile,
        media_type: mediaType,
        customer_id: customerId.trim() || null,
        transaction_id: transactionId.trim() || null,
      });
      toast.success("Complaint ingested and AI triaged successfully!");
      onIngested();
      onClose();
    } catch (err: any) {
      toast.error(err.message || "Failed to ingest complaint.");
    } finally {
      setSubmitting(false);
    }
  };

  const renderFilePreview = () => {
    if (!file) return null;
    const isImage = file.type.startsWith("image/");
    const isAudio = file.type.startsWith("audio/");
    const isVideo = file.type.startsWith("video/");

    return (
      <div className="mt-3 p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center gap-3">
        <div className="p-2 rounded bg-white border border-slate-100 flex-shrink-0 text-slate-500">
          {isImage && <FileImage className="h-6 w-6 text-blue-500" />}
          {isAudio && <FileAudio className="h-6 w-6 text-amber-500" />}
          {isVideo && <FileVideo className="h-6 w-6 text-purple-500" />}
          {!isImage && !isAudio && !isVideo && <AlertCircle className="h-6 w-6 text-slate-500" />}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-slate-700 truncate">{file.name}</p>
          <p className="text-[10px] text-slate-400">{(file.size / (1024 * 1024)).toFixed(2)} MB · {file.type}</p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={() => {
            setFile(null);
            setFilePreview(null);
            if (fileInputRef.current) fileInputRef.current.value = "";
          }}
          className="text-rose-500 hover:text-rose-600 font-bold text-xs h-7 px-2 cursor-pointer"
        >
          Remove
        </Button>
      </div>
    );
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg w-full font-sans border-slate-200 overflow-y-auto max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="text-lg font-bold flex items-center gap-2 text-rose-600">
            <PlusCircle className="h-5 w-5" /> Submit New Complaint
          </DialogTitle>
          <DialogDescription className="text-slate-500 text-xs">
            Ingest customer grievances from any channel (App, Email, Social, Call Center, Branch, Web).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-2">
          {/* Row 1: Channel */}
          <div className="space-y-1">
            <Label htmlFor="igChan" className="text-xs font-semibold text-slate-700">Channel</Label>
            <Select value={channel} onValueChange={(val) => setChannel(val || "")}>
              <SelectTrigger id="igChan" className="border-slate-200 text-sm">
                <SelectValue placeholder="Select channel" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="app">Mobile App</SelectItem>
                <SelectItem value="email">Email</SelectItem>
                <SelectItem value="social">Social Media</SelectItem>
                <SelectItem value="ivr">IVR / Call Center</SelectItem>
                <SelectItem value="branch">Branch Visit</SelectItem>
                <SelectItem value="web">Web Portal</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Row 2: Customer ID and Transaction ID */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="igCustId" className="text-xs font-semibold text-slate-700">Customer ID</Label>
              <Input
                id="igCustId"
                type="text"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value)}
                placeholder="e.g. 10010245 (8-digit)"
                className="border-slate-200 text-sm focus-visible:ring-blue-500"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="igTxId" className="text-xs font-semibold text-slate-700">
                Transaction ID <span className="text-slate-400 font-normal">(optional)</span>
              </Label>
              <Input
                id="igTxId"
                type="text"
                value={transactionId}
                onChange={(e) => setTransactionId(e.target.value)}
                placeholder="e.g. 300304820001 (12-digit)"
                className="border-slate-200 text-sm focus-visible:ring-blue-500"
              />
            </div>
          </div>

          {/* Row 3: Complaint Text */}
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <Label htmlFor="igText" className="text-xs font-semibold text-slate-700">Complaint Text</Label>
              {isSupported && (
                <button
                  type="button"
                  onClick={toggleListening}
                  className={`flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-all duration-200 cursor-pointer ${
                    isListening
                      ? "bg-rose-50 border-rose-200 text-rose-600 animate-pulse shadow-sm shadow-rose-100"
                      : "bg-slate-50 hover:bg-slate-100 text-slate-600 border-slate-200 hover:border-slate-300"
                  }`}
                  title={isListening ? "Stop listening" : "Start voice input"}
                >
                  {isListening ? (
                    <>
                      <span className="relative flex h-2 w-2">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
                      </span>
                      <MicOff className="h-3.5 w-3.5 text-rose-600 animate-bounce" />
                      <span>Listening...</span>
                    </>
                  ) : (
                    <>
                      <Mic className="h-3.5 w-3.5 text-slate-500" />
                      <span>Speak</span>
                    </>
                  )}
                </button>
              )}
            </div>
            <Textarea
              id="igText"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="e.g. My loan EMI was debited twice from my account. Please refund..."
              className="min-h-[100px] border-slate-200 text-sm resize-none focus-visible:ring-blue-500"
            />
          </div>

          {/* Row 4: Evidence File */}
          <div className="space-y-1">
            <Label htmlFor="igFile" className="text-xs font-semibold text-slate-700">Attach Evidence</Label>
            <div className="border border-dashed border-slate-200 rounded-lg p-4 bg-slate-50/50 hover:bg-slate-50 transition-colors relative cursor-pointer flex flex-col items-center justify-center text-center">
              <Input
                ref={fileInputRef}
                id="igFile"
                type="file"
                accept="image/*,audio/*,video/*"
                onChange={handleFileChange}
                className="absolute inset-0 opacity-0 cursor-pointer h-full w-full"
              />
              <span className="text-xs font-medium text-slate-500">Drag & drop or Click to browse</span>
              <span className="text-[10px] text-slate-400 mt-1">Accepts Screenshots, Voice logs, Screen recordings</span>
            </div>
            {renderFilePreview()}
          </div>
        </div>

        <DialogFooter className="pt-2">
          <Button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full bg-rose-600 hover:bg-rose-700 font-extrabold text-xs h-10 gap-2 cursor-pointer text-white"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Ingesting & Triage in progress...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" /> Analyse & Submit Complaint
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
