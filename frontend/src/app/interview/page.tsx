'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function InterviewPage() {
  const router = useRouter();
  const [interviewLink, setInterviewLink] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!interviewLink.trim()) {
      setError('Please enter an interview link');
      return;
    }
    
    // Extract the link code from the full URL or just use the input
    const link = interviewLink.trim();
    if (link.includes('/interview/')) {
      const parts = link.split('/interview/');
      const code = parts[parts.length - 1];
      router.push(`/interview/${code}`);
    } else {
      router.push(`/interview/${link}`);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-3">
            <div className="w-12 h-12 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center">
              <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="text-2xl font-bold text-white">AI Interviewer</span>
          </Link>
        </div>

        {/* Card */}
        <div className="bg-slate-800/50 border border-slate-700/50 backdrop-blur-sm rounded-2xl p-8">
          <div className="text-center mb-6">
            <div className="w-16 h-16 bg-gradient-to-br from-blue-500/20 to-cyan-500/20 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-2">Enter Interview Link</h1>
            <p className="text-slate-400">
              Paste the interview link shared by the recruiter
            </p>
          </div>

          {error && (
            <div className="bg-red-500/10 border border-red-500/20 text-red-400 px-4 py-3 rounded-xl mb-4">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <input
                type="text"
                value={interviewLink}
                onChange={(e) => {
                  setInterviewLink(e.target.value);
                  setError('');
                }}
                placeholder="https://.../interview/abc123"
                className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition"
              />
            </div>

            <button
              type="submit"
              className="w-full py-3 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 text-white font-semibold rounded-xl transition-all transform hover:scale-[1.02]"
            >
              Start Interview
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-slate-700/50">
            <p className="text-center text-slate-500 text-sm mb-4">
              Don't have an interview link?
            </p>
            <Link
              href="/"
              className="block text-center text-blue-400 hover:text-blue-300 transition"
            >
              ← Back to Home
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
