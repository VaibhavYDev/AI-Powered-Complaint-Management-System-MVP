import { describe, expect, it } from "vitest";

import { decide, loadHistory, sendMessage, store, uploadDocument, reset } from "./store.js";

const RISK = { severity_class: "III", severity_reason: "Cosmetic.", confidence: 0.8 };
const COMPLAINT = { id: 1, reference: "CC-2026-0001", product: { batch_number: "PCM24031" } };

function state() {
  return store.getState().copilot;
}

function dispatch(action) {
  store.dispatch(action);
  return state();
}

describe("copilot slice", () => {
  it("starts empty with a welcome message", () => {
    const s = dispatch(reset());
    expect(s.complaint).toBeNull();
    expect(s.busy).toBeNull();
    expect(s.messages).toHaveLength(1);
  });

  it("records the user message and busy state while sending", () => {
    dispatch(reset());
    const s = dispatch({ type: sendMessage.pending.type, meta: { arg: "broken tablets" } });
    expect(s.busy).toBe("sending");
    expect(s.messages.at(-1)).toMatchObject({ role: "user", text: "broken tablets" });
  });

  it("stores the complaint and appends the reply and risk card", () => {
    dispatch(reset());
    const s = dispatch({
      type: sendMessage.fulfilled.type,
      payload: { intent: "LOG", message: "Logged.", complaint: COMPLAINT, patch: null, risk_assessment: RISK },
    });
    expect(s.busy).toBeNull();
    expect(s.complaint).toEqual(COMPLAINT);
    expect(s.messages.at(-2)).toMatchObject({ role: "assistant", text: "Logged.", intent: "LOG" });
    expect(s.messages.at(-1)).toMatchObject({ role: "risk", risk: RISK });
  });

  it("keeps the patch so changed fields can be highlighted, and adds no risk card without one", () => {
    dispatch(reset());
    const patch = { product: { batch_number: "PCM24099" } };
    const s = dispatch({
      type: sendMessage.fulfilled.type,
      payload: { intent: "EDIT", message: "Updated.", complaint: COMPLAINT, patch, risk_assessment: null },
    });
    expect(s.patch).toEqual(patch);
    expect(s.messages.filter((m) => m.role === "risk")).toHaveLength(0);
  });

  it("shows an upload as a file message and clears busy on failure", () => {
    dispatch(reset());
    const file = { name: "complaint.pdf" };
    let s = dispatch({ type: uploadDocument.pending.type, meta: { arg: file } });
    expect(s.busy).toBe("uploading");
    expect(s.messages.at(-1)).toMatchObject({ role: "user", file: true });

    s = dispatch({ type: uploadDocument.rejected.type, payload: "The PDF could not be read.", error: {} });
    expect(s.busy).toBeNull();
    expect(s.messages.at(-1)).toMatchObject({ role: "error", text: "The PDF could not be read." });
  });

  it("reset clears a loaded complaint", () => {
    dispatch({
      type: sendMessage.fulfilled.type,
      payload: { intent: "LOG", message: "Logged.", complaint: COMPLAINT, patch: null, risk_assessment: RISK },
    });
    const s = dispatch(reset());
    expect(s.complaint).toBeNull();
    expect(s.messages).toHaveLength(1);
  });
});

describe("review decisions", () => {
  it("keeps the evidence summary from the last AI operation", () => {
    dispatch(reset());
    const review = { unsupported: ["complaint.complaint_received_date"], derived: [], missing: [], quoted: 5 };
    const s = dispatch({
      type: sendMessage.fulfilled.type,
      payload: { intent: "LOG", message: "Logged.", complaint: COMPLAINT, patch: null, review },
    });
    expect(s.review).toEqual(review);
    expect(s.events).toEqual([]);
  });

  it("replaces the complaint and audit trail once a decision is applied", () => {
    dispatch(reset());
    const approved = { ...COMPLAINT, status: "approved", revision: 1 };
    const events = [{ action: "extracted", revision: 1 }, { action: "approved", revision: 1 }];

    let s = dispatch({ type: decide.pending.type });
    expect(s.busy).toBe("reviewing");

    s = dispatch({ type: decide.fulfilled.type, payload: { complaint: approved, events } });
    expect(s.busy).toBeNull();
    expect(s.complaint.status).toBe("approved");
    expect(s.events).toHaveLength(2);
  });

  it("surfaces a revision conflict as an error message", () => {
    dispatch(reset());
    const s = dispatch({
      type: decide.rejected.type,
      payload: "This complaint changed while you were reviewing it.",
      error: {},
    });
    expect(s.busy).toBeNull();
    expect(s.messages.at(-1)).toMatchObject({ role: "error" });
  });

  it("loads history on demand", () => {
    dispatch(reset());
    const s = dispatch({ type: loadHistory.fulfilled.type, payload: [{ action: "extracted", revision: 1 }] });
    expect(s.events).toHaveLength(1);
  });
});
