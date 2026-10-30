import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";

import { exportCare } from "../api";
import { analyseNote, decideCare } from "../store";

// Fictional residents and a fictional care plan. Nothing here is a real person or record.
const SAMPLE_NOTE = `Shift notes, 14 March 2026 — Unit 2.

Frau Anna Keller: while washing, redness appeared at the left heel, about 2 x 3 cm,
skin not broken. Barrier cream applied, heel kept free of pressure. No pain reported.

Herr Josef Brandt: walked to the dining room with his frame unaided. Ate well. No fall.`;

const SAMPLE_PLAN = [
  { resident: "Anna Keller", category: "mobility", body_site: null, instruction: "Assist with transfers" },
  { resident: "Josef Brandt", category: "mobility", body_site: null, instruction: "Walking frame at all times" },
  { resident: "Josef Brandt", category: "nutrition", body_site: null, instruction: "Normal diet, record intake" },
];

const SEVERITY = {
  high: "border-red-300 bg-red-50 text-red-900",
  medium: "border-amber-300 bg-amber-50 text-amber-900",
  low: "border-slate-200 bg-slate-50 text-slate-700",
};

const EVIDENCE = {
  verbatim: { label: "quoted", classes: "text-emerald-700" },
  normalized: { label: "matched", classes: "text-emerald-700" },
  derived: { label: "inferred", classes: "text-slate-500" },
  unsupported: { label: "not in note", classes: "text-red-600" },
};

