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
  
  // Form state
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
    return <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">Loading...</div>;
  }

  if (state === 'not-found') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-center text-white">
          <h1 className="text-3xl font-bold mb-4">Interview Not Found</h1>
          <p className="text-slate-400">This interview link may be invalid or expired.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white">
      {state === 'register' && interview && (
        <div className="flex items-center justify-center min-h-screen">
          <div className="bg-white text-slate-900 p-8 rounded-lg shadow-xl max-w-md w-full">
            <h1 className="text-2xl font-bold mb-2">{interview.role} Interview</h1>
            <p className="text-slate-500 mb-6">
              {interview.num_questions} questions • {interview.difficulty} difficulty
            </p>
            
            <h2 className="text-lg font-semibold mb-4">Enter Your Details</h2>
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1">Full Name</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg"
                  required
                />
              </div>
              <button
                type="submit"
                className="w-full bg-blue-600 text-white py-3 rounded-lg hover:bg-blue-700"
              >
                Continue
              </button>
            </form>
          </div>
        </div>
      )}

      {state === 'permissions' && (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <h1 className="text-2xl font-bold mb-6">Before We Begin</h1>
            {!hasPermission && (
              <div className="bg-red-500/20 text-red-300 p-4 rounded-lg mb-6">
                Camera and microphone access required
              </div>
            )}
            <div className="bg-slate-800 p-6 rounded-lg mb-6 text-left">
              <p className="mb-4 font-semibold">Please ensure:</p>
              <ul className="text-slate-300 space-y-2">
                <li>✓ Camera is connected and working</li>
                <li>✓ Microphone is connected and working</li>
                <li>✓ You're in a quiet environment</li>
                <li>✓ Close other browser tabs</li>
                <li>✓ Stable internet connection</li>
              </ul>
            </div>
            <button
              onClick={checkPermissions}
              className="bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 mr-4"
            >
              Check Permissions
            </button>
            {hasPermission && (
              <button
                onClick={startInterview}
                className="bg-green-600 text-white px-6 py-3 rounded-lg hover:bg-green-700"
              >
                Start Interview
              </button>
            )}
          </div>
        </div>
      )}

      {state === 'ready' && (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <h1 className="text-2xl font-bold mb-4">Ready to Begin</h1>
            <p className="text-slate-400 mb-6">
              You have {questions.length || interview?.num_questions} questions. 
              Each question has 2 minutes limit.
            </p>
            <button
              onClick={startInterview}
              className="bg-green-600 text-white px-8 py-3 rounded-lg hover:bg-green-700 text-lg"
            >
              Start Interview
            </button>
          </div>
        </div>
      )}

      {state === 'interview' && questions.length > 0 && (
        <div className="max-w-6xl mx-auto p-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <div className="flex justify-between items-center mb-6">
                <div className="text-slate-400">
                  Question {currentQuestionIndex + 1} of {questions.length}
                </div>
                <div className={`text-2xl font-bold ${timeLeft < 30 ? 'text-red-500' : 'text-white'}`}>
                  {formatTime(timeLeft)}
                </div>
              </div>

              <div className="bg-slate-800 rounded-lg p-6 mb-6">
                <h2 className="text-xl font-semibold mb-4">{questions[currentQuestionIndex].question_text}</h2>
                
                <textarea
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  placeholder="Type your answer here... (Speech-to-text will be added in Phase 5)"
                  className="w-full h-48 px-4 py-3 bg-slate-700 border border-slate-600 rounded-lg text-white resize-none"
                />
              </div>

              <div className="flex justify-between items-center">
                <div className="text-slate-400 text-sm">
                  Source: {questions[currentQuestionIndex].source}
                </div>
                <div className="flex gap-3">
                  {isRecording && (
                    <div className="flex items-center gap-2 text-red-500">
                      <span className="w-3 h-3 bg-red-500 rounded-full animate-pulse"></span>
                      Recording
                    </div>
                  )}
                  <button
                    onClick={submitAnswer}
                    className="bg-blue-600 text-white px-8 py-3 rounded-lg hover:bg-blue-700"
                  >
                    {currentQuestionIndex < questions.length - 1 ? 'Next Question' : 'Submit Interview'}
                  </button>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <div className="bg-slate-800 rounded-lg p-4">
                <h3 className="text-sm font-semibold mb-2">Camera</h3>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  playsInline
                  className="w-full h-40 object-cover rounded bg-slate-900"
                />
              </div>

              <div className="bg-slate-800 rounded-lg p-4">
                <div className="flex justify-between items-center mb-2">
                  <h3 className="text-sm font-semibold">Screen Share</h3>
                  <button
                    onClick={toggleScreenShare}
                    className={`px-3 py-1 text-xs rounded ${screenSharing ? 'bg-red-600' : 'bg-green-600'}`}
                  >
                    {screenSharing ? 'Stop' : 'Share'}
                  </button>
                </div>
                {screenSharing && (
                  <video
                    ref={screenRef}
                    autoPlay
                    muted
                    className="w-full h-32 object-contain rounded bg-slate-900"
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {state === 'completed' && (
        <div className="flex items-center justify-center min-h-screen">
          <div className="text-center">
            <h1 className="text-3xl font-bold mb-4 text-green-500">Interview Completed!</h1>
            <p className="text-slate-300 mb-6">
              Thank you for completing the interview. Your responses have been recorded.
            </p>
            <p className="text-slate-400">
              The recruiter will review your answers and get back to you.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
