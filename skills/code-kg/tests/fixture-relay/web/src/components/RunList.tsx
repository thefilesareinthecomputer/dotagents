import { AppState, submitGoal } from "../state";
import { formatRunLine, statusColor } from "../format";

export interface RunListProps {
  state: AppState;
  container: HTMLElement;
}

export class RunList {
  private readonly container: HTMLElement;

  constructor(container: HTMLElement) {
    this.container = container;
  }

  render(state: AppState): void {
    this.container.innerHTML = "";
    const form = document.createElement("form");
    const input = document.createElement("input");
    input.placeholder = "goal for the agent";
    form.appendChild(input);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (input.value.trim()) void submitGoal(input.value.trim());
    });
    this.container.appendChild(form);

    const list = document.createElement("ul");
    for (const run of state.runs) {
      const item = document.createElement("li");
      item.textContent = formatRunLine(run);
      item.style.color = statusColor(run.failed);
      list.appendChild(item);
    }
    this.container.appendChild(list);

    if (state.runState === "loading") {
      const note = document.createElement("p");
      note.textContent = "running…";
      this.container.appendChild(note);
    }
  }
}
