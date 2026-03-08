const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000/api/v1';

class ApiService {
  private token: string | null = null;

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

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    };

    const url = `${API_BASE_URL}${endpoint}`;
    console.log(`API Request: ${options.method || 'GET'} ${url}`);

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: `HTTP ${response.status}: ${response.statusText}` }));
        throw new Error(error.detail || `Request failed with status ${response.status}`);
      }

      if (response.status === 204) {
        return {} as T;
      }

      return response.json();
    } catch (err: any) {
      if (err.name === 'TypeError' && err.message === 'Failed to fetch') {
        throw new Error('Cannot connect to backend server. Is it running on http://127.0.0.1:8000?');
      }
      throw err;
    }
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
    return this.request(`/interviews/${interviewId}/questions?question_text=${encodeURIComponent(questionText)}`, {
      method: 'POST',
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

  // Candidate Interview
  async getInterviewByLink(interviewLink: string) {
    return this.request(`/candidate/interview/${interviewLink}`);
  }

  async registerCandidate(interviewId: number, name: string, email: string) {
    return this.request(`/candidate/interview/${interviewId}/register`, {
      method: 'POST',
      body: JSON.stringify({ name, email }),
    });
  }

  async getCandidateQuestions(interviewId: number) {
    return this.request(`/candidate/interview/${interviewId}/questions`);
  }

  async startCandidateInterview(interviewId: number, candidateId: number) {
    return this.request(`/candidate/interview/${interviewId}/start?candidate_id=${candidateId}`, {
      method: 'POST',
    });
  }

  async submitAnswer(candidateId: number, questionId: number, transcript: string) {
    return this.request(`/candidate/answer?candidate_id=${candidateId}&question_id=${questionId}`, {
      method: 'POST',
      body: JSON.stringify({ transcript }),
    });
  }

  async completeInterview(interviewId: number, candidateId: number) {
    return this.request(`/candidate/interview/${interviewId}/complete?candidate_id=${candidateId}`, {
      method: 'POST',
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
