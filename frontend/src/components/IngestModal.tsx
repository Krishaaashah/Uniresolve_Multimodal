"use client";

import React, { useState, useEffect, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { 
  PlusCircle, Loader2, Sparkles, AlertCircle, FileAudio, FileImage, FileVideo, 
  Mic, Square, Play, Pause, RotateCcw, UploadCloud, Radio, ShieldCheck, Volume2
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngested: () => void;
}

export default function IngestModal({ isOpen, onClose, onIngested }: IngestModalProps) {
  const [activeMode, setActiveMode] = useState<"audio" | "text">("audio");
  const [channel, setChannel] = useState("app");
  const [customerId, setCustomerId] = useState("");
  const [transactionId, setTransactionId] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [filePreview, setFilePreview] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const audioFileInputRef = useRef<HTMLInputElement>(null);

  // Audio Recording states
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [recordedAudioBlob, setRecordedAudioBlob] = useState<Blob | null>(null);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState<string | null>(null);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const timerIntervalRef = useRef<any>(null);
  const audioPlayerRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setChannel("voice");
      setCustomerId("");
      setTransactionId("");
      setText("");
      setFile(null);
      setFilePreview(null);
      setRecordedAudioBlob(null);
      setRecordedAudioUrl(null);
      setIsRecording(false);
      setRecordingSeconds(0);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (audioFileInputRef.current) audioFileInputRef.current.value = "";
    } else {
      stopRecordingCleanup();
    }
  }, [isOpen]);

  const startRecording = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        toast.error("Audio recording is not supported in this browser.");
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        setRecordedAudioBlob(audioBlob);
        const url = URL.createObjectURL(audioBlob);
        setRecordedAudioUrl(url);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(200);
      setIsRecording(true);
      setRecordingSeconds(0);

      timerIntervalRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);

      toast.info("Recording customer voice grievance... Speak into microphone.");
    } catch (err: any) {
      console.error("Recording error:", err);
      toast.error("Microphone access denied or audio device not found.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerIntervalRef.current) {
        clearInterval(timerIntervalRef.current);
      }
      toast.success("Recording captured. Ready for multimodal analysis.");
    }
  };

  const stopRecordingCleanup = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
    }
    setIsRecording(false);
  };

  const resetAudio = () => {
    stopRecordingCleanup();
    setRecordedAudioBlob(null);
    setRecordedAudioUrl(null);
    setRecordingSeconds(0);
    if (audioFileInputRef.current) audioFileInputRef.current.value = "";
  };

  const handleAudioFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    if (selectedFile) {
      setRecordedAudioBlob(selectedFile);
      const url = URL.createObjectURL(selectedFile);
      setRecordedAudioUrl(url);
      toast.success(`Loaded audio file: ${selectedFile.name}`);
    }
  };

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

  const formatTimer = (secs: number) => {
    const m = Math.floor(secs / 60).toString().padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const handleSubmit = async () => {
    if (activeMode === "audio") {
      if (!recordedAudioBlob) {
        toast.error("Please record voice audio or upload an audio file first.");
        return;
      }

      setSubmitting(true);
      try {
        const formData = new FormData();
        const audioFile = recordedAudioBlob instanceof File 
          ? recordedAudioBlob 
          : new File([recordedAudioBlob], "customer_voice.wav", { type: "audio/wav" });
        
        formData.append("audio_file", audioFile);
        if (customerId.trim()) formData.append("customer_id", customerId.trim());
        if (transactionId.trim()) formData.append("transaction_id", transactionId.trim());
        formData.append("channel", "voice");
        formData.append("channel_metadata", JSON.stringify({ source: "frontend_voice_recorder" }));

        await api.ingestAudio(formData);
        toast.success("Multimodal Voice Grievance triaged with WavLM + FinBERT!");
        onIngested();
        onClose();
      } catch (err: any) {
        toast.error(err.message || "Failed to ingest audio grievance.");
      } finally {
        setSubmitting(false);
      }
    } else {
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
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-[620px] max-h-[90vh] overflow-y-auto bg-white border border-slate-200 shadow-2xl rounded-2xl p-6">
        <DialogHeader className="pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600">
              <PlusCircle className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold text-slate-900 tracking-tight">
                Ingest Customer Grievance
              </DialogTitle>
              <DialogDescription className="text-xs text-slate-500 mt-0.5">
                Submit raw customer voice notes, transcripts, or structured complaints for Multimodal Triage.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* Ingestion Mode Switcher */}
        <div className="mt-2">
          <Tabs value={activeMode} onValueChange={(val) => setActiveMode(val as any)} className="w-full">
            <TabsList className="grid grid-cols-2 bg-slate-100 p-1 rounded-xl">
              <TabsTrigger 
                value="audio" 
                className="flex items-center gap-2 text-xs font-semibold data-[state=active]:bg-white data-[state=active]:text-indigo-600 data-[state=active]:shadow-sm rounded-lg py-2"
              >
                <Radio className="h-4 w-4 text-indigo-500" />
                Voice Grievance (Multimodal Fusion)
              </TabsTrigger>
              <TabsTrigger 
                value="text" 
                className="flex items-center gap-2 text-xs font-semibold data-[state=active]:bg-white data-[state=active]:text-indigo-600 data-[state=active]:shadow-sm rounded-lg py-2"
              >
                <Sparkles className="h-4 w-4 text-purple-500" />
                Text & Attachment Form
              </TabsTrigger>
            </TabsList>

            {/* TAB 1: AUDIO GRIEVANCE */}
            <TabsContent value="audio" className="space-y-4 pt-3">
              <div className="p-4 bg-gradient-to-br from-indigo-50/70 to-blue-50/70 border border-indigo-100/80 rounded-2xl text-center space-y-3">
                <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-indigo-700">
                  <Volume2 className="h-4 w-4 text-indigo-600" />
                  <span>WavLM Acoustic Prosody & Speech Fusion</span>
                  <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 text-[10px] rounded-full font-mono">CPU Ready</span>
                </div>

                {/* Recorder Controls */}
                <div className="flex flex-col items-center justify-center gap-2 py-2">
                  {!recordedAudioUrl ? (
                    <div className="flex flex-col items-center gap-2">
                      <button
                        type="button"
                        onClick={isRecording ? stopRecording : startRecording}
                        className={`h-16 w-16 rounded-full flex items-center justify-center transition-all duration-300 shadow-md ${
                          isRecording 
                            ? "bg-rose-500 hover:bg-rose-600 text-white animate-pulse ring-4 ring-rose-200" 
                            : "bg-indigo-600 hover:bg-indigo-700 text-white hover:scale-105"
                        }`}
                      >
                        {isRecording ? <Square className="h-6 w-6" /> : <Mic className="h-7 w-7" />}
                      </button>
                      
                      <div className="text-xs font-mono font-bold text-slate-700">
                        {isRecording ? (
                          <span className="text-rose-600 flex items-center gap-1.5">
                            <span className="h-2 w-2 rounded-full bg-rose-500 animate-ping" />
                            Recording: {formatTimer(recordingSeconds)}
                          </span>
                        ) : (
                          <span className="text-slate-500">Tap microphone to record voice grievance</span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="w-full bg-white p-3 rounded-xl border border-indigo-100 flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-slate-700 flex items-center gap-1.5">
                          <FileAudio className="h-4 w-4 text-amber-500" />
                          Voice Recording Captured
                        </span>
                        <Button 
                          type="button" 
                          size="sm" 
                          variant="ghost" 
                          onClick={resetAudio}
                          className="h-7 text-xs text-rose-500 hover:text-rose-600 font-semibold"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" /> Re-record
                        </Button>
                      </div>
                      <audio ref={audioPlayerRef} controls src={recordedAudioUrl} className="w-full h-10 mt-1" />
                    </div>
                  )}

                  {/* Or Upload Audio File */}
                  {!recordedAudioUrl && !isRecording && (
                    <div className="w-full pt-2 border-t border-indigo-100/60">
                      <label className="cursor-pointer flex items-center justify-center gap-2 text-xs font-medium text-indigo-600 hover:text-indigo-800 transition-colors">
                        <UploadCloud className="h-4 w-4" />
                        <span>Or upload audio file (.wav, .mp3, .m4a, .webm)</span>
                        <input
                          ref={audioFileInputRef}
                          type="file"
                          accept="audio/*"
                          onChange={handleAudioFileUpload}
                          className="hidden"
                        />
                      </label>
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-center gap-1.5 text-[11px] text-slate-500 bg-white/60 py-1.5 px-3 rounded-lg border border-slate-100">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                  <span>Presidio PII Scrubber automatically masks PAN, Aadhaar & Mobile before storage.</span>
                </div>
              </div>

              {/* Customer ID & Transaction ID */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold text-slate-700">Customer ID</Label>
                  <Input
                    placeholder="e.g. CUST-10245"
                    value={customerId}
                    onChange={(e) => setCustomerId(e.target.value)}
                    className="h-9 text-xs rounded-lg border-slate-200"
                  />
                  <p className="text-[10px] text-slate-400">Optional (Auto-extracted from speech if spoken)</p>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold text-slate-700">Linked Transaction ID</Label>
                  <Input
                    placeholder="e.g. TXN-10245-F1"
                    value={transactionId}
                    onChange={(e) => setTransactionId(e.target.value)}
                    className="h-9 text-xs rounded-lg border-slate-200"
                  />
                  <p className="text-[10px] text-slate-400">Optional reference transaction</p>
                </div>
              </div>
            </TabsContent>

            {/* TAB 2: TEXT & ATTACHMENT FORM */}
            <TabsContent value="text" className="space-y-4 pt-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-bold text-slate-700">Channel</Label>
                  <Select value={channel} onValueChange={(val: any) => setChannel(val || 'app')}>
                    <SelectTrigger className="h-9 text-xs rounded-lg border-slate-200">
                      <SelectValue placeholder="Select Channel" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="app">Mobile Banking App</SelectItem>
                      <SelectItem value="web">Web Portal</SelectItem>
                      <SelectItem value="email">Email Support</SelectItem>
                      <SelectItem value="ivr">IVR / Helpline</SelectItem>
                      <SelectItem value="branch">Branch In-Person</SelectItem>
                      <SelectItem value="social">Social Media</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs font-bold text-slate-700">Customer ID <span className="text-rose-500">*</span></Label>
                  <Input
                    placeholder="e.g. CUST-10245"
                    value={customerId}
                    onChange={(e) => setCustomerId(e.target.value)}
                    className="h-9 text-xs rounded-lg border-slate-200"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-700">Transaction ID</Label>
                <Input
                  placeholder="e.g. TXN-10245-F1 or 12-digit number"
                  value={transactionId}
                  onChange={(e) => setTransactionId(e.target.value)}
                  className="h-9 text-xs rounded-lg border-slate-200"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-700">Complaint Description</Label>
                <Textarea
                  placeholder="Describe the customer grievance in detail..."
                  rows={4}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  className="text-xs rounded-lg border-slate-200 resize-none"
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-700">Evidence File (Screenshot, Receipt, Slip)</Label>
                <Input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,video/*,audio/*,.pdf"
                  onChange={handleFileChange}
                  className="text-xs rounded-lg border-slate-200"
                />
                {file && (
                  <div className="mt-2 p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
                    <span className="text-xs text-slate-700 truncate">{file.name}</span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setFile(null);
                        setFilePreview(null);
                        if (fileInputRef.current) fileInputRef.current.value = "";
                      }}
                      className="h-6 text-xs text-rose-500 font-bold"
                    >
                      Remove
                    </Button>
                  </div>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <DialogFooter className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
          <Button type="button" variant="outline" size="sm" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={handleSubmit}
            disabled={submitting || isRecording}
            className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs px-5 shadow-sm"
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
                {activeMode === "audio" ? "Analyzing Audio & Triaging..." : "Triaging..."}
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-1.5" />
                {activeMode === "audio" ? "Submit Voice Grievance" : "Ingest & Auto-Triage"}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
