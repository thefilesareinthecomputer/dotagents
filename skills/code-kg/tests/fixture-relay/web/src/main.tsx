import { subscribe, currentState } from "./state";
import { RunList } from "./components/RunList";
import { RunDetail } from "./components/RunDetail";
import { logInfo, logError } from "./console";
import { HashRouter } from "./router";

function mount(): void {
  logInfo("mounting relay console");
  const listEl = document.getElementById("runs");
  const detailEl = document.getElementById("detail");
  if (!listEl || !detailEl) {
    logError("index.html is missing #runs or #detail");
    throw new Error("index.html is missing #runs or #detail");
  }
  const list = new RunList(listEl);
  const detail = new RunDetail(detailEl);
  const router = new HashRouter();
  router.onChange((route) => logInfo(`view: ${route.view}`));

  subscribe((state) => {
    list.render(state);
    detail.render(state);
  });

  void detail.refresh().then(() => {
    list.render(currentState());
    detail.render(currentState());
  });
}

document.addEventListener("DOMContentLoaded", mount);
