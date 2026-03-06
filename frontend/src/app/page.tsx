import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center">
      <div className="text-center text-white">
        <h1 className="text-5xl font-bold mb-6">AI Interviewer</h1>
        <p className="text-xl text-slate-300 mb-12 max-w-2xl">
          Fully automated AI interview platform. Conduct interviews without human intervention.
        </p>
        <div className="flex gap-6 justify-center">
          <Link 
            href="/recruiter/login"
            className="px-8 py-3 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition"
          >
            Recruiter Login
          </Link>
          <Link 
            href="/interview"
            className="px-8 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg font-semibold transition"
          >
            Take Interview
          </Link>
        </div>
      </div>
    </div>
  );
}
