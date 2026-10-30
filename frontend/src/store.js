import { configureStore, createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import * as api from "./api";

const WELCOME = {
  role: "assistant",
  text: "Ready to process new complaints. Paste the customer's email, describe the issue in your own words, or upload a PDF complaint report. I'll extract the details into the form and run an initial risk assessment.",
};

export const sendMessage = createAsyncThunk("copilot/send", async (text, { getState, rejectWithValue }) => {
  try {
    return await api.chat(text, getState().copilot.complaint?.id);
  } catch (err) {
    return rejectWithValue(err.message);
  }
});

export const uploadDocument = createAsyncThunk("copilot/upload", async (file, { rejectWithValue }) => {
  try {
    return await api.upload(file);
  } catch (err) {
    return rejectWithValue(err.message);
  }
});

export const decide = createAsyncThunk(
  "copilot/decide",
  async ({ action, acknowledge, note }, { getState, rejectWithValue }) => {
    const { complaint } = getState().copilot;
    try {
      const updated =
        action === "approve"
          ? await api.approve(complaint.id, complaint.revision, acknowledge, note)
          : await api.reject(complaint.id, complaint.revision, note);
      return { complaint: updated, events: await api.history(complaint.id) };
    } catch (err) {
      return rejectWithValue(err.message);
    }
  },
);

export const loadHistory = createAsyncThunk("copilot/history", async (id) => api.history(id));

const initialState = {
  complaint: null, // the persisted record as returned by the API; single source of truth for the form
  patch: null, // fields changed by the last EDIT, used to highlight them
  messages: [WELCOME],
  events: [],
  review: null, // what a reviewer should look at first, from the last AI operation
  busy: null, // "sending" | "uploading" | "reviewing" | null
};

const copilot = createSlice({
  name: "copilot",
  initialState,
  reducers: {
    reset: () => initialState,
  },
  extraReducers: (builder) => {
    const settled = (state, { payload }) => {
      state.busy = null;
      state.complaint = payload.complaint;
      state.patch = payload.patch;
      state.review = payload.review ?? null;
      state.events = [];
      state.messages.push({ role: "assistant", text: payload.message, intent: payload.intent });
      if (payload.risk_assessment) state.messages.push({ role: "risk", risk: payload.risk_assessment });
    };
    const failed = (state, { payload, error }) => {
      state.busy = null;
      state.messages.push({ role: "error", text: payload ?? error.message });
    };
    builder
      .addCase(sendMessage.pending, (state, { meta }) => {
        state.busy = "sending";
        state.messages.push({ role: "user", text: meta.arg });
      })
      .addCase(uploadDocument.pending, (state, { meta }) => {
        state.busy = "uploading";
        state.messages.push({ role: "user", text: `Uploaded ${meta.arg.name}`, file: true });
      })
      .addCase(sendMessage.fulfilled, settled)
      .addCase(uploadDocument.fulfilled, settled)
      .addCase(sendMessage.rejected, failed)
      .addCase(uploadDocument.rejected, failed)
      .addCase(decide.pending, (state) => {
        state.busy = "reviewing";
      })
      .addCase(decide.fulfilled, (state, { payload }) => {
        state.busy = null;
        state.complaint = payload.complaint;
        state.events = payload.events;
      })
      .addCase(decide.rejected, failed)
      .addCase(loadHistory.fulfilled, (state, { payload }) => {
        state.events = payload;
      });
  },
});

export const { reset } = copilot.actions;

export const analyseNote = createAsyncThunk("care/analyse", async ({ note, carePlan }, { rejectWithValue }) => {
  try {
    return await api.analyseNote(note, carePlan);
  } catch (err) {
    return rejectWithValue(err.message);
  }
});

export const decideCare = createAsyncThunk(
  "care/decide",
  async ({ action, acknowledged, note }, { getState, rejectWithValue }) => {
    const { record } = getState().care;
    try {
      const updated = await api.decideCare(record.id, action, record.revision, acknowledged, note);
      return { record: updated, events: await api.careHistory(record.id) };
    } catch (err) {
      return rejectWithValue(err.message);
    }
  },
);

const care = createSlice({
  name: "care",
  initialState: { record: null, events: [], busy: false, error: null },
  reducers: {
    clear: (state) => {
      state.record = null;
      state.events = [];
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    const working = (state) => {
      state.busy = true;
      state.error = null;
    };
    const failed = (state, { payload, error }) => {
      state.busy = false;
      state.error = payload ?? error.message;
    };
    builder
      .addCase(analyseNote.pending, working)
      .addCase(analyseNote.fulfilled, (state, { payload }) => {
        state.busy = false;
        state.record = payload;
        state.events = [];
      })
      .addCase(analyseNote.rejected, failed)
      .addCase(decideCare.pending, working)
      .addCase(decideCare.fulfilled, (state, { payload }) => {
        state.busy = false;
        state.record = payload.record;
        state.events = payload.events;
      })
      .addCase(decideCare.rejected, failed);
  },
});

export const { clear: clearCare } = care.actions;

export const store = configureStore({ reducer: { copilot: copilot.reducer, care: care.reducer } });