export default function CareLab() {
  const dispatch = useDispatch();
  const { record, events, busy, error } = useSelector((s) => s.care);
  const [note, setNote] = useState(SAMPLE_NOTE);
  const [acknowledged, setAcknowledged] = useState([]);
  const [reviewNote, setReviewNote] = useState("");
  const [exported, setExported] = useState(null);

  const alerts = record?.alerts ?? [];
  const mustAcknowledge = alerts.filter((a) => a.severity === "high").map((a) => a.key);
  const outstanding = mustAcknowledge.filter((key) => !acknowledged.includes(key));
  const pending = record?.status === "needs_review";

  const analyse = () => {
    setAcknowledged([]);
    setExported(null);
    dispatch(analyseNote({ note, carePlan: SAMPLE_PLAN }));
  };

  const decide = (action) => {
    setExported(null);
    dispatch(decideCare({ action, acknowledged, note: reviewNote.trim() || null }));
  };

  const toggle = (key) =>
    setAcknowledged((current) =>
      current.includes(key) ? current.filter((k) => k !== key) : [...current, key],
    );

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 p-4">
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">Care Documentation Reliability Lab</h1>
        <p className="mt-1 text-sm text-slate-500">
          Evidence-grounded extraction from a caregiver note. An independent case study on
          fictional residents — not a clinical system, and not connected to any care provider.
        </p>

        <label className="mt-4 block text-xs font-medium text-slate-600">
          Caregiver note (synthetic)
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={9}
            className="mt-1 w-full rounded-lg border border-slate-200 px-3 py-2 font-mono text-xs focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none"
          />
        </label>

        <details className="mt-2 text-xs text-slate-600">
          <summary className="cursor-pointer font-medium text-indigo-700">
            Care plan on file ({SAMPLE_PLAN.length} entries)
          </summary>
          <ul className="mt-1 list-disc pl-5">
            {SAMPLE_PLAN.map((entry, i) => (
              <li key={i}>
                {entry.resident} · {entry.category} — {entry.instruction}
              </li>
            ))}
          </ul>
        </details>

        <button
          onClick={analyse}
          disabled={busy || !note.trim()}
          className="mt-3 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-40"
        >
          {busy ? "Analysing…" : "Analyse note"}
        </button>

        {error && (
          <p className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>
        )}
      </section>

      {record && (
        <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold text-slate-900">
              Extracted observations · {record.note.residents.length} resident
              {record.note.residents.length === 1 ? "" : "s"}
            </h2>
            <span className="text-xs text-slate-500">
              revision {record.revision} · {record.status.replace("_", " ")}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-slate-500 uppercase">
                <tr>
                  <th className="py-1 pr-3">Resident</th>
                  <th className="py-1 pr-3">Category</th>
                  <th className="py-1 pr-3">Finding</th>
                  <th className="py-1 pr-3">Site</th>
                  <th className="py-1">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {record.note.observations.map((o, i) => {
                  const source = EVIDENCE[record.evidence[`observations.${i}.finding`]?.status];
                  const excerpt = record.evidence[`observations.${i}.finding`]?.excerpt;
                  return (
                    <tr key={i} className="border-t border-slate-100 align-top">
                      <td className="py-2 pr-3">{o.resident ?? <span className="text-red-600">unattributed</span>}</td>
                      <td className="py-2 pr-3 text-slate-600">{o.category}</td>
                      <td className="py-2 pr-3">{o.finding}</td>
                      <td className="py-2 pr-3 text-slate-600">{o.body_site ?? "—"}</td>
                      <td className="py-2">
                        {source && (
                          <span className={`text-xs font-medium ${source.classes}`} title={excerpt ?? undefined}>
                            {source.label}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {record.note.open_questions.length > 0 && (
            <div className="mt-3 text-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase">The reader abstained on</p>
              <ul className="mt-1 list-disc pl-5 text-slate-700">
                {record.note.open_questions.map((q, i) => (
                  <li key={i}>{q}</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4">
            <p className="mb-2 text-xs font-semibold text-slate-500 uppercase">
              Documentation alerts ({alerts.length})
            </p>
            {alerts.length === 0 ? (
              <p className="text-sm text-slate-500">Nothing to flag against the care plan or the note.</p>
            ) : (
              <ul className="space-y-2">
                {alerts.map((alert) => {
                  const needsTick = alert.severity === "high" && pending;
                  return (
                    <li key={alert.key} className={`rounded-md border px-3 py-2 text-sm ${SEVERITY[alert.severity]}`}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <span className="font-medium">{alert.kind.replace(/_/g, " ")}</span>
                        <span className="text-xs uppercase">{alert.severity}</span>
                      </div>
                      <p className="mt-0.5">{alert.message}</p>
                      {needsTick && (
                        <label className="mt-1 flex items-start gap-2 text-xs">
                          <input
                            type="checkbox"
                            checked={acknowledged.includes(alert.key)}
                            onChange={() => toggle(alert.key)}
                            className="mt-0.5"
                          />
                          <span>I have checked this against the note.</span>
                        </label>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {pending ? (
            <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
              <label className="flex-1 text-xs text-slate-600">
                Reviewer note (optional)
                <input
                  value={reviewNote}
                  onChange={(e) => setReviewNote(e.target.value)}
                  maxLength={500}
                  className="mt-1 w-full rounded-md border border-slate-200 px-3 py-1.5 text-sm focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none"
                />
              </label>
              <div className="flex gap-2">
                <button
                  onClick={() => decide("approve")}
                  disabled={busy || outstanding.length > 0}
                  title={outstanding.length > 0 ? "Acknowledge the high-priority alerts first" : undefined}
                  className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-40"
                >
                  Approve
                </button>
                <button
                  onClick={() => decide("reject")}
                  disabled={busy}
                  className="rounded-lg border border-red-200 px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-40"
                >
                  Reject
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
              <span>This record is {record.status.replace("_", " ")}.</span>
              {record.status === "approved" && (
                <button
                  onClick={async () => setExported(await exportCare(record.id))}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50"
                >
                  Export approved record
                </button>
              )}
            </div>
          )}

          {exported && (
            <pre className="mt-3 max-h-56 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
              {JSON.stringify(exported.note, null, 2)}
            </pre>
          )}

          {events.length > 0 && (
            <div className="mt-4">
              <p className="mb-1 text-xs font-semibold text-slate-500 uppercase">Audit history</p>
              <ol className="space-y-1 text-xs text-slate-600">
                {events.map((event, i) => (
                  <li key={i}>
                    <span className="font-medium text-slate-800">{event.action}</span> · revision {event.revision} ·{" "}
                    {new Date(event.created_at).toLocaleString()}
                    {event.note && <span className="italic"> — “{event.note}”</span>}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
