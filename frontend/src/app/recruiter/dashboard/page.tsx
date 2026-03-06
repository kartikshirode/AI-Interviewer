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
  
  // Create form state
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

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">AI Interviewer - Dashboard</h1>
          <button onClick={handleLogout} className="text-red-600 hover:underline">
            Logout
          </button>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-2xl font-semibold">My Interviews</h2>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            {showCreate ? 'Cancel' : '+ Create Interview'}
          </button>
        </div>

        {showCreate && (
          <div className="bg-white p-6 rounded-lg shadow-md mb-6">
            <h3 className="text-lg font-semibold mb-4">Create New Interview</h3>
            <form onSubmit={handleCreateInterview} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Role</label>
                <input
                  type="text"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  placeholder="e.g., ML Engineer"
                  className="w-full px-3 py-2 border rounded-lg"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Difficulty</label>
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg"
                >
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Number of Questions</label>
                <input
                  type="number"
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(parseInt(e.target.value))}
                  min={1}
                  max={20}
                  className="w-full px-3 py-2 border rounded-lg"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Topics</label>
                <div className="flex flex-wrap gap-2">
                  {topics.map(topic => (
                    <label key={topic.id} className="flex items-center gap-1">
                      <input
                        type="checkbox"
                        checked={selectedTopics.includes(topic.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedTopics([...selectedTopics, topic.id]);
                          } else {
                            setSelectedTopics(selectedTopics.filter(id => id !== topic.id));
                          }
                        }}
                      />
                      {topic.name}
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Custom Questions (Optional)</label>
                {customQuestions.map((q, idx) => (
                  <div key={idx} className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={q}
                      onChange={(e) => {
                        const newQuestions = [...customQuestions];
                        newQuestions[idx] = e.target.value;
                        setCustomQuestions(newQuestions);
                      }}
                      placeholder="Enter custom question..."
                      className="flex-1 px-3 py-2 border rounded-lg"
                    />
                    {customQuestions.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setCustomQuestions(customQuestions.filter((_, i) => i !== idx))}
                        className="text-red-500 hover:text-red-700"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setCustomQuestions([...customQuestions, ''])}
                  className="text-sm text-blue-600 hover:underline"
                >
                  + Add another question
                </button>
              </div>
              <button type="submit" className="bg-green-600 text-white px-6 py-2 rounded-lg hover:bg-green-700">
                Create Interview
              </button>
            </form>
          </div>
        )}

        {interviews.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-slate-500">
            No interviews yet. Create your first interview!
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {interviews.map(interview => (
              <div key={interview.id} className="bg-white p-6 rounded-lg shadow">
                <h3 className="font-semibold text-lg">{interview.role}</h3>
                <p className="text-slate-500 text-sm mb-2">
                  {interview.difficulty} • {interview.num_questions} questions
                </p>
                <p className="text-xs text-slate-400 mb-4">
                  Created: {new Date(interview.created_at).toLocaleDateString()}
                </p>
                <div className="flex flex-col gap-2">
                  <button
                    onClick={() => copyLink(interview.interview_link)}
                    className="text-blue-600 text-sm hover:underline"
                  >
                    Copy Interview Link
                  </button>
                  <Link
                    href={`/recruiter/interview/${interview.id}/candidates`}
                    className="text-green-600 text-sm hover:underline"
                  >
                    View Candidates
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-8">
          <Link href="/" className="text-slate-600 hover:underline">
            ← Back to Home
          </Link>
        </div>
      </main>
    </div>
  );
}
