'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/services/api';

interface Candidate {
  id: number;
  name: string;
  email: string;
  status: string;
  final_score: number | null;
  communication_score: number | null;
  cheating_risk: string;
}

interface Interview {
  id: number;
  role: string;
  difficulty: string;
}

export default function InterviewCandidatesPage() {
  const router = useRouter();
  const params = useParams();
  const interviewId = parseInt(params.id as string);

  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [interview, setInterview] = useState<Interview | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null);
  const [report, setReport] = useState<any>(null);
  const [processing, setProcessing] = useState<number | null>(null);

  useEffect(() => {
    const token = api.getToken();
    if (!token) {
      router.push('/recruiter/login');
      return;
    }
    loadData();
  }, [router, interviewId]);

  const loadData = async () => {
    try {
      const [interviewData, candidatesData] = await Promise.all([
        api.getInterview(interviewId),
        api.getCandidates(interviewId)
      ]);
      setInterview(interviewData as Interview);
      setCandidates(candidatesData as Candidate[]);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleViewReport = async (candidate: Candidate) => {
    setSelectedCandidate(candidate);
    try {
      const reportData = await api.getCandidateReport(candidate.id);
      setReport(reportData);
    } catch (err) {
      alert('Failed to load report');
    }
  };

  const handleTranscribe = async (candidateId: number) => {
    setProcessing(candidateId);
    try {
      await api.transcribeCandidateAnswers(candidateId);
      alert('Transcription completed');
      loadData();
    } catch (err) {
      alert('Transcription failed');
    } finally {
      setProcessing(null);
    }
  };

  const handleEvaluate = async (candidateId: number) => {
    setProcessing(candidateId);
    try {
      await api.evaluateCandidate(candidateId);
      await api.getProctoringReport(candidateId);
      alert('Evaluation completed');
      loadData();
    } catch (err) {
      alert('Evaluation failed');
    } finally {
      setProcessing(null);
    }
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-600';
      case 'medium': return 'text-yellow-600';
      default: return 'text-green-600';
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center">Loading...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 py-4 flex justify-between items-center">
          <div>
            <h1 className="text-xl font-bold">{interview?.role} - Candidates</h1>
            <p className="text-sm text-slate-500">{interview?.difficulty} difficulty</p>
          </div>
          <Link href="/recruiter/dashboard" className="text-blue-600 hover:underline">
            Back to Dashboard
          </Link>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-8">
        {candidates.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-8 text-center text-slate-500">
            No candidates yet. Share the interview link to attract candidates.
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Name</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Email</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Score</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Risk</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {candidates.map(candidate => (
                  <tr key={candidate.id}>
                    <td className="px-6 py-4">{candidate.name}</td>
                    <td className="px-6 py-4 text-slate-500">{candidate.email}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 text-xs rounded ${
                        candidate.status === 'completed' ? 'bg-green-100 text-green-800' :
                        candidate.status === 'in_progress' ? 'bg-blue-100 text-blue-800' :
                        'bg-gray-100 text-gray-800'
                      }`}>
                        {candidate.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-semibold">
                      {candidate.final_score ? candidate.final_score.toFixed(1) : '-'}
                    </td>
                    <td className={`px-6 py-4 font-semibold ${getRiskColor(candidate.cheating_risk)}`}>
                      {candidate.cheating_risk}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        {candidate.status === 'completed' && (
                          <>
                            <button
                              onClick={() => handleTranscribe(candidate.id)}
                              disabled={processing === candidate.id}
                              className="text-blue-600 text-sm hover:underline disabled:opacity-50"
                            >
                              Transcribe
                            </button>
                            <button
                              onClick={() => handleEvaluate(candidate.id)}
                              disabled={processing === candidate.id}
                              className="text-green-600 text-sm hover:underline disabled:opacity-50"
                            >
                              Evaluate
                            </button>
                          </>
                        )}
                        <button
                          onClick={() => handleViewReport(candidate)}
                          className="text-purple-600 text-sm hover:underline"
                        >
                          View Report
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {selectedCandidate && report && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4">
            <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
              <div className="p-6">
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <h2 className="text-2xl font-bold">{report.candidate.name}</h2>
                    <p className="text-slate-500">{report.candidate.email}</p>
                  </div>
                  <button onClick={() => setSelectedCandidate(null)} className="text-slate-400 hover:text-slate-600">
                    ✕
                  </button>
                </div>

                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-slate-50 p-4 rounded-lg text-center">
                    <p className="text-sm text-slate-500">Final Score</p>
                    <p className="text-3xl font-bold text-blue-600">{report.scores.final_score?.toFixed(1) || '-'}</p>
                  </div>
                  <div className="bg-slate-50 p-4 rounded-lg text-center">
                    <p className="text-sm text-slate-500">Communication</p>
                    <p className="text-3xl font-bold text-green-600">{report.scores.communication_score?.toFixed(1) || '-'}</p>
                  </div>
                  <div className="bg-slate-50 p-4 rounded-lg text-center">
                    <p className="text-sm text-slate-500">Cheating Risk</p>
                    <p className={`text-3xl font-bold ${getRiskColor(report.scores.cheating_risk)}`}>
                      {report.scores.cheating_risk}
                    </p>
                  </div>
                </div>

                {report.topic_scores && Object.keys(report.topic_scores).length > 0 && (
                  <div className="mb-6">
                    <h3 className="font-semibold mb-2">Topic Scores</h3>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(report.topic_scores).map(([topic, score]: [string, any]) => (
                        <span key={topic} className="bg-slate-100 px-3 py-1 rounded">
                          {topic}: {score}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                <div>
                  <h3 className="font-semibold mb-2">Question Evaluations</h3>
                  <div className="space-y-3">
                    {report.question_evaluations.map((q: any, idx: number) => (
                      <div key={idx} className="border rounded p-3">
                        <p className="font-medium text-sm">{q.question_text}</p>
                        <div className="flex gap-4 mt-2 text-sm text-slate-500">
                          <span>Correctness: {q.correctness || '-'}</span>
                          <span>Clarity: {q.clarity || '-'}</span>
                          <span>Depth: {q.depth || '-'}</span>
                        </div>
                        {q.is_flagged && (
                          <div className="mt-2 text-xs text-red-600">
                            Flagged: {q.flag_reason}
                          </div>
                        )}
                        <div className="mt-2">
                          <details>
                            <summary className="text-xs text-blue-600 cursor-pointer">View Transcript</summary>
                            <p className="text-sm text-slate-600 mt-1 p-2 bg-slate-50 rounded">
                              {q.transcript || 'No transcript available'}
                            </p>
                          </details>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
