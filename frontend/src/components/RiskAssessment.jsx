export const SEVERITY = {
  I: { label: "Class I · Critical", classes: "bg-red-100 text-red-800 ring-red-200" },
  II: { label: "Class II · Major", classes: "bg-amber-100 text-amber-800 ring-amber-200" },
  III: { label: "Class III · Minor", classes: "bg-emerald-100 text-emerald-800 ring-emerald-200" },
};

export default function RiskAssessment({ risk }) {
  return (
    <fieldset className="rounded-lg border border-indigo-100 bg-indigo-50/40 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs font-semibold tracking-wide text-indigo-700 uppercase">5. AI-Assisted Risk Assessment</h2>
        {risk && (
          <span className={`rounded-md px-2 py-1 text-xs font-semibold ring-1 ${SEVERITY[risk.severity_class].classes}`}>
            {SEVERITY[risk.severity_class].label}
          </span>
        )}
      </div>

      {!risk ? (
        <p className="text-sm text-slate-500 italic">
          Generated automatically once a complaint is logged or extracted from a document.
        </p>
      ) : (
        <div className="grid gap-4 text-sm md:grid-cols-2">
          <div className="md:col-span-2">
            <p className="mb-1 text-xs font-medium text-slate-600">Severity reasoning</p>
            <p className="leading-relaxed text-slate-800">{risk.severity_reason}</p>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-600">Immediate actions</p>
            <ol className="list-decimal space-y-1 pl-5 text-slate-800">
              {risk.immediate_actions.map((a) => <li key={a}>{a}</li>)}
            </ol>
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-600">Recommended follow-up</p>
            <ol className="list-decimal space-y-1 pl-5 text-slate-800">
              {risk.recommended_follow_up.map((a) => <li key={a}>{a}</li>)}
            </ol>
          </div>
          <div className="md:col-span-2">
            <div className="mb-1 flex justify-between text-xs text-slate-600">
              <span className="font-medium">AI confidence</span>
              <span>{Math.round(risk.confidence * 100)}%</span>
            </div>
            <div className="h-1.5 w-full rounded-full bg-slate-200">
              <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${risk.confidence * 100}%` }} />
            </div>
          </div>
          <p className="text-xs text-slate-500 md:col-span-2">{risk.disclaimer}</p>
        </div>
      )}
    </fieldset>
  );
}
