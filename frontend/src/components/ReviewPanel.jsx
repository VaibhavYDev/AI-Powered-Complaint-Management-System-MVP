import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import { exportRecord } from "../api";
import { decide, loadHistory } from "../store";

const STATUS = {
  needs_review: { label: "Needs review", classes: "bg-amber-100 text-amber-800 ring-amber-200" },
  approved: { label: "Approved", classes: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
  rejected: { label: "Rejected", classes: "bg-red-100 text-red-800 ring-red-200" },
};

const ACTIONS = {
  extracted: "Extracted by the co-pilot",
  edited: "Edited",
  approved: "Approved",
  rejected: "Rejected",
};

function when(iso) {
  return new Date(iso).toLocaleString();
}

export default function ReviewPanel() {
  const dispatch = useDispatch();
  const { complaint, events, busy } = useSelector((s) => s.copilot);
  const [acknowledge, setAcknowledge] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState(null);
  const [exported, setExported] = useState(null);
  const [showSource, setShowSource] = useState(false);

  const id = complaint?.id;
  const revision = complaint?.revision;

  useEffect(() => {
    if (id) dispatch(loadHistory(id));
    setAcknowledge(false);
    setNote("");
    setError(null);
    setExported(null);
  }, [id, revision, dispatch]);

  if (!complaint) return null;

  const evidence = complaint.evidence ?? {};
  const unsupported = Object.entries(evidence)
    .filter(([, e]) => e.status === "unsupported")
    .map(([path]) => path);
  const status = STATUS[complaint.status] ?? STATUS.needs_review;
  const pending = complaint.status === "needs_review";
  const reviewing = busy === "reviewing";
  const blocked = unsupported.length > 0 && !acknowledge;

  const act = async (action) => {
    setError(null);
    const result = await dispatch(decide({ action, acknowledge, note: note.trim() || null }));
    if (result.error) setError(result.payload ?? result.error.message);
  };

  const runExport = async () => {
    setError(null);
    try {
      setExported(await exportRecord(id));
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <fieldset className="rounded-lg border border-slate-200 bg-slate-50/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">6. Human review</h2>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-500">revision {complaint.revision}</span>
          <span className={`rounded-md px-2 py-1 font-semibold ring-1 ${status.classes}`}>{status.label}</span>
        </div>
      </div>

      <p className="mb-3 text-sm text-slate-600">
        Extracted values are suggestions until approved. Each field above is marked with where it came
        from; anything the source does not support has to be acknowledged before approval.
      </p>

      {unsupported.length > 0 && (
        <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm">
          <p className="font-medium text-red-800">
            {unsupported.length} value{unsupported.length > 1 ? "s are" : " is"} not supported by the source
          </p>
          <ul className="mt-1 list-disc pl-5 text-red-700">
            {unsupported.map((path) => (
              <li key={path}>{path.replace(".", " · ").replace(/_/g, " ")}</li>
            ))}
          </ul>
          {pending && (
            <label className="mt-2 flex items-start gap-2 text-red-900">
              <input
                type="checkbox"
                checked={acknowledge}
                onChange={(e) => setAcknowledge(e.target.checked)}
                className="mt-0.5"
              />
              <span>I have checked these against the source and accept them.</span>
            </label>
          )}
        </div>
      )}

      {complaint.source_text && (
        <div className="mb-3">
          <button
            onClick={() => setShowSource((v) => !v)}
            className="text-xs font-medium text-indigo-700 hover:underline"
          >
            {showSource ? "Hide" : "Show"} the source this was extracted from
          </button>
          {showSource && (
            <pre className="mt-2 max-h-56 overflow-auto rounded-md border border-slate-200 bg-white p-3 text-xs whitespace-pre-wrap text-slate-700">
              {complaint.source_text}
            </pre>
          )}
        </div>
      )}

      {pending && (
        <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex-1 text-xs text-slate-600">
            Reviewer note (optional)
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={500}
              placeholder="e.g. batch number confirmed against the returned sample"
              className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none"
            />
          </label>
          <div className="flex gap-2">
            <button
              onClick={() => act("approve")}
              disabled={reviewing || blocked}
              title={blocked ? "Acknowledge the unsupported values first" : undefined}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
            >
              {reviewing ? "Working…" : "Approve"}
            </button>
            <button
              onClick={() => act("reject")}
              disabled={reviewing}
              className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {!pending && (
        <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
          <span className="text-slate-600">
            {status.label}
            {complaint.reviewed_at ? ` on ${when(complaint.reviewed_at)}` : ""}. Editing the complaint
            sends it back for review.
          </span>
          {complaint.status === "approved" && (
            <button
              onClick={runExport}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-white"
            >
              Export approved record
            </button>
          )}
        </div>
      )}

      {error && (
        <p className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
      )}

      {exported && (
        <div className="mb-3">
          <p className="mb-1 text-xs font-medium text-emerald-700">
            Mock export of {exported.reference} (approved records only)
          </p>
          <pre className="max-h-48 overflow-auto rounded-md border border-slate-200 bg-white p-3 text-xs text-slate-700">
            {JSON.stringify(exported, null, 2)}
          </pre>
        </div>
      )}

      {events.length > 0 && (
        <div>
          <p className="mb-1 text-xs font-semibold tracking-wide text-slate-500 uppercase">Audit history</p>
          <ol className="space-y-1 text-xs text-slate-600">
            {events.map((event, i) => (
              <li key={i} className="flex flex-wrap gap-x-2">
                <span className="font-medium text-slate-800">{ACTIONS[event.action] ?? event.action}</span>
                <span>revision {event.revision}</span>
                <span>· {when(event.created_at)}</span>
                {event.changed_fields?.length > 0 && (
                  <span>· {event.changed_fields.join(", ").replace(/_/g, " ")}</span>
                )}
                {event.note && <span className="w-full text-slate-500 italic">“{event.note}”</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </fieldset>
  );
}
