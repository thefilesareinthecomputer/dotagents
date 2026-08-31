import { AppState, loadLatest, refreshMemory } from "../state";
import { truncate } from "../format";

export class RunDetail {
  private readonly container: HTMLElement;
  private body = "";

  constructor(container: HTMLElement) {
    this.container = container;
  }

  async refresh(): Promise<void> {
    this.body = await loadLatest();
  }

  render(state: AppState): void {
    this.container.innerHTML = "";
    const heading = document.createElement("h2");
    heading.textContent = "Latest run";
    this.container.appendChild(heading);

    const pre = document.createElement("pre");
    pre.textContent = truncate(this.body || "(nothing yet)", 2000);
    this.container.appendChild(pre);

    const search = document.createElement("input");
    search.placeholder = "search memory";
    search.addEventListener("change", () => {
      if (search.value.trim()) void refreshMemory(search.value.trim());
    });
    this.container.appendChild(search);

    const hits = document.createElement("ul");
    for (const hit of state.hits) {
      const item = document.createElement("li");
      item.textContent = `[${hit.kind}] ${hit.key}: ${truncate(hit.body, 160)}`;
      hits.appendChild(item);
    }
    this.container.appendChild(hits);

    if (state.lastError) {
      const err = document.createElement("p");
      err.className = "error";
      err.textContent = state.lastError;
      this.container.appendChild(err);
    }
  }
}
