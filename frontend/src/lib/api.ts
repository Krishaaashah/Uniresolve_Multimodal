// UniResolve Frontend API Client in TypeScript

export const API_BASE = typeof window !== 'undefined'
  ? (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? 'http://127.0.0.1:8000' : window.location.origin)
  : 'http://127.0.0.1:8000';

function getHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  
  if (typeof window !== 'undefined') {
    const localKey = localStorage.getItem('UNIRESOLVE_API_KEY');
    const apiKey = (!localKey || localKey === 'undefined' || localKey === 'null' || localKey.trim() === '') ? 'dev-secret-key' : localKey;
    headers['X-Api-Key'] = apiKey;
    
    const token = localStorage.getItem('auth_token');
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }
  
  return headers;
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const mergedOptions = {
    ...options,
    headers: {
      ...getHeaders(),
      ...(options.headers || {}),
    },
  };
  
  const res = await fetch(url, mergedOptions);
  
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const errorData = await res.json();
      if (errorData && errorData.detail) {
        if (typeof errorData.detail === 'string') {
          msg = errorData.detail;
        } else if (Array.isArray(errorData.detail)) {
          msg = errorData.detail.map((d: any) => d.msg || d).join(', ');
        }
      }
    } catch (e) {}
    throw new Error(msg);
  }
  
  // Some endpoints (like downloads) might return raw text or need blob, but we expect JSON by default.
  if (res.headers.get('content-type')?.includes('text/csv')) {
    return (await res.text()) as unknown as T;
  }
  return res.json() as Promise<T>;
}

export interface Complaint {
  id: string;
  ticket_id?: string;
  parent_ticket_id?: string;
  channel: 'app' | 'email' | 'social' | 'ivr' | 'branch' | 'web';
  channel_metadata?: {
    attachments?: Array<{ type: string; url: string }>;
    sender?: string;
    subject?: string;
    author?: string;
    url?: string;
  };
  raw_text: string;
  masked_text: string;
  summary?: string;
  received_at: string;
  status: 'pending' | 'in_review' | 'resolved' | 'escalated';
  escalation_level?: string;
  escalation_history?: Array<{
    id: string;
    from_level: string;
    to_level: string;
    reason: string;
    escalated_by: string;
    escalated_at: string;
  }>;
  communication_history: Array<{
    id: string;
    author: 'customer' | 'agent' | 'system';
    author_name: string;
    content: string;
    is_ai_draft?: boolean;
    timestamp: string;
  }>;
  triage?: {
    category: string;
    severity: 'critical' | 'high' | 'medium' | 'low';
    sentiment: 'angry' | 'frustrated' | 'neutral' | 'satisfied';
    key_issue: string;
    suggested_response: string;
    confidence: number;
    detected_language?: string;
    severity_reason?: string;
  };
  sla?: {
    deadline: string;
    hours_allowed: number;
    hours_elapsed: number;
    hours_remaining: number;
    percent_used: number;
    status: 'on_track' | 'at_risk' | 'breached';
    breached: boolean;
  };
  cluster?: {
    cluster_id?: string;
    is_duplicate: boolean;
    duplicate_reason?: string;
    cluster_size: number;
    affected_customers?: number;
    systemic_alert: boolean;
    cluster_description?: string;
  };
  rbi_status?: string;
  rbi_deadline?: string;
  customer_id?: string;
  transaction_id?: string;
  duplicate_count?: number;
  duplicate_channels?: string[];
  resolved_at?: string;
  recurring?: boolean;
  recurring_of?: string | null;
  needs_human?: boolean;
  needs_info?: boolean;
  agent_trace?: Array<{
    node: string;
    timestamp: string;
    result?: any;
  }>;
  thread_id?: string;
  linked_incident?: string;
  priority_score?: number;
  detected_language?: string;
  missing_fields_question?: string;
}

export interface Stats {
  total: number;
  pending: number;
  resolved: number;
  resolved_today?: number;
  escalated: number;
  sla_breached: number;
  sla_at_risk?: number;
  systemic_alerts: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
  by_channel: Record<string, number>;
  avg_resolution_minutes?: number;
  daily_trend: Array<{ date: string; count: number }>;
}

export interface AuditLog {
  id: string;
  complaint_id: string;
  action: string;
  actor: string;
  role: string;
  timestamp: string;
  changes?: string;
}

export interface CustomerProfile {
  id: string;
  name: string;
  account_no: string;
  account_type: string;
  kyc_status: string;
  risk_tier: string;
  phone: string;
  balance: string;
  transactions: Array<{
    date: string;
    desc: string;
    ref: string;
    amount: string;
    status: 'Success' | 'Failed';
  }>;
}

export interface ClusterNode {
  category: string;
  complaint_count: number;
  customer_count: number;
  severity_breakdown: Record<string, number>;
}

export interface RootCause {
  cause: string;
  count_estimate: number;
  example_complaint: string;
}

export interface TimelineProgress {
  ticket_id: string;
  current_stage: string;
  elapsed_time: string;
  steps: Array<{
    stage: string;
    completed: boolean;
    timestamp?: string;
    actor?: string;
  }>;
}

