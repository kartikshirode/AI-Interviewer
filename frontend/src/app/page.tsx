'use client';

import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="border-b border-slate-700/50 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-cyan-400 rounded-xl flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="text-xl font-bold text-white">AI Interviewer</span>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex items-center justify-center min-h-[calc(100vh-80px)]">
        <div className="text-center max-w-4xl px-6">
          <div className="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 rounded-full px-4 py-2 mb-8">
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
            <span className="text-sm text-blue-300">100% Free - No Credit Card Required</span>
          </div>
          
          <h1 className="text-5xl md:text-6xl font-bold text-white mb-6 leading-tight">
            Conduct Technical Interviews with{' '}
            <span className="bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
              AI Power
            </span>
          </h1>
          
          <p className="text-xl text-slate-400 mb-12 max-w-2xl mx-auto leading-relaxed">
            Automated interview platform with video recording, speech-to-text transcription, 
            AI evaluation, and proctoring. Completely free forever.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link 
              href="/recruiter/login"
              className="group px-8 py-4 bg-gradient-to-r from-blue-500 to-cyan-500 hover:from-blue-600 hover:to-cyan-600 rounded-xl font-semibold text-lg transition-all transform hover:scale-105 shadow-lg shadow-blue-500/25"
            >
              <span className="flex items-center justify-center gap-2">
                Get Started
                <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              </span>
            </Link>
            <Link 
              href="/interview"
              className="px-8 py-4 bg-slate-800/50 hover:bg-slate-700/50 border border-slate-700 rounded-xl font-semibold text-lg transition-all"
            >
              Take Interview
            </Link>
          </div>
        </div>
      </main>

      {/* Features Section */}
      <section className="border-t border-slate-800 bg-slate-900/50">
        <div className="max-w-6xl mx-auto px-6 py-16">
          <h2 className="text-3xl font-bold text-white text-center mb-12">Everything You Need</h2>
          
          <div className="grid md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-blue-500/30 transition-colors">
              <div className="w-12 h-12 bg-blue-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Video Recording</h3>
              <p className="text-slate-400">Record candidate responses with webcam and screen share for later review.</p>
            </div>

            {/* Feature 2 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-cyan-500/30 transition-colors">
              <div className="w-12 h-12 bg-cyan-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">AI Transcription</h3>
              <p className="text-slate-400">Convert speech to text automatically using local whisper model - 100% free.</p>
            </div>

            {/* Feature 3 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-green-500/30 transition-colors">
              <div className="w-12 h-12 bg-green-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">AI Evaluation</h3>
              <p className="text-slate-400">Get instant scores on correctness, clarity, and depth using Gemini AI.</p>
            </div>

            {/* Feature 4 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-purple-500/30 transition-colors">
              <div className="w-12 h-12 bg-purple-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Smart Proctoring</h3>
              <p className="text-slate-400">Detect tab switches, clipboard usage, and calculate risk scores.</p>
            </div>

            {/* Feature 5 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-orange-500/30 transition-colors">
              <div className="w-12 h-12 bg-orange-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Analytics Dashboard</h3>
              <p className="text-slate-400">View comprehensive reports with scores, feedback, and recommendations.</p>
            </div>

            {/* Feature 6 */}
            <div className="bg-slate-800/50 border border-slate-700/50 rounded-2xl p-6 hover:border-pink-500/30 transition-colors">
              <div className="w-12 h-12 bg-pink-500/20 rounded-xl flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-pink-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">100% Free</h3>
              <p className="text-slate-400">No API costs. Uses local whisper and Gemini free tier forever.</p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-8">
        <div className="max-w-7xl mx-auto px-6 text-center text-slate-500">
          <p>Built with FastAPI + Next.js</p>
        </div>
      </footer>
    </div>
  );
}
