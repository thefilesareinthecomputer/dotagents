export type View = "runs" | "memory" | "config";

export interface Route {
  view: View;
  param: string;
}

const DEFAULT_ROUTE: Route = { view: "runs", param: "" };

export function parseHash(hash: string): Route {
  const cleaned = hash.replace(/^#\/?/, "");
  if (!cleaned) return DEFAULT_ROUTE;
  const [head, ...rest] = cleaned.split("/");
  if (head === "runs" || head === "memory" || head === "config") {
    return { view: head, param: rest.join("/") };
  }
  return DEFAULT_ROUTE;
}

export function toHash(route: Route): string {
  return route.param ? `#/${route.view}/${route.param}` : `#/${route.view}`;
}

type RouteListener = (route: Route) => void;

export class HashRouter {
  private listeners: RouteListener[] = [];

  constructor() {
    window.addEventListener("hashchange", () => this.emit());
  }

  current(): Route {
    return parseHash(window.location.hash);
  }

  navigate(route: Route): void {
    window.location.hash = toHash(route);
  }

  onChange(listener: RouteListener): void {
    this.listeners.push(listener);
  }

  private emit(): void {
    const route = this.current();
    for (const listener of this.listeners) listener(route);
  }
}
