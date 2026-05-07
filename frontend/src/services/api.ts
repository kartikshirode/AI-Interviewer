// NOTE: tokens are kept in localStorage. This is XSS-readable; switching to
// httpOnly cookies requires a backend cookie-session refactor and is tracked
// as a security follow-up (audit ISSUE-22).
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';
export const API_BASE = API_BASE_URL;

// FastAPI returns `detail` as a string for HTTPException, but as an array of
// {loc, msg, type} objects on Pydantic validation failures (422). Render both
// shapes as a readable string so callers don't show "[object Object]".
function formatApiError(body: unknown, status: number): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            const msg = (item as { msg?: unknown }).msg;
            const loc = (item as { loc?: unknown }).loc;
            const field = Array.isArray(loc) ? loc.filter((p) => p !== 'body').join('.') : '';
            return field ? `${field}: ${msg}` : String(msg);
          }
          return JSON.stringify(item);
        })
        .join('; ');
    }
    if (detail) return JSON.stringify(detail);
  }
  return `Request failed with status ${status}`;
}

class ApiService {
  private token: string | null = null;
  private candidateToken: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('token', token);
      } else {
        localStorage.removeItem('token');
      }
    }
  }

  getToken(): string | null {
    if (this.token) return this.token;
    if (typeof window !== 'undefined') {
      return localStorage.getItem('token');
    }
    return null;
  }

  setCandidateToken(token: string | null) {
    this.candidateToken = token;
    if (typeof window !== 'undefined') {
      if (token) {
        sessionStorage.setItem('candidate_token', token);
      } else {
        sessionStorage.removeItem('candidate_token');
      }
    }
  }

  getCandidateToken(): string | null {
    if (this.candidateToken) return this.candidateToken;
    if (typeof window !== 'undefined') {
      return sessionStorage.getItem('candidate_token');
    }
    return null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit & { useCandidateToken?: boolean; rawBody?: boolean } = {},
  ): Promise<T> {
    const { useCandidateToken, rawBody, ...fetchOptions } = options;
    const token = useCandidateToken ? this.getCandidateToken() : this.getToken();
    const headers: Record<string, string> = {
      ...(rawBody ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...((options.headers as Record<string, string>) || {}),
    };

    const url = `${API_BASE_URL}${endpoint}`;
    if (process.env.NODE_ENV !== 'production') {
      console.log(`API Request: ${fetchOptions.method || 'GET'} ${url}`);
    }

    let response: Response;
    try {
      response = await fetch(url, {
        ...fetchOptions,
        headers,
      });
    } catch (err: any) {
      if (err?.name === 'TypeError') {
        throw new Error(
          `Cannot connect to backend server at ${API_BASE_URL}. Is it running?`,
        );
      }
      throw err;
    }

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({
        detail: `HTTP ${response.status}: ${response.statusText}`,
      }));
      throw new Error(
        formatApiError(errorBody, response.status),
      );
    }

    if (response.status === 204) {
      return {} as T;
    }

    return response.json();
  }

  // Auth
  async signup(email: string, password: string, fullName?: string, company?: string) {
    return this.request('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName, company }),
    });
  }

  async login(email: string, password: string) {
    const response = await this.request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(response.access_token);
    return response;
  }

  logout() {
    this.setToken(null);
    this.setCandidateToken(null);
  }

  // Interviews
  async createInterview(data: { role: string; difficulty: string; num_questions: number; topics?: number[]; custom_questions?: string[] }) {
    return this.request('/interviews/', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getInterviews() {
    return this.request('/interviews/');
  }

  async getInterview(id: number) {
    return this.request(`/interviews/${id}`);
  }

  async getInterviewQuestions(interviewId: number) {
    return this.request(`/interviews/${interviewId}/questions`);
  }

  async addCustomQuestion(interviewId: number, questionText: string) {
    // Body-based — matches the backend Pydantic model (ISSUE-17/24).
    return this.request(`/interviews/${interviewId}/questions`, {
      method: 'POST',
      body: JSON.stringify({ question_text: questionText }),
    });
  }

  async deleteInterview(id: number) {
    return this.request(`/interviews/${id}`, { method: 'DELETE' });
  }

  // Topics
  async getTopics() {
    return this.request('/topics/');
  }

  async createTopic(name: string, description?: string) {
    return this.request('/topics/', {
      method: 'POST',
      body: JSON.stringify({ name, description }),
    });
  }

  async getSampleQuestions(
    topicId: number,
    difficulty: string = 'medium',
    options: { count?: number; regenerate?: boolean } = {},
  ) {
    const qs = new URLSearchParams({
      difficulty,
      count: String(options.count ?? 5),
      regenerate: options.regenerate ? 'true' : 'false',
    }).toString();
    return this.request<{ topic_id: number; topic_name: string; difficulty: string; questions: string[] }>(
      `/interviews/sample-questions/${topicId}?${qs}`,
    );
  }

  // Candidate Interview
  async getInterviewByLink(interviewLink: string) {
    return this.request(`/candidate/interview/${interviewLink}`);
  }

  async registerCandidate(interviewId: number, name: string, email: string) {
    const result = await this.request<{ session_token: string; id: number; interview_id: number; status: string; final_score: number | null; communication_score: number | null; cheating_risk: string; name: string; email: string }>(
      `/candidate/interview/${interviewId}/register`,
      {
        method: 'POST',
        body: JSON.stringify({ name, email }),
      },
    );
    if (result?.session_token) {
      this.setCandidateToken(result.session_token);
    }
    return result;
  }

  async getCandidateQuestions(interviewId: number) {
    return this.request(`/candidate/interview/${interviewId}/questions`, {
      useCandidateToken: true,
    });
  }

  async startCandidateInterview(interviewId: number) {
    return this.request(`/candidate/interview/${interviewId}/start`, {
      method: 'POST',
      useCandidateToken: true,
    });
  }

  async submitAnswerForm(formData: FormData) {
    const token = this.getCandidateToken();
    const url = `${API_BASE_URL}/candidate/answer`;
    const response = await fetch(url, {
      method: 'POST',
      body: formData,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) {
      const errorBody = await response
        .json()
        .catch(() => ({ detail: `HTTP ${response.status}` }));
      throw new Error(errorBody.detail || `Submit failed (${response.status})`);
    }
    return response.json();
  }

  async completeInterview(interviewId: number) {
    return this.request(`/candidate/interview/${interviewId}/complete`, {
      method: 'POST',
      useCandidateToken: true,
    });
  }

  // Recruiter - Candidates
  async getCandidates(interviewId: number) {
    return this.request(`/interviews/${interviewId}/candidates`);
  }

  async getCandidateReport(candidateId: number) {
    return this.request(`/candidate/candidate/${candidateId}/report`);
  }

  async transcribeCandidateAnswers(candidateId: number) {
    return this.request(`/candidate/candidate/${candidateId}/transcribe-all`, {
      method: 'POST',
    });
  }

  async evaluateCandidate(candidateId: number) {
    return this.request(`/candidate/candidate/${candidateId}/evaluate`, {
      method: 'POST',
    });
  }

  async getProctoringReport(candidateId: number) {
    return this.request(`/candidate/candidate/${candidateId}/proctoring/report`, {
      method: 'POST',
    });
  }
}

export const api = new ApiService();
