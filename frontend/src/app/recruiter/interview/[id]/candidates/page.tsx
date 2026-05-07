'use client';

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { api } from '@/services/api';

type Band = 'top_30' | 'middle' | 'bottom_30' | 'insufficient_data';

interface Candidate {
  id: number;
  name: string;
  email: string;
  status: string;
  final_score: number | null;
  communication_score: number | null;
  cheating_risk: string;
  band?: Band | null;
  cohort_size?: number | null;
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
      case 'high': return 'bg-red-500/20 text-red-400 border border-red-500/30';
      case 'medium': return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30';
      default: return 'bg-green-500/20 text-green-400 border border-green-500/30';
    }
  };

  // Phase 0.3: render percentile bands as the headline; raw scores are
  // not the primary signal a recruiter should anchor on.
  const renderBand = (band?: Band | null, cohortSize?: number | null) => {
    const cohortNote = cohortSize != null ? `n=${cohortSize}` : '';
    if (!band || band === 'insufficient_data') {
      return (
        <span className="px-3 py-1 rounded-full text-xs font-medium bg-slate-700/50 text-slate-400 border border-slate-600/40">
          Insufficient data {cohortNote}
        </span>
      );
    }
    const styles: Record<Band, string> = {
      top_30: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
      middle: 'bg-slate-500/20 text-slate-300 border-slate-500/40',
      bottom_30: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
      insufficient_data: 'bg-slate-700/50 text-slate-400 border-slate-600/40',
    };
    const labels: Record<Band, string> = {
      top_30: 'Top 30%',
      middle: 'Middle',
      bottom_30: 'Bottom 30%',
      insufficient_data: 'Insufficient data',
    };
    return (
      <span className={`px-3 py-1 rounded-full text-xs font-medium border ${styles[band]}`}>
        {labels[band]} {cohortNote && <span className="ml-1 opacity-60">({cohortNote})</span>}
      </span>
    );
  };

  // Plain text color for places where the chip background would clash with
  // the surrounding card (e.g. the big number on the score card).
  const getRiskTextColor = (risk: string) => {
    switch (risk) {
      case 'high': return 'text-red-400';
      case 'medium': return 'text-yellow-400';
      default: return 'text-green-400';
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return 'bg-green-500/20 text-green-400 border border-green-500/30';
      case 'in_progress': return 'bg-blue-500/20 text-blue-400 border border-blue-500/30';
      default: return 'bg-slate-500/20 text-slate-400 border border-slate-500/30';
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
          <div>
            <div className="flex items-center gap-3">
              <Link href="/recruiter/dashboard" className="text-slate-400 hover:text-white transition">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                </svg>
              </Link>
              <h1 className="text-xl font-bold text-white">{interview?.role} - Candidates</h1>
            </div>
            <p className="text-sm text-slate-400 ml-8">{interview?.difficulty} difficulty</p>
          </div>
          <Link 
            href="/recruiter/dashboard" 
            className="px-4 py-2 bg-slate-700/50 hover:bg-slate-700 text-slate-300 rounded-lg transition flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back
          </Link>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {candidates.length === 0 ? (
          <div className="bg-slate-800/30 border border-slate-700/50 rounded-2xl p-12 text-center">
            <div className="w-16 h-16 bg-slate-700/50 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
            </div>
            <h3 className="text-xl font-semibold text-white mb-2">No candidates yet</h3>
            <p className="text-slate-400">Share the interview link to attract candidates.</p>
          </div>
        ) : (
          <div className="bg-slate-800/30 border border-slate-700/50 rounded-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-800/50 border-b border-slate-700/50">
                  <tr>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Name</th>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Email</th>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Status</th>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Band</th>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Risk</th>
                    <th className="px-6 py-4 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/50">
                  {candidates.map(candidate => (
                    <tr key={candidate.id} className="hover:bg-slate-800/30 transition">
                      <td className="px-6 py-4">
                        <span className="text-white font-medium">{candidate.name}</span>
                      </td>
                      <td className="px-6 py-4 text-slate-400">{candidate.email}</td>
                      <td className="px-6 py-4">
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(candidate.status)}`}>
                          {candidate.status}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {renderBand(candidate.band, candidate.cohort_size)}
                      </td>
                      <td className="px-6 py-4">
                        <span className={`px-3 py-1 rounded-full text-xs font-medium ${getRiskColor(candidate.cheating_risk)}`}>
                          {candidate.cheating_risk}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex gap-2">
                          {candidate.status === 'completed' && (
                            <>
                              <button
                                onClick={() => handleTranscribe(candidate.id)}
                                disabled={processing === candidate.id}
                                className="px-3 py-1.5 bg-blue-500/10 hover:bg-blue-500/20 text-blue-400 rounded-lg text-sm transition disabled:opacity-50"
                              >
                                {processing === candidate.id ? 'Processing...' : 'Transcribe'}
                              </button>
                              <button
                                onClick={() => handleEvaluate(candidate.id)}
                                disabled={processing === candidate.id}
                                className="px-3 py-1.5 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg text-sm transition disabled:opacity-50"
                              >
                                Evaluate
                              </button>
                            </>
                          )}
                          <button
                            onClick={() => handleViewReport(candidate)}
                            className="px-3 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 rounded-lg text-sm transition"
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
          </div>
        )}
      </main>

      {/* Report Modal */}
      {selectedCandidate && report && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800/90 border border-slate-700/50 rounded-2xl max-w-3xl w-full max-h-[90vh] overflow-y-auto">
            <div className="p-6 border-b border-slate-700/50 flex justify-between items-start">
              <div>
                <h2 className="text-2xl font-bold text-white">{report.candidate.name}</h2>
                <p className="text-slate-400">{report.candidate.email}</p>
              </div>
              <button 
                onClick={() => setSelectedCandidate(null)} 
                className="p-2 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Headline: percentile band against the (role, difficulty) cohort.
                  Raw scores are intentionally NOT the headline — they're available
                  in the per-question breakdown below for debugging only. */}
              <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-6 text-center space-y-2">
                <p className="text-sm text-slate-400">Cohort placement</p>
                <div className="flex justify-center">
                  {renderBand(report.band?.band, report.band?.cohort_size)}
                </div>
                {report.band?.band === 'insufficient_data' && (
                  <p className="text-xs text-slate-500">
                    Need at least 10 scored candidates with this role and difficulty
                    before a band can be computed. {report.band?.cohort_size ?? 0} so far.
                  </p>
                )}
              </div>

              {/* Secondary signals — these are intentionally not the headline. */}
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-4 text-center">
                  <p className="text-sm text-slate-400 mb-1">Cheating risk (informational)</p>
                  <p className={`text-2xl font-semibold ${getRiskTextColor(report.scores.cheating_risk)}`}>
                    {report.scores.cheating_risk}
                  </p>
                </div>
                <div className="bg-slate-900/50 border border-slate-700/50 rounded-xl p-4 text-center">
                  <p className="text-sm text-slate-400 mb-1">Questions answered</p>
                  <p className="text-2xl font-semibold text-slate-200">
                    {report.answered_questions ?? 0} / {report.total_questions ?? 0}
                  </p>
                </div>
              </div>

              {/* Topic Scores */}
              {report.topic_scores && Object.keys(report.topic_scores).length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-slate-400 mb-3">Topic Scores</h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(report.topic_scores).map(([topic, score]: [string, any]) => (
                      <span key={topic} className="px-4 py-2 bg-slate-700/50 border border-slate-600/50 rounded-lg text-white">
                        <span className="text-slate-400">{topic}:</span> {score}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Question Evaluations — Phase 1: rubric-anchored. Each
                  question shows the chosen 0-4 anchor, the one-sentence
                  justification, and any concepts the candidate missed.
                  Legacy answers (no rubric on the question, e.g. generated
                  before Phase 1) fall back to the old correctness/clarity/
                  depth display under a "Legacy" badge. */}
              <div>
                <h3 className="text-sm font-medium text-slate-400 mb-3">Question Evaluations</h3>
                <div className="space-y-4">
                  {report.question_evaluations?.map((q: any, idx: number) => {
                    const rubricScore: number | null = q.rubric_score ?? null;
                    const isLegacy: boolean = !!q.is_legacy_evaluation;
                    return (
                      <div key={idx} className="bg-slate-900/30 border border-slate-700/50 rounded-xl p-4">
                        <div className="flex justify-between items-start gap-3 mb-3">
                          <p className="text-white font-medium flex-1">{q.question_text}</p>
                          <div className="flex gap-2 shrink-0">
                            {isLegacy && (
                              <span className="px-2 py-1 bg-slate-600/30 text-slate-300 rounded text-xs">
                                Legacy
                              </span>
                            )}
                            {q.is_flagged && (
                              <span className="px-2 py-1 bg-red-500/20 text-red-400 rounded text-xs">
                                Flagged
                              </span>
                            )}
                          </div>
                        </div>

                        {/* Rubric-anchored score: the headline number. */}
                        {rubricScore !== null ? (
                          <div className="flex items-baseline gap-2">
                            <span className="text-2xl font-bold text-white">
                              {Number(rubricScore).toFixed(rubricScore % 1 === 0 ? 0 : 2)}
                            </span>
                            <span className="text-sm text-slate-500">/ 4</span>
                            {q.rubric?.anchors?.[String(Math.round(rubricScore))] && !isLegacy && (
                              <span className="text-xs text-slate-400 ml-3 italic">
                                Anchor: {q.rubric.anchors[String(Math.round(rubricScore))]}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="text-sm text-slate-500 italic">Not evaluated.</div>
                        )}

                        {q.rubric_justification && (
                          <p className="mt-2 text-sm text-slate-300">
                            <span className="text-slate-500">Why:</span> {q.rubric_justification}
                          </p>
                        )}

                        {Array.isArray(q.missing_concepts) && q.missing_concepts.length > 0 && (
                          <div className="mt-2">
                            <p className="text-xs text-slate-500 mb-1">Missing concepts</p>
                            <div className="flex flex-wrap gap-1">
                              {q.missing_concepts.map((c: string, i: number) => (
                                <span key={i} className="px-2 py-0.5 bg-amber-500/10 text-amber-300 border border-amber-500/30 rounded text-xs">
                                  {c}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Legacy debug fields — kept available for old answers. */}
                        {isLegacy && (q.correctness != null || q.clarity != null || q.depth != null) && (
                          <details className="mt-3">
                            <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300">Raw legacy scores</summary>
                            <div className="mt-2 flex gap-4 text-xs text-slate-400">
                              <span>Correctness: <span className="text-white">{q.correctness ?? '-'}</span></span>
                              <span>Clarity: <span className="text-white">{q.clarity ?? '-'}</span></span>
                              <span>Depth: <span className="text-white">{q.depth ?? '-'}</span></span>
                            </div>
                          </details>
                        )}

                        {q.transcript && (
                          <details className="mt-3">
                            <summary className="text-sm text-blue-400 cursor-pointer hover:text-blue-300">View Transcript</summary>
                            <p className="text-sm text-slate-400 mt-2 p-3 bg-slate-900/50 rounded-lg">
                              {q.transcript}
                            </p>
                          </details>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
