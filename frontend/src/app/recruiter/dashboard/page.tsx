'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/services/api';

interface Interview {
  id: number;
  role: string;
  difficulty: string;
  interview_link: string;
  status: string;
  created_at: string;
  num_questions?: number;
}

interface Topic {
  id: number;
  name: string;
  description?: string;
}

export default function RecruiterDashboard() {
  const router = useRouter();
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  
  const [role, setRole] = useState('');
  const [difficulty, setDifficulty] = useState('medium');
  const [numQuestions, setNumQuestions] = useState(5);
  const [selectedTopics, setSelectedTopics] = useState<number[]>([]);
  const [customQuestions, setCustomQuestions] = useState<string[]>(['']);

  useEffect(() => {
    const token = api.getToken();
    if (!token) {
      router.push('/recruiter/login');
      return;
    }
    loadData();
  }, [router]);

  const loadData = async () => {
    try {
      const [interviewsData, topicsData] = await Promise.all([
        api.getInterviews(),
        api.getTopics()
      ]);
      setInterviews(interviewsData as Interview[]);
      setTopics(topicsData as Topic[]);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateInterview = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const filteredCustomQuestions = customQuestions.filter(q => q.trim() !== '');
      await api.createInterview({
        role,
        difficulty,
        num_questions: numQuestions,
        topics: selectedTopics,
        custom_questions: filteredCustomQuestions
      });
      setShowCreate(false);
      setRole('');
      setSelectedTopics([]);
      setCustomQuestions(['']);
      loadData();
    } catch (err: any) {
      alert(err.message);
    }
  };

  const handleLogout = () => {
    api.logout();
    router.push('/');
  };

  const copyLink = (link: string) => {
    navigator.clipboard.writeText(`${window.location.origin}/interview/${link}`);
    alert('Link copied to clipboard!');
  };

  const getDifficultyColor = (difficulty: string) => {
    switch (difficulty) {
      case 'easy': return 'bg-green-500/20 text-green-400';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400';
      case 'hard': return 'bg-red-500/20 text-red-400';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-slate-400">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800/50 border-b border-slate-700/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <Link href="/" className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="text-xl font-bold text-white">AI Interviewer</span>
          </Link>
          <button 
            onClick={handleLogout} 
            className="px-4 py-2 bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg transition flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            Logout
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-8">
          <div>
            <h2 className="text-3xl font-bold text-white">My Interviews</h2>
            <p className="text-slate-400 mt-1">Create and manage your interview sessions</p>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className={`px-6 py-3 rounded-xl font-semibold transition-all transform hover:scale-105 ${
              showCreate 
                ? 'bg-slate-700 text-slate-300 hover:bg-slate-600' 
                : 'bg-gradient-to-r from-blue-500 to-cyan-500 text-white hover:from-blue-600 hover:to-cyan-600 shadow-lg shadow-blue-500/25'
            }`}
          >
            {showCreate ? 'Cancel' : '+ Create Interview'}
          </button>
        </div>

        {/* Create Interview Form */}
        {showCreate && (
          <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 mb-8 animate-in slide-in-from-top-4">
            <h3 className="text-xl font-semibold text-white mb-6">Create New Interview</h3>
            <form onSubmit={handleCreateInterview} className="space-y-6">
              <div className="grid md:grid-cols-3 gap-6">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Role</label>
                  <input
                    type="text"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    placeholder="e.g., ML Engineer"
                    className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Difficulty</label>
                  <select
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  >
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Number of Questions</label>
                  <input
                    type="number"
                    value={numQuestions}
                    onChange={(e) => setNumQuestions(parseInt(e.target.value))}
                    min={1}
                    max={20}
                    className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-3">Select Topics</label>
                <div className="flex flex-wrap gap-2">
                  {topics.map(topic => (
                    <button
                      key={topic.id}
                      type="button"
                      onClick={() => {
                        if (selectedTopics.includes(topic.id)) {
                          setSelectedTopics(selectedTopics.filter(id => id !== topic.id));
                        } else {
                          setSelectedTopics([...selectedTopics, topic.id]);
                        }
                      }}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition ${
                        selectedTopics.includes(topic.id)
                          ? 'bg-blue-500/20 text-blue-400 border border-blue-500/50'
                          : 'bg-slate-700/50 text-slate-400 border border-slate-700 hover:border-slate-600'
                      }`}
                    >
                      {topic.name}
                    </button>
                  ))}
                </div>
              </div>
              
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-3">Custom Questions (Optional)</label>
                <div className="space-y-2">
                  {customQuestions.map((q, idx) => (
                    <div key={idx} className="flex gap-2">
                      <input
                        type="text"
                        value={q}
                        onChange={(e) => {
                          const newQuestions = [...customQuestions];
                          newQuestions[idx] = e.target.value;
                          setCustomQuestions(newQuestions);
                        }}
                        placeholder="Enter custom question..."
                        className="flex-1 px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                      />
                      {customQuestions.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setCustomQuestions(customQuestions.filter((_, i) => i !== idx))}
                          className="p-3 text-slate-400 hover:text-red-400 transition"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  type="button"
                  onClick={() => setCustomQuestions([...customQuestions, ''])}
                  className="mt-3 text-sm text-blue-400 hover:text-blue-300 transition"
                >
                  + Add another question
                </button>
              </div>
              
              <button 
                type="submit" 
                className="w-full py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 text-white font-semibold rounded-xl transition-all transform hover:scale-[1.02] shadow-lg shadow-green-500/25"
              >
                Create Interview
              </button>
            </form>
          </div>
        )}

        {/* Interviews Grid */}
        {interviews.length === 0 ? (
          <div className="bg-slate-800/30 border border-slate-700/50 rounded-2xl p-12 text-center">
            <div className="w-16 h-16 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">No interviews yet</h3>
            <p className="text-slate-400 mb-6">Create your first interview to get started</p>
            <button
              onClick={() => setShowCreate(true)}
              className="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-xl transition"
            >
              Create Interview
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {interviews.map(interview => (
              <div key={interview.id} className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-blue-500/30 transition group">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-semibold text-lg text-white group-hover:text-blue-400 transition">{interview.role}</h3>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${getDifficultyColor(interview.difficulty)}`}>
                    {interview.difficulty}
                  </span>
                </div>
                <p className="text-slate-400 text-sm mb-1">
                  {interview.num_questions || 5} questions
                </p>
                <p className="text-xs text-slate-500 mb-4">
                  Created {new Date(interview.created_at).toLocaleDateString()}
                </p>
                <div className="flex flex-col gap-2 pt-4 border-t border-slate-700/50">
                  <button
                    onClick={() => copyLink(interview.interview_link)}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-lg transition text-sm"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
                    </svg>
                    Copy Link
                  </button>
                  <Link
                    href={`/recruiter/interview/${interview.id}/candidates`}
                    className="flex items-center justify-center gap-2 px-4 py-2 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg transition text-sm"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
                    </svg>
                    View Candidates
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
