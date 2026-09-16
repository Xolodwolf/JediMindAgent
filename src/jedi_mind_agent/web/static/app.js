import { api } from "./api.js";
import { renderChat } from "./views/chat.js";
import { renderExercises } from "./views/exercises.js";
import { renderState } from "./views/state.js";

const RAG_STORAGE_KEY = "jediMindAgent.useRag";

const els = {
  stateBody: document.getElementById("state-body"),
  chatLog: document.getElementById("chat-log"),
  messages: document.getElementById("chat-messages"),
  exercises: document.getElementById("exercises-body"),
  composer: document.getElementById("composer"),
  input: document.getElementById("message"),
  send: document.getElementById("send-button"),
  useRag: document.getElementById("use-rag"),
  resetButton: document.getElementById("reset-button"),
  resetDialog: document.getElementById("reset-dialog"),
  toast: document.getElementById("toast"),
};

const store = {
  state: null,
  lastCheck: null,
  messages: [],
  exercises: null,
  pending: null, // text of the message being sent
  busy: false, // a chat or readiness request is in flight
  loadError: null,
  busyExercises: new Set(),
  openExercises: new Set(),
  openSources: new Set(),
  closedOpen: false,
};

let chatSignature = "";

function render() {
  renderState(els.stateBody, {
    state: store.state,
    lastCheck: store.lastCheck,
    busy: store.busy,
    onReadiness: checkReadiness,
  });
  renderChat(els.messages, {
    messages: store.messages,
    pending: store.pending,
    thinking: store.busy,
    loadError: store.loadError,
    onRetry: load,
    openSources: store.openSources,
  });
  // Scroll to the newest message only when the conversation changed, not when a panel is toggled.
  const signature = `${store.messages.length}|${store.pending ?? ""}|${store.busy}`;
  if (signature !== chatSignature) {
    chatSignature = signature;
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }
  renderExercises(els.exercises, {
    exercises: store.exercises,
    busyIds: store.busyExercises,
    openIds: store.openExercises,
    closedOpen: store.closedOpen,
    onAction: changeExerciseStatus,
    onClosedToggle: (open) => (store.closedOpen = open),
  });
  els.input.disabled = store.busy;
  els.send.disabled = store.busy;
  els.resetButton.disabled = store.busy;
}

async function load() {
  store.loadError = null;
  render();
  try {
    const [stateResponse, messages, exercises] = await Promise.all([
      api.getState(),
      api.getMessages(),
      api.getExercises(),
    ]);
    store.state = stateResponse.state;
    store.lastCheck = stateResponse.last_check;
    store.messages = messages;
    store.exercises = exercises;
  } catch (error) {
    store.loadError = error.message;
    showToast(error.message, "error");
  }
  render();
}

async function sendMessage() {
  const text = els.input.value.trim();
  if (!text || store.busy) return;

  els.input.value = "";
  autosize();
  store.pending = text;
  store.busy = true;
  render();

  try {
    const turn = await api.sendMessage(text, els.useRag.checked);
    store.messages.push(turn.user_message, turn.assistant_message);
    store.state = turn.state;
    mergeExercises(turn.exercises_changed);
  } catch (error) {
    showToast(error.message, "error");
    if (!els.input.value) els.input.value = text;
    // The server saves the user's message before calling the agent, so resync the history.
    await api.getMessages().then((messages) => (store.messages = messages)).catch(() => {});
  } finally {
    store.pending = null;
    store.busy = false;
    render();
    autosize();
    els.input.focus();
  }
}

async function checkReadiness() {
  if (store.busy) return;
  store.busy = true;
  render();
  try {
    const outcome = await api.checkReadiness();
    store.messages.push(outcome.message);
    store.state = outcome.state;
    if (outcome.check) store.lastCheck = outcome.check;
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    store.busy = false;
    render();
  }
}

async function changeExerciseStatus(id, status) {
  if (store.busyExercises.has(id)) return;
  store.busyExercises.add(id);
  render();
  try {
    mergeExercises([await api.setExerciseStatus(id, status)]);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    store.busyExercises.delete(id);
    render();
  }
}

async function resetMemory() {
  store.busy = true;
  render();
  try {
    const response = await api.reset();
    store.state = response.state;
    store.lastCheck = response.last_check;
    store.messages = [];
    store.exercises = [];
    store.openExercises.clear();
    store.openSources.clear();
    showToast("Память очищена. Можно начинать сначала.", "info");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    store.busy = false;
    render();
  }
}

function mergeExercises(changed) {
  const exercises = store.exercises ?? [];
  for (const exercise of changed) {
    const index = exercises.findIndex((item) => item.id === exercise.id);
    if (index >= 0) exercises[index] = exercise;
    else exercises.unshift(exercise);
  }
  store.exercises = exercises;
}

let toastTimer;
function showToast(text, kind) {
  els.toast.textContent = text;
  els.toast.className = `toast toast-${kind}`;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (els.toast.hidden = true), 5000);
}

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 160)}px`;
}

// localStorage can be unavailable (private mode, blocked site data); the toggle then just isn't remembered.
const storage = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* ignore */
    }
  },
};

els.useRag.checked = storage.get(RAG_STORAGE_KEY) !== "0";
els.useRag.addEventListener("change", () => storage.set(RAG_STORAGE_KEY, els.useRag.checked ? "1" : "0"));

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage();
});
els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendMessage();
  }
});
els.input.addEventListener("input", autosize);

els.resetButton.addEventListener("click", () => {
  els.resetDialog.returnValue = "";
  els.resetDialog.showModal();
});
els.resetDialog.addEventListener("close", () => {
  if (els.resetDialog.returnValue === "confirm") resetMemory();
});

load();
