'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function InterviewPage() {
  const router = useRouter();
  const [status, setStatus] = useState<'checking' | 'ready' | 'interview'>('checking');
  const [hasPermission, setHasPermission] = useState(false);

  useEffect(() => {
    checkPermissions();
  }, []);

  const checkPermissions = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      stream.getTracks().forEach(track => track.stop());
      setHasPermission(true);
      setStatus('ready');
    } catch (err) {
      setHasPermission(false);
      setStatus('ready');
    }
  };

  const startInterview = () => {
    if (!hasPermission) {
      alert('Please allow camera and microphone access to proceed');
      return;
    }
    setStatus('interview');
  };

  if (status === 'checking') {
    return <div className="min-h-screen flex items-center justify-center">Checking permissions...</div>;
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center">
      <div className="text-center text-white">
        {status === 'ready' && (
          <>
            <h1 className="text-3xl font-bold mb-4">Interview Setup</h1>
            {!hasPermission && (
              <div className="bg-red-500/20 text-red-300 p-4 rounded-lg mb-6">
                Camera and microphone access required
              </div>
            )}
            <div className="bg-slate-800 p-6 rounded-lg mb-6">
              <p className="mb-4">Before starting:</p>
              <ul className="text-left text-slate-300 space-y-2">
                <li>✓ Allow camera access</li>
                <li>✓ Allow microphone access</li>
                <li>✓ Close other tabs</li>
                <li>✓ Find a quiet place</li>
              </ul>
            </div>
            <button
              onClick={startInterview}
              className="bg-green-600 text-white px-8 py-3 rounded-lg text-lg hover:bg-green-700 transition"
            >
              Start Interview
            </button>
          </>
        )}
        
        {status === 'interview' && (
          <div>
            <h1 className="text-2xl font-bold mb-4">Interview in Progress</h1>
            <div className="bg-slate-800 p-8 rounded-lg">
              <p className="text-slate-400">Interview functionality coming in Phase 3</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