export interface GroupItem {
  group_id: string;
  customer_id: string;
  transaction_id: string | null;
  count: number;
  channels: string[];
  first_raised: string;
  last_raised: string;
  tickets: Array<{ id: string; ticket_id?: string; channel: string; timestamp: string }>;
  grouping_reason: string;
}

export const api = {
  login: (credentials: any) =>
    apiFetch<any>('/complaints/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    }),
    
  getComplaints: (search?: string) => {
    const q = search ? `?search=${encodeURIComponent(search)}` : '';
    return apiFetch<Complaint[]>(`/complaints${q}`);
  },
  
  getStats: () => apiFetch<Stats>('/complaints/stats'),
  
  getAlerts: () => apiFetch<{ alerts: Complaint[] }>('/complaints/alerts'),
  
  getTrends: () =>
    apiFetch<any>('/complaints/trends?group_by=category&window=7d'),
    
  getGroups: () => apiFetch<GroupItem[]>('/complaints/groups'),
  
  getTimeline: (id: string) => apiFetch<TimelineProgress>(`/complaints/${id}/timeline`),
  
  getAudit: (id: string) => apiFetch<AuditLog[]>(`/complaints/${id}/audit`),
  
  getDuplicates: (ticketId: string) =>
    apiFetch<{ tickets: Array<{ id: string; ticket_id: string; channel: string; timestamp: string }> }>(
      `/complaints/${ticketId}/duplicates`
    ),
    
  getRegulatoryReport: () =>
    apiFetch<any>('/complaints/reports/regulatory'),
    
  getRootCause: () => apiFetch<{ root_causes: RootCause[]; message?: string }>('/complaints/root-cause'),
  
  getClusters: () => apiFetch<ClusterNode[]>('/complaints/clusters'),
  
  getSystemicAlerts: () => apiFetch<any[]>('/complaints/systemic-alerts'),
  
  getSemanticClusters: () => apiFetch<any[]>('/complaints/semantic-clusters'),
  
  getExplain: (id: string) => apiFetch<{ explanation: string }>(`/complaints/${id}/explain`),
  
  getCustomer: (id: string) => apiFetch<CustomerProfile>(`/customers/${id}`),
  
  ingest: (data: any) =>
    apiFetch<any>('/complaints/ingest', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
    
  doAction: (id: string, action: string, customResponse: string) =>
    apiFetch<any>(`/complaints/${id}/action`, {
      method: 'POST',
      body: JSON.stringify({ complaint_id: id, action, agent_id: 'agent_krisha', custom_response: customResponse }),
    }),
    
  escalate: (id: string, toLevel: string, reason: string) =>
    apiFetch<any>(`/complaints/${id}/escalate`, {
      method: 'POST',
      body: JSON.stringify({ complaint_id: id, to_level: toLevel, reason, agent_id: 'agent_krisha' }),
    }),
    
  sendReply: (id: string, text: string) =>
    apiFetch<any>(`/complaints/${id}/reply`, {
      method: 'POST',
      body: JSON.stringify({ complaint_id: id, content: text, author: 'agent', author_name: 'Agent Krisha' }),
    }),
    
  linkCustomer: (id: string, customerId: string | null) =>
    apiFetch<any>(`/complaints/${id}/link-customer`, {
      method: 'POST',
      body: JSON.stringify({ customer_id: customerId }),
    }),
    
  reseedData: () =>
    apiFetch<any>('/admin/seed', {
      method: 'POST',
    }),
    
  getHealth: () => apiFetch<any>('/health'),
};

export async function approveComplaintDraft(complaintId: string): Promise<{ success: boolean; complaint: Complaint }> {
  return apiFetch<{ success: boolean; complaint: Complaint }>(`/complaints/${complaintId}/approve`, {
    method: 'POST',
  });
}

export async function provideComplaintInfo(
  complaintId: string,
  transaction_ref?: string,
  amount?: number
): Promise<{ success: boolean; complaint: Complaint }> {
  return apiFetch<{ success: boolean; complaint: Complaint }>(`/complaints/${complaintId}/provide-info`, {
    method: 'POST',
    body: JSON.stringify({ transaction_ref, amount }),
  });
}

export async function verifyComplaintLedger(complaintId: string): Promise<{ complaint_id: string; valid: boolean }> {
  return apiFetch<{ complaint_id: string; valid: boolean }>(`/complaints/${complaintId}/ledger/verify`);
}

export async function fetchComplaintTrace(complaintId: string): Promise<{ complaint_id: string; agent_trace: Array<any> }> {
  return apiFetch<{ complaint_id: string; agent_trace: Array<any> }>(`/complaints/${complaintId}/trace`);
}

export async function fetchActiveIncidents(): Promise<Array<{ cluster_id: string; label: string; customer_count: number; ticket_count: number; status: string }>> {
  return apiFetch<Array<{ cluster_id: string; label: string; customer_count: number; ticket_count: number; status: string }>>(`/complaints/incidents/all`);
}
