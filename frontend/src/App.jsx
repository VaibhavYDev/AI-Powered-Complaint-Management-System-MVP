import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import * as api from "./api";
import { reset } from "./store";
import CareLab from "./components/CareLab";
import ComplaintForm from "./components/ComplaintForm";
import Copilot from "./components/Copilot";

export default function App() {
  const dispatch = useDispatch();
  const complaint = useSelector((s) => s.copilot.complaint);
  const [health, setHealth] = useState(null);
  const [view, setView] = useState("complaints");

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ database: "unavailable" }));
  }, []);

  const ok = health?.database === "ok" && health?.groq_configured;

  return (
    <div className="min-h-screen lg:flex lg:h-screen lg:flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center gap-3">
          <span className="rounded-md bg-slate-900 px-2 py-1 text-sm font-bold tracking-tight text-white">AIVOA</span>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-slate-900">Quality Management System</p>
            <p className="text-xs text-slate-500">Customer Complaints · AI-assisted intake</p>
          </div>
        </div>
        <nav className="flex items-center gap-1 rounded-lg bg-slate-100 p-1 text-xs font-medium">
          {[
            ["complaints", "Complaints"],
            ["care", "Care Lab"],
          ].map(([key, label]) => (
            <button
              key={key}
              onClick={() => setView(key)}
              className={`rounded-md px-3 py-1.5 ${
                view === key ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-3 text-xs">
          {health && (
            <span className="flex items-center gap-1.5 text-slate-500" title={health.fallback_reason ?? ""}>
              <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
              {ok ? `${health.active_model}` : health.database !== "ok" ? "Backend unavailable" : "Groq key missing"}
            </span>
          )}
          {complaint && view === "complaints" && (
            <button
              onClick={() => dispatch(reset())}
              className="rounded-md border border-slate-200 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
            >
              New complaint
            </button>
          )}
        </div>
      </header>

      {view === "complaints" ? (
        <main className="flex flex-col gap-4 p-4 lg:grid lg:min-h-0 lg:flex-1 lg:grid-cols-[3fr_2fr]">
          <div className="lg:min-h-0 lg:overflow-y-auto">
            <ComplaintForm />
          </div>
          <div className="h-[75vh] lg:h-auto lg:min-h-0">
            <Copilot />
          </div>
        </main>
      ) : (
        <main className="lg:min-h-0 lg:flex-1 lg:overflow-y-auto">
          <CareLab />
        </main>
      )}
    </div>
  );
}
