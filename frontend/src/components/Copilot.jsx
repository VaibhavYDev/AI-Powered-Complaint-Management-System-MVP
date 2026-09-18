import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { sendMessage, uploadDocument } from "../store";
import { SEVERITY } from "./RiskAssessment";

const SAMPLE =
  "Customer Rahul Sharma reported that Paracetamol 500 mg tablets from batch PCM24031 were chipped and broken inside the blister pack. The complaint was received today. No hospitalization occurred and the sample is available.";

function Message({ m }) {
  if (m.role === "user") {
    return (
      <div className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-slate-800 px-4 py-2.5 text-sm text-white">
        {m.file && <span className="mr-2 rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase">PDF</span>}
        {m.text}
      </div>
    );
  }
  if (m.role === "risk") {
    const sev = SEVERITY[m.risk.severity_class];
    return (
      <div className="max-w-[92%] rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-sm">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[11px] font-semibold tracking-wide text-indigo-700 uppercase">AI-assisted risk assessment</span>
          <span className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ring-1 ${sev.classes}`}>{sev.label}</span>
        </div>
        <p className="text-slate-700">{m.risk.severity_reason}</p>
        <p className="mt-1.5 text-xs text-indigo-600">Full assessment shown in section 5 of the form.</p>
      </div>
    );
  }
  return (
    <div
      className={`max-w-[92%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm ${
        m.role === "error" ? "border border-red-200 bg-red-50 text-red-800" : "bg-slate-100 text-slate-800"
      }`}
    >
      {m.intent && (
        <span className="mr-2 rounded bg-white px-1.5 py-0.5 text-[10px] font-semibold tracking-wide text-indigo-600 uppercase ring-1 ring-indigo-100">
          {m.intent}
        </span>
      )}
      {m.text}
    </div>
  );
}

export default function Copilot() {
  const dispatch = useDispatch();
  const { messages, busy, complaint } = useSelector((s) => s.copilot);
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const bottom = useRef(null);
  const fileInput = useRef(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  const send = () => {
    const value = text.trim();
    if (!value || busy) return;
    dispatch(sendMessage(value));
    setText("");
  };

  const uploadFile = (file) => {
    if (file && !busy) dispatch(uploadDocument(file));
  };

  return (
    <aside
      className={`flex h-full flex-col rounded-xl border bg-white shadow-sm transition-colors ${
        dragging ? "border-indigo-400 bg-indigo-50/40" : "border-slate-200"
      }`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        uploadFile(e.dataTransfer.files[0]);
      }}
    >
      <header className="border-b border-slate-100 px-5 py-4">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-indigo-500" />
          <h2 className="font-semibold text-slate-900">AIVOA Co-pilot</h2>
        </div>
        <p className="mt-0.5 text-xs text-slate-500">Describe the complaint, ask for a correction, or drop a PDF complaint report.</p>
      </header>

      <div className="flex flex-1 flex-col gap-3 overflow-y-auto px-5 py-4">
        {messages.map((m, i) => (
          <Message key={i} m={m} />
        ))}
        {busy && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
            {busy === "uploading" ? "Reading the document and extracting the complaint…" : "Analysing…"}
          </div>
        )}
        <div ref={bottom} />
      </div>

      <footer className="border-t border-slate-100 p-4">
        {messages.length === 1 && (
          <button
            onClick={() => setText(SAMPLE)}
            className="mb-3 rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
          >
            Try a sample complaint
          </button>
        )}
        {complaint && (
          <p className="mb-2 text-xs text-slate-500">
            Working on <span className="font-mono text-slate-700">{complaint.reference}</span> — corrections apply to this complaint.
          </p>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={3}
            placeholder={
              complaint
                ? 'e.g. "Actually change the batch number to PCM24099"'
                : "Describe the complaint or paste the customer's email…"
            }
            className="flex-1 resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none"
          />
          <div className="flex flex-col gap-2">
            <button
              onClick={send}
              disabled={!!busy || !text.trim()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
            >
              Send
            </button>
            <button
              onClick={() => fileInput.current.click()}
              disabled={!!busy}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-40"
            >
              PDF
            </button>
            <input
              ref={fileInput}
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(e) => {
                uploadFile(e.target.files[0]);
                e.target.value = "";
              }}
            />
          </div>
        </div>
      </footer>
    </aside>
  );
}
