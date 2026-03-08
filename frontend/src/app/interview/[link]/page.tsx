'use client';

import { useState, useEffect, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { useProctoring } from '@/hooks/useProctoring';

interface Interview {
  id: number;
  role: string;
  difficulty: string;
  num_questions: number;
  status: string;
}

interface Question {
  id: number;
  question_text: string;
  topic_id: number | null;
  source: string;
}

interface Candidate {
  id: number;
  name: string;
  email: string;
  status: string;
}

type InterviewState = 'loading' | 'not-found' | 'register' | 'permissions' | 'ready' | 'interview' | 'completed';

export default function CandidateInterviewPage() {
  const router = useRouter();
  const params = useParams();
  const interviewLink = params.link as string;

  const [state, setState] = useState<InterviewState>('loading');
  const [interview, setInterview] = useState<Interview | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [timeLeft, setTimeLeft] = useState(120);
  const [hasPermission, setHasPermission] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [screenSharing, setScreenSharing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [copied, setCopied] = useState(false);
  
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  const videoRef = useRef<HTMLVideoElement>(null);
  const screenRef = useRef<HTMLVideoElement>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);

  const proctoring = useProctoring(videoRef);

  useEffect(() => {
    loadInterview();
  }, [interviewLink]);

  useEffect(() => {
    if (state === 'interview' && timeLeft > 0) {
      const timer = setInterval(() => setTimeLeft(t => t - 1), 1000);
      return () => clearInterval(timer);
    }
  }, [state, timeLeft]);

  useEffect(() => {
    return () => {
      stopAllMedia();
    };
  }, []);

  const stopAllMedia = () => {
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
    }
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop());
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
    }
  };

  const loadInterview = async () => {
    try {
      const data = await (await fetch(`http://localhost:8000/api/v1/candidate/interview/${interviewLink}`)).json();
      if (data.detail) {
        setState('not-found');
      } else {
        setInterview(data);
        setState('register');
      }
    } catch (err) {
      setState('not-found');
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!interview) return;

    try {
      const candidateData = await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview.id}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email })
      });
      const newCandidate = await candidateData.json();
      setCandidate(newCandidate);
      setState('permissions');
    } catch (err) {
      alert('Registration failed. Please try again.');
    }
  };

  const checkPermissions = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      stream.getTracks().forEach(track => track.stop());
      setHasPermission(true);
      setState('ready');
    } catch (err) {
      setHasPermission(false);
    }
  };

  const startMediaCapture = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      mediaStreamRef.current = stream;
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      mediaRecorderRef.current = new MediaRecorder(stream, { mimeType: 'video/webm' });
      recordedChunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunksRef.current.push(event.data);
        }
      };

      mediaRecorderRef.current.start(1000);
      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start media capture:', err);
    }
  };

  const stopMediaCapture = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleScreenShare = async () => {
    if (screenSharing) {
      if (screenStreamRef.current) {
        screenStreamRef.current.getTracks().forEach(track => track.stop());
        screenStreamRef.current = null;
      }
      setScreenSharing(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getDisplayMedia({ video: true });
        screenStreamRef.current = stream;
        
        if (screenRef.current) {
          screenRef.current.srcObject = stream;
        }

        stream.getVideoTracks()[0].onended = () => {
          setScreenSharing(false);
          screenStreamRef.current = null;
        };

        setScreenSharing(true);
      } catch (err) {
        console.error('Failed to start screen share:', err);
      }
    }
  };

  const startInterview = async () => {
    if (!interview || !candidate) return;

    try {
      await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview.id}/start?candidate_id=${candidate.id}`, {
        method: 'POST'
      });

      const questionsData = await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview.id}/questions`);
      const questionsList = await questionsData.json();
      setQuestions(questionsList);
      
      await startMediaCapture();
      proctoring.startMonitoring();
      
      setTimeLeft(120);
      setState('interview');
    } catch (err) {
      alert('Failed to start interview');
    }
  };

  const submitAnswer = async () => {
    if (!candidate || !questions[currentQuestionIndex]) return;

    try {
      const blob = recordedChunksRef.current.length > 0 
        ? new Blob(recordedChunksRef.current, { type: 'video/webm' })
        : null;
      
      const formData = new FormData();
      formData.append('transcript', transcript);
      if (blob) {
        formData.append('video', blob, `answer_${questions[currentQuestionIndex].id}.webm`);
      }

      await fetch(`http://localhost:8000/api/v1/candidate/answer?candidate_id=${candidate.id}&question_id=${questions[currentQuestionIndex].id}`, {
        method: 'POST',
        body: formData
      });

      recordedChunksRef.current = [];

      if (currentQuestionIndex < questions.length - 1) {
        setCurrentQuestionIndex(i => i + 1);
        setTimeLeft(120);
        setTranscript('');
      } else {
        stopMediaCapture();
        await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview?.id}/complete?candidate_id=${candidate.id}`, {
          method: 'POST'
        });
        setState('completed');
      }
    } catch (err) {
      alert('Failed to submit answer');
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  if (state === 'loading') {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-slate-400">Loading interview...</span>
        </div>
      </div>
    );
  }

  if (state === 'not-found') {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center p-6">
        <div className="text-center max-w-md">
          <div className="w-20 h-20 bg-red-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white mb-4">Interview Not Found</h1>
          <p className="text-slate-400 mb-8">This interview link may be invalid or expired.</p>
          <a href="/" className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 transition">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Go to Home
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {/* Registration */}
      {state === 'register' && interview && (
        <div className="flex items-center justify-center min-h-screen p-6">
          <div className="w-full max-w-md">
            <div className="bg-slate-800/50 border border-slate-700/50 backdrop-blur-sm rounded-2xl p-8">
              <div className="text-center mb-8">
                <div className="w-16 h-16 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                </div>
                <h1 className="text-2xl font-bold mb-2">{interview.role} Interview</h1>
                <p className="text-slate-400">
                  {interview.num_questions} questions • {interview.difficulty} difficulty
                </p>
              </div>
              
              <h2 className="text-lg font-semibold mb-4">Enter Your Details</h2>
              <form onSubmit={handleRegister} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Full Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                    placeholder="John Doe"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                    placeholder="john@example.com"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="w-full py-3 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 font-semibold rounded-xl transition-all transform hover:scale-[1.02]"
                >
                  Continue
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Permissions */}
      {state === 'permissions' && (
        <div className="flex items-center justify-center min-h-screen p-6">
          <div className="w-full max-w-lg text-center">
            <h1 className="text-2xl font-bold mb-6">Before We Begin</h1>
            
            {!hasPermission && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-6 py-4 rounded-xl mb-6">
                Camera and microphone access required
              </div>
            )}
            
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 mb-6 text-left">
              <p className="font-semibold mb-4 text-white">Please ensure:</p>
              <ul className="text-slate-300 space-y-3">
                <li className="flex items-center gap-3">
                  <span className="w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-sm">✓</span>
                  Camera is connected and working
                </li>
                <li className="flex items-center gap-3">
                  <span className="w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-sm">✓</span>
                  Microphone is connected and working
                </li>
                <li className="flex items-center gap-3">
                  <span className="w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-sm">✓</span>
                  You're in a quiet environment
                </li>
                <li className="flex items-center gap-3">
                  <span className="w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-sm">✓</span>
                  Close other browser tabs
                </li>
                <li className="flex items-center gap-3">
                  <span className="w-6 h-6 bg-green-500/20 rounded-full flex items-center justify-center text-green-400 text-sm">✓</span>
                  Stable internet connection
                </li>
              </ul>
            </div>
            
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              <button
                onClick={checkPermissions}
                className="px-6 py-3 bg-slate-700 hover:bg-slate-600 rounded-xl font-semibold transition"
              >
                Check Permissions
              </button>
              {hasPermission && (
                <button
                  onClick={startInterview}
                  className="px-6 py-3 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 rounded-xl font-semibold transition-all transform hover:scale-105"
                >
                  Start Interview
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Ready */}
      {state === 'ready' && (
        <div className="flex items-center justify-center min-h-screen p-6">
          <div className="w-full max-w-lg text-center">
            <div className="w-20 h-20 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-10 h-10 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold mb-4">Ready to Begin</h1>
            <p className="text-slate-400 mb-8">
              You have {questions.length || interview?.num_questions} questions. 
              Each question has 2 minutes limit.
            </p>
            <button
              onClick={startInterview}
              className="px-8 py-4 bg-gradient-to-r from-green-500 to-emerald-500 hover:from-green-600 hover:to-emerald-600 rounded-xl font-semibold text-lg transition-all transform hover:scale-105 shadow-lg shadow-green-500/25"
            >
              Start Interview
            </button>
          </div>
        </div>
      )}

      {/* Interview */}
      {state === 'interview' && questions.length > 0 && (
        <div className="max-w-7xl mx-auto p-4 md:p-6">
          {/* Header */}
          <div className="flex justify-between items-center mb-6 bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
            <div className="flex items-center gap-4">
              <div className="text-slate-400">
                Question <span className="text-white font-semibold">{currentQuestionIndex + 1}</span> of <span className="text-white font-semibold">{questions.length}</span>
              </div>
              {proctoring.riskLevel && (
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                  proctoring.riskLevel === 'low' ? 'bg-green-500/20 text-green-400' :
                  proctoring.riskLevel === 'medium' ? 'bg-yellow-500/20 text-yellow-400' :
                  'bg-red-500/20 text-red-400'
                }`}>
                  Risk: {proctoring.riskLevel}
                </span>
              )}
            </div>
            <div className={`text-3xl font-bold font-mono ${timeLeft < 30 ? 'text-red-500' : timeLeft < 60 ? 'text-yellow-500' : 'text-white'}`}>
              {formatTime(timeLeft)}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Main Content */}
            <div className="lg:col-span-3 space-y-6">
              {/* Question */}
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
                <div className="flex items-center gap-2 text-sm text-slate-500 mb-4">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {questions[currentQuestionIndex].source}
                </div>
                <h2 className="text-xl md:text-2xl font-semibold text-white">{questions[currentQuestionIndex].question_text}</h2>
              </div>

              {/* Answer Input */}
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
                <textarea
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  placeholder="Type your answer here... (Video is being recorded for AI transcription)"
                  className="w-full h-40 md:h-48 px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              {/* Submit */}
              <div className="flex justify-end">
                <button
                  onClick={submitAnswer}
                  className="px-8 py-4 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 rounded-xl font-semibold text-lg transition-all transform hover:scale-105 shadow-lg shadow-blue-500/25"
                >
                  {currentQuestionIndex < questions.length - 1 ? 'Next Question' : 'Submit Interview'}
                </button>
              </div>
            </div>

            {/* Sidebar */}
            <div className="space-y-4">
              {/* Camera */}
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
                <div className="p-3 border-b border-slate-700/50 flex justify-between items-center">
                  <span className="text-sm font-medium">Camera</span>
                  {isRecording && (
                    <span className="flex items-center gap-2 text-red-400 text-xs">
                      <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                      REC
                    </span>
                  )}
                </div>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full h-40 object-cover"
                />
              </div>

              {/* Screen Share */}
              <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
                <div className="p-3 border-b border-slate-700/50 flex justify-between items-center">
                  <span className="text-sm font-medium">Screen Share</span>
                  <button
                    onClick={toggleScreenShare}
                    className={`px-3 py-1 text-xs rounded-lg transition ${
                      screenSharing 
                        ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' 
                        : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                    }`}
                  >
                    {screenSharing ? 'Stop' : 'Share'}
                  </button>
                </div>
                {screenSharing ? (
                  <video
                    ref={screenRef}
                    autoPlay
                    muted
                    className="w-full h-32 object-contain"
                  />
                ) : (
                  <div className="w-full h-32 bg-slate-900/50 flex items-center justify-center text-slate-500 text-sm">
                    Not sharing
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Completed */}
      {state === 'completed' && (
        <div className="flex items-center justify-center min-h-screen p-6">
          <div className="w-full max-w-lg text-center">
            <div className="w-24 h-24 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-12 h-12 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h1 className="text-3xl font-bold mb-4 text-green-400">Interview Completed!</h1>
            <p className="text-slate-300 mb-4">
              Thank you for completing the interview. Your responses have been recorded.
            </p>
            <p className="text-slate-500">
              The recruiter will review your answers and get back to you.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
