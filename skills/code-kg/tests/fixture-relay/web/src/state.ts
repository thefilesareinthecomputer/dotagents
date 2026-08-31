import { FetchState, MemoryHit, RunSummary } from "@relay/types";
import { latestRun, searchMemory, startRun } from "./api";

export interface AppState {
  runState: FetchState;
  runs: RunSummary[];
  hits: MemoryHit[];
  lastError: string;
}

type Listener = (state: AppState) => void;

const state: AppState = {
  runState: "idle",
  runs: [],
  hits: [],
  lastError: "",
};

const listeners: Listener[] = [];

export function subscribe(listener: Listener): () => void {
  listeners.push(listener);
  return () => {
    const i = listeners.indexOf(listener);
    if (i >= 0) listeners.splice(i, 1);
  };
}

function publish(): void {
  for (const listener of listeners) listener({ ...state });
}

export async function submitGoal(goal: string): Promise<void> {
  state.runState = "loading";
  publish();
  const result = await startRun(goal);
  if (result.ok) {
    state.runs = [result.value, ...state.runs].slice(0, 20);
    state.runState = "loaded";
    state.lastError = "";
  } else {
    state.runState = "error";
    state.lastError = result.error.message;
  }
  publish();
}

export async function refreshMemory(query: string): Promise<void> {
  const result = await searchMemory(query);
  if (result.ok) {
    state.hits = result.value.hits;
    state.lastError = "";
  } else {
    state.lastError = result.error.message;
  }
  publish();
}

export async function loadLatest(): Promise<string> {
  const result = await latestRun();
  return result.ok ? result.value.body : `no runs: ${result.error.message}`;
}

export function currentState(): AppState {
  return { ...state };
}
