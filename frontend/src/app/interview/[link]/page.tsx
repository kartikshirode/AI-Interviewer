'use client';

import { useState, useEffect, useRef } from 'react';
import { useParams } from 'next/navigation';
import { useProctoring } from '@/hooks/useProctoring';
import { useSystemCheck } from '@/hooks/useSystemCheck';
import { useVoiceVerification } from '@/hooks/useVoiceVerification';
import { useVoiceInterview } from '@/hooks/useVoiceInterview';

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

type InterviewState = 'loading' | 'not-found' | 'register' | 'system-check' | 'voice-verify' | 'ready' | 'interview' | 'completed';

export default function CandidateInterviewPage() {
  const params = useParams();
  const interviewLink = params.link as string;

  const [state, setState] = useState<InterviewState>('loading');
  const [interview, setInterview] = useState<Interview | null>(null);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [timeLeft, setTimeLeft] = useState(120);
  const [submitting, setSubmitting] = useState(false);
  
  const [screenSharing, setScreenSharing] = useState(false);
  
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  const localVideoRef = useRef<HTMLVideoElement>(null);
  const screenVideoRef = useRef<HTMLVideoElement>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const screenStreamRef = useRef<MediaStream | null>(null);

  const proctoring = useProctoring(localVideoRef);
  const systemCheck = useSystemCheck();
  const voiceVerify = useVoiceVerification();
  const voiceInterview = useVoiceInterview();

  useEffect(() => {
    loadInterview();
  }, [interviewLink]);

  useEffect(() => {
    if (state === 'interview' && timeLeft > 0) {
      const timer = setInterval(() => setTimeLeft(t => t - 1), 1000);
      return () => clearInterval(timer);
    }
    if (state === 'interview' && timeLeft === 0 && !submitting) {
      submitAnswer();
    }
  }, [state, timeLeft]);

  useEffect(() => {
    return () => {
      stopAllMedia();
    };
  }, []);

  const stopAllMedia = () => {
    voiceInterview.stopSpeaking();
    voiceInterview.stopAnswer();
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach(track => track.stop());
    }
    if (screenStreamRef.current) {
      screenStreamRef.current.getTracks().forEach(track => track.stop());
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
      setState('system-check');
    } catch (err) {
      alert('Registration failed. Please try again.');
    }
  };

  const handleSystemCheckComplete = async () => {
    if (!systemCheck.canProceed()) return;
    setState('voice-verify');
  };

  const handleVoiceVerifyComplete = async () => {
    if (voiceVerify.state.status !== 'verified') {
      alert('Please record and play back your voice to verify');
      return;
    }
    
    if (!interview || !candidate) return;

    try {
      const questionsData = await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview.id}/questions`);
      const questionsList = await questionsData.json();
      setQuestions(questionsList);
      
      await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview.id}/start?candidate_id=${candidate.id}`, {
        method: 'POST'
      });

      await startMediaCapture();
      proctoring.startMonitoring();
      
      setTimeLeft(120);
      setState('interview');

      // Start speaking the first question after a brief delay
      setTimeout(async () => {
        voiceInterview.resetTranscript();
        await voiceInterview.speakQuestion(questionsList[0].question_text);
        // Start both recognition + background audio recording
        voiceInterview.startAnswer();
      }, 500);
    } catch (err) {
      console.error('Failed to start interview:', err);
      alert('Failed to start interview. Please try again.');
    }
  };

  const startMediaCapture = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        video: true,
        audio: false
      });
      mediaStreamRef.current = stream;
      
      if (localVideoRef.current) {
        localVideoRef.current.srcObject = stream;
        await localVideoRef.current.play();
      }
      
      await startScreenShare();
      
    } catch (err) {
      console.error('Failed to start media capture:', err);
    }
  };

  const startScreenShare = async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ 
        video: true 
      });
      screenStreamRef.current = stream;
      
      if (screenVideoRef.current) {
        screenVideoRef.current.srcObject = stream;
        await screenVideoRef.current.play();
      }

      stream.getVideoTracks()[0].onended = () => {
        setScreenSharing(false);
      };

      setScreenSharing(true);
    } catch (err) {
      console.error('Failed to start screen share:', err);
    }
  };

  const submitAnswer = async () => {
    if (!candidate || !questions[currentQuestionIndex] || submitting) return;
    setSubmitting(true);

    try {
      voiceInterview.stopSpeaking();

      // Stop both recognition + recording, get the audio blob
      const audioBlob = voiceInterview.stopAnswer();

      const formData = new FormData();
      formData.append('candidate_id', candidate.id.toString());
      formData.append('question_id', questions[currentQuestionIndex].id.toString());
      formData.append('transcript', voiceInterview.transcript || 'No answer provided');

      // Attach recorded audio for backend Whisper processing
      if (audioBlob && audioBlob.size > 0) {
        formData.append('audio', audioBlob, 'answer.webm');
      }

      await fetch(`http://localhost:8000/api/v1/candidate/answer`, {
        method: 'POST',
        body: formData
      });

      if (currentQuestionIndex < questions.length - 1) {
        const nextIndex = currentQuestionIndex + 1;
        setCurrentQuestionIndex(nextIndex);
        setTimeLeft(120);

        // Start next question
        voiceInterview.resetTranscript();
        await voiceInterview.speakQuestion(questions[nextIndex].question_text);
        voiceInterview.startAnswer();
      } else {
        stopAllMedia();
        await fetch(`http://localhost:8000/api/v1/candidate/interview/${interview?.id}/complete?candidate_id=${candidate.id}`, {
          method: 'POST'
        });
        setState('completed');
      }
    } catch (err) {
      alert('Failed to submit answer');
    } finally {
      setSubmitting(false);
    }
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  // ========== RENDER STATES ==========

  if (state === 'loading') {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-4 border-cyan-500 border-t-transparent rounded-full animate-spin"></div>
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
          <a href="/" className="inline-flex items-center gap-2 text-cyan-400 hover:text-cyan-300 transition">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Go to Home
          </a>
        </div>
      </div>
    );
  }

  // ========== REGISTRATION ==========
  if (state === 'register' && interview) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-6">
        <div className="w-full max-w-md">
          <div className="bg-slate-800/50 border border-slate-700/50 backdrop-blur-sm rounded-2xl p-8">
            <div className="text-center mb-8">
              <div className="w-16 h-16 bg-gradient-to-br from-cyan-500 to-blue-500 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              <h1 className="text-2xl font-bold mb-2">{interview.role}</h1>
              <p className="text-slate-400 mb-4">
                {interview.num_questions} questions • {interview.difficulty} difficulty
              </p>
              <div className="inline-flex items-center gap-2 px-4 py-2 bg-cyan-500/20 text-cyan-400 rounded-full text-sm">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                </svg>
                Voice-based AI Interview
              </div>
            </div>
            
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-cyan-500 focus:border-transparent outline-none"
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
                  className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-cyan-500 focus:border-transparent outline-none"
                  placeholder="john@example.com"
                  required
                />
              </div>
              <button
                type="submit"
                className="w-full py-3 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 font-semibold rounded-xl transition-all transform hover:scale-[1.02]"
              >
                Continue to System Check
              </button>
            </form>
          </div>
        </div>
      </div>
    );
  }

  // ========== SYSTEM CHECK ==========
  if (state === 'system-check') {
    const { speedTest, permissions, deviceInfo, runSpeedTest, requestCamera, requestMicrophone, requestScreen, canProceed, getPermissionSummary } = systemCheck;
    const permSummary = getPermissionSummary();

    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">System Check</h1>
            <p className="text-slate-400">Verify your device is ready for the voice interview</p>
          </div>

          <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-400">Device: {deviceInfo.deviceType}</span>
              <span className="text-slate-400">Browser: {deviceInfo.browser}</span>
              <span className="text-slate-400">OS: {deviceInfo.os}</span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {(['camera', 'microphone', 'screen'] as const).map((perm) => {
              const status = permissions[perm];
              const requestFn = perm === 'camera' ? requestCamera : perm === 'microphone' ? requestMicrophone : requestScreen;
              const iconColor = status === 'granted' ? 'text-green-400' : status === 'denied' ? 'text-red-400' : 'text-slate-400';
              return (
                <div key={perm} className={`bg-slate-800/30 border rounded-xl p-5 transition ${
                  status === 'granted' ? 'border-green-500/50' : 
                  status === 'denied' ? 'border-red-500/50' : 'border-slate-700/50'
                }`}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        status === 'granted' ? 'bg-green-500/20' : 
                        status === 'denied' ? 'bg-red-500/20' : 'bg-slate-700/50'
                      }`}>
                        {perm === 'camera' && <svg className={`w-5 h-5 ${iconColor}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>}
                        {perm === 'microphone' && <svg className={`w-5 h-5 ${iconColor}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" /></svg>}
                        {perm === 'screen' && <svg className={`w-5 h-5 ${iconColor}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>}
                      </div>
                      <div>
                        <div className="text-white font-medium capitalize">{perm === 'screen' ? 'Screen Share' : perm}</div>
                        {status !== 'not-requested' && (
                          <div className={`text-xs ${status === 'granted' ? 'text-green-400' : 'text-red-400'}`}>
                            {status === 'granted' ? '✓ Ready' : '✗ Denied'}
                          </div>
                        )}
                      </div>
                    </div>
                    {status === 'not-requested' && (
                      <button onClick={requestFn} className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm font-medium transition">
                        Allow
                      </button>
                    )}
                    {status === 'granted' && (
                      <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    {status === 'denied' && (
                      <button onClick={requestFn} className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg text-sm font-medium transition">
                        Retry
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-white font-medium flex items-center gap-2">
                <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Internet Speed Test
              </h3>
              {speedTest.status === 'idle' && (
                <button onClick={runSpeedTest} className="px-4 py-2 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-400 rounded-lg text-sm transition">
                  Run Test
                </button>
              )}
              {speedTest.status === 'testing' && (
                <div className="flex items-center gap-2 text-cyan-400">
                  <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                  <span className="text-sm">Testing...</span>
                </div>
              )}
            </div>
            
            {speedTest.status === 'complete' && (
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 bg-slate-900/50 rounded-lg">
                  <div className="text-2xl font-bold text-green-400">{speedTest.download} Mbps</div>
                  <div className="text-xs text-slate-400">Download</div>
                </div>
                <div className="text-center p-3 bg-slate-900/50 rounded-lg">
                  <div className="text-2xl font-bold text-blue-400">{speedTest.upload} Mbps</div>
                  <div className="text-xs text-slate-400">Upload</div>
                </div>
                <div className="text-center p-3 bg-slate-900/50 rounded-lg">
                  <div className="text-2xl font-bold text-yellow-400">{speedTest.latency} ms</div>
                  <div className="text-xs text-slate-400">Latency</div>
                </div>
              </div>
            )}
          </div>

          <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${canProceed() ? 'bg-green-400' : 'bg-yellow-400'}`}></div>
                <span className="text-slate-300">
                  {canProceed() ? 'All systems ready!' : 'Complete all checks to proceed'}
                </span>
              </div>
              <span className="text-sm text-slate-400">
                Permissions: {permSummary.granted}/{permSummary.total}
              </span>
            </div>
          </div>

          <div className="flex gap-4">
            <button onClick={() => setState('register')} className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-xl transition">
              Back
            </button>
            <button
              onClick={handleSystemCheckComplete}
              disabled={!canProceed()}
              className={`flex-1 py-3 font-semibold rounded-xl transition-all transform hover:scale-[1.02] ${
                canProceed()
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 text-white shadow-lg shadow-cyan-500/25'
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              }`}
            >
              Next: Voice Verification
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ========== VOICE VERIFICATION ==========
  if (state === 'voice-verify') {
    const { state: voiceState, verificationPhrase, startRecording, stopRecording, playRecording, reset, verifyAndProceed } = voiceVerify;

    const handleVerify = () => {
      if (verifyAndProceed()) {
        handleVoiceVerifyComplete();
      }
    };

    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
        <div className="max-w-2xl mx-auto">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-white mb-2">Voice Verification</h1>
            <p className="text-slate-400">Speak the phrase below to verify your microphone</p>
          </div>

          <div className="bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/30 rounded-2xl p-8 mb-8">
            <div className="text-center">
              <p className="text-slate-400 text-sm mb-4">Please speak this exact phrase:</p>
              <p className="text-2xl font-semibold text-white mb-4">"{verificationPhrase}"</p>
              <p className="text-slate-500 text-sm">Make sure your microphone is working and you're in a quiet environment</p>
            </div>
          </div>

          {/* Audio Level Indicator */}
          <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-white font-medium">Microphone Level</span>
              <span className="text-slate-400">{voiceState.audioLevel}%</span>
            </div>
            <div className="h-4 bg-slate-700/50 rounded-full overflow-hidden">
              <div 
                className={`h-full transition-all duration-100 ${
                  voiceState.audioLevel > 50 ? 'bg-green-500' : 
                  voiceState.audioLevel > 20 ? 'bg-yellow-500' : 'bg-slate-500'
                }`}
                style={{ width: `${voiceState.audioLevel}%` }}
              ></div>
            </div>
          </div>

          {/* Recording Status */}
          <div className="bg-slate-800/30 border border-slate-700/50 rounded-xl p-6 mb-6">
            <div className="flex items-center justify-center gap-4">
              {voiceState.status === 'idle' && (
                <button
                  onClick={startRecording}
                  className="px-8 py-4 bg-red-500 hover:bg-red-600 text-white font-semibold rounded-xl transition-all"
                >
                  <span className="flex items-center gap-2">
                    <span className="w-3 h-3 bg-white rounded-full"></span>
                    Start Recording
                  </span>
                </button>
              )}

              {voiceState.status === 'recording' && (
                <div className="text-center">
                  <div className="flex items-center justify-center gap-2 text-red-400 mb-4">
                    <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                    Recording...
                  </div>
                  <button
                    onClick={stopRecording}
                    className="px-8 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-xl transition-all"
                  >
                    Stop Recording
                  </button>
                </div>
              )}

              {voiceState.status === 'ready' && (
                <div className="flex items-center gap-4">
                  <button
                    onClick={playRecording}
                    className="px-6 py-3 bg-blue-500 hover:bg-blue-600 text-white font-semibold rounded-xl transition-all"
                  >
                    ▶ Play Recording
                  </button>
                  <button
                    onClick={reset}
                    className="px-6 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-xl transition-all"
                  >
                    Re-record
                  </button>
                </div>
              )}

              {voiceState.status === 'playing' && (
                <div className="flex items-center gap-2 text-cyan-400">
                  <div className="w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></div>
                  Playing...
                </div>
              )}

              {voiceState.status === 'verified' && (
                <div className="flex items-center gap-2 text-green-400">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  Voice Verified!
                </div>
              )}
            </div>
          </div>

          {voiceState.error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-xl mb-6 text-center">
              {voiceState.error}
            </div>
          )}

          <div className="flex gap-4">
            <button onClick={() => setState('system-check')} className="flex-1 py-3 bg-slate-700 hover:bg-slate-600 text-white font-semibold rounded-xl transition">
              Back
            </button>
            <button
              onClick={handleVerify}
              disabled={voiceState.status !== 'verified'}
              className={`flex-1 py-3 font-semibold rounded-xl transition-all transform hover:scale-[1.02] ${
                voiceState.status === 'verified'
                  ? 'bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 text-white shadow-lg shadow-cyan-500/25'
                  : 'bg-slate-700 text-slate-500 cursor-not-allowed'
              }`}
            >
              Start Interview
            </button>
          </div>

          {voiceState.status !== 'verified' && (
            <p className="text-center text-yellow-400 text-sm mt-4">
              Please record and verify your voice to proceed
            </p>
          )}
        </div>
      </div>
    );
  }

  // ========== INTERVIEW ==========
  if (state === 'interview' && questions.length > 0) {
    return (
      <div className="max-w-7xl mx-auto p-4 md:p-6">
        <div className="flex justify-between items-center mb-6 bg-slate-800/50 border border-slate-700/50 rounded-xl p-4">
          <div className="flex items-center gap-4">
            <div className="text-slate-400">
              Question <span className="text-white font-semibold">{currentQuestionIndex + 1}</span> of <span className="text-white font-semibold">{questions.length}</span>
            </div>
            <div className="flex items-center gap-2">
              {voiceInterview.isSpeaking && (
                <span className="px-3 py-1 rounded-full text-xs font-medium bg-cyan-500/20 text-cyan-400 flex items-center gap-1">
                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse"></span>
                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" style={{animationDelay: '0.2s'}}></span>
                  <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" style={{animationDelay: '0.4s'}}></span>
                  <span className="ml-1">AI Speaking</span>
                </span>
              )}
              {voiceInterview.isListening && (
                <span className="px-3 py-1 rounded-full text-xs font-medium bg-red-500/20 text-red-400 flex items-center gap-1">
                  <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse"></span>
                  Listening
                </span>
              )}
              {voiceInterview.isRecording && (
                <span className="px-3 py-1 rounded-full text-xs font-medium bg-orange-500/20 text-orange-400 flex items-center gap-1">
                  <span className="w-2 h-2 bg-orange-500 rounded-full animate-pulse"></span>
                  Recording
                </span>
              )}
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
          <div className="lg:col-span-3 space-y-6">
            {/* Question Card */}
            <div className="bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/30 rounded-2xl p-6">
              <div className="flex items-center gap-2 text-sm text-cyan-400 mb-4">
                {voiceInterview.isSpeaking ? (
                  <>
                    <svg className="w-5 h-5 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    </svg>
                    AI Interviewer Speaking...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    </svg>
                    AI Interviewer Question
                  </>
                )}
              </div>
              <h2 className="text-xl md:text-2xl font-semibold text-white">
                {questions[currentQuestionIndex].question_text}
              </h2>
              <div className="mt-4 text-sm text-slate-400">
                Topic: {questions[currentQuestionIndex].source}
              </div>
            </div>

            {/* Voice Answer / Transcript Area */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                  </svg>
                  Your Voice Answer
                </div>
                {voiceInterview.isListening && (
                  <div className="flex items-center gap-3 text-red-400">
                    <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                    <span className="text-sm">Listening...</span>
                    {voiceInterview.isRecording && (
                      <span className="text-xs text-orange-400 bg-orange-500/10 px-2 py-0.5 rounded-full">Audio recording</span>
                    )}
                  </div>
                )}
              </div>

              <div className="min-h-[150px] p-4 bg-slate-900/50 border border-slate-700 rounded-xl">
                {voiceInterview.transcript || voiceInterview.interimTranscript ? (
                  <p className="text-white leading-relaxed">
                    {voiceInterview.transcript}
                    <span className="text-slate-500 italic">{voiceInterview.interimTranscript}</span>
                  </p>
                ) : (
                  <p className="text-slate-500 italic">
                    {voiceInterview.isSpeaking 
                      ? 'Listen to the question, then speak your answer...'
                      : voiceInterview.isListening 
                        ? 'Start speaking your answer...' 
                        : 'Waiting...'}
                  </p>
                )}
              </div>

              {voiceInterview.error && (
                <div className="mt-3 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2">
                  {voiceInterview.error}
                </div>
              )}
            </div>

            <div className="flex justify-end">
              <button
                onClick={submitAnswer}
                disabled={submitting}
                className={`px-8 py-4 bg-gradient-to-r from-cyan-500 to-blue-500 hover:from-cyan-600 hover:to-blue-600 rounded-xl font-semibold text-lg transition-all transform hover:scale-105 shadow-lg shadow-cyan-500/25 ${
                  submitting ? 'opacity-50 cursor-not-allowed' : ''
                }`}
              >
                {submitting ? 'Submitting...' : currentQuestionIndex < questions.length - 1 ? 'Next Question →' : 'Finish Interview'}
              </button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
              <div className="p-3 border-b border-slate-700/50 flex justify-between items-center">
                <span className="text-sm font-medium">Your Camera</span>
                <span className="flex items-center gap-2 text-green-400 text-xs">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  Live
                </span>
              </div>
              <video
                ref={localVideoRef}
                autoPlay
                muted
                playsInline
                className="w-full h-48 object-cover bg-slate-900"
              />
            </div>

            <div className="bg-slate-800/50 border border-red-500/30 rounded-xl overflow-hidden">
              <div className="p-3 border-b border-slate-700/50 flex justify-between items-center bg-red-500/10">
                <span className="text-sm font-medium text-red-400">Screen Share</span>
                {screenSharing ? (
                  <span className="flex items-center gap-2 text-green-400 text-xs">
                    <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                    Sharing
                  </span>
                ) : (
                  <button
                    onClick={startScreenShare}
                    className="text-xs px-2 py-1 bg-red-500/20 text-red-400 rounded hover:bg-red-500/30 transition"
                  >
                    Share Now
                  </button>
                )}
              </div>
              {screenSharing ? (
                <video
                  ref={screenVideoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full h-40 object-contain bg-slate-900"
                />
              ) : (
                <div className="w-full h-40 bg-slate-900 flex flex-col items-center justify-center text-slate-500">
                  <svg className="w-8 h-8 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <span className="text-sm">Screen not shared</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ========== COMPLETED ==========
  if (state === 'completed') {
    return (
      <div className="flex items-center justify-center min-h-screen p-6">
        <div className="w-full max-w-lg text-center">
          <div className="w-24 h-24 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-6">
            <svg className="w-12 h-12 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold mb-4 text-green-400">Interview Completed!</h1>
          <p className="text-slate-300 mb-4">
            Thank you for completing the voice interview. Your responses have been recorded.
          </p>
          <p className="text-slate-500">
            The recruiter will review your answers and get back to you.
          </p>
        </div>
      </div>
    );
  }

  return null;
}
