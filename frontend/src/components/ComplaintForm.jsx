import { useSelector } from "react-redux";
import RiskAssessment from "./RiskAssessment";

const SECTIONS = [
  {
    key: "complainant",
    title: "Complainant Information",
    fields: [
      ["name", "Name"],
      ["email", "Email"],
      ["phone", "Phone"],
      ["organization", "Organization"],
      ["country", "Country"],
      ["contact_channel", "Contact channel"],
    ],
  },
  {
    key: "product",
    title: "Product Information",
    fields: [
      ["product_name", "Product name"],
      ["generic_name", "Generic name / API"],
      ["manufacturer", "Manufacturer"],
      ["dosage_form", "Dosage form"],
      ["strength", "Strength"],
      ["batch_number", "Batch number"],
      ["lot_number", "Lot number"],
      ["manufacturing_date", "Manufacturing date"],
      ["expiry_date", "Expiry date"],
    ],
  },
  {
    key: "complaint",
    title: "Complaint / Defect Information",
    fields: [
      ["complaint_received_date", "Complaint received"],
      ["event_date", "Event date"],
      ["defect_category", "Defect category"],
      ["affected_quantity", "Affected quantity"],
      ["sample_available", "Sample available"],
      ["suspected_counterfeit", "Suspected counterfeit"],
      ["complaint_description", "Complaint description", "wide"],
      ["defect_description", "Defect description", "wide"],
    ],
  },
  {
    key: "patient",
    title: "Patient / Consumer Information",
    fields: [
      ["patient_involved", "Patient involved"],
      ["patient_age", "Age"],
      ["patient_gender", "Gender"],
      ["adverse_event", "Adverse event"],
      ["medical_attention_required", "Medical attention"],
      ["hospitalization_required", "Hospitalization"],
      ["death_reported", "Death reported"],
    ],
  },
];

const ENUMS = new Set(["contact_channel", "defect_category", "patient_gender"]);

function display(key, value) {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (ENUMS.has(key)) return value.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
  return String(value);
}

export default function ComplaintForm() {
  const { complaint, patch } = useSelector((s) => s.copilot);
  const risk = complaint?.risk_assessment;

  return (
    <section className="flex flex-col gap-6 rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Log Customer Complaint</h1>
          <p className="text-sm text-slate-500">API &amp; FDF Quality Assurance · Customer Complaint intake</p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium">
          {complaint && (
            <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-slate-600">
              {complaint.reference}
            </span>
          )}
          {complaint && (
            <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-600">
              via {complaint.source === "document" ? "document" : "chat"}
            </span>
          )}
          <span className={`rounded-md px-2 py-1 ${risk ? "bg-indigo-50 text-indigo-700" : "bg-amber-50 text-amber-700"}`}>
            {risk ? "AI triaged" : "Pending triage"}
          </span>
        </div>
      </header>

      {SECTIONS.map(({ key, title, fields }, i) => {
        const data = complaint?.[key] ?? {};
        const filled = fields.filter(([f]) => data[f] != null).length;
        return (
          <fieldset key={key}>
            <div className="mb-3 flex items-baseline justify-between border-b border-slate-100 pb-2">
              <h2 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                {i + 1}. {title}
              </h2>
              <span className={`text-xs ${filled === fields.length ? "text-emerald-600" : "text-slate-400"}`}>
                {filled}/{fields.length} captured
              </span>
            </div>
            <div className="grid grid-cols-1 gap-x-4 gap-y-3 md:grid-cols-2">
              {fields.map(([f, label, wide]) => {
                const value = data[f];
                const updated = patch?.[key]?.[f] !== undefined;
                return (
                  <div key={f} className={`min-w-0 ${wide ? "md:col-span-2" : ""}`}>
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-600">{label}</span>
                      {updated && <span className="font-medium text-amber-600">updated</span>}
                    </div>
                    <div
                      className={`min-h-9 rounded-md border px-3 py-1.5 text-sm break-words transition-colors ${
                        updated
                          ? "border-amber-300 bg-amber-50 text-slate-900"
                          : value == null
                            ? "border-dashed border-slate-200 bg-slate-50 text-slate-400 italic"
                            : "border-slate-200 bg-white text-slate-900"
                      }`}
                    >
                      {value == null ? "Awaiting AI extraction" : display(f, value)}
                    </div>
                  </div>
                );
              })}
            </div>
          </fieldset>
        );
      })}

      <RiskAssessment risk={risk} />
    </section>
  );
}
