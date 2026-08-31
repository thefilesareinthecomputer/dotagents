const read = (key: string, fallback: string): string => {
  const value = typeof process !== "undefined" ? process.env?.[key] : undefined;
  return value && value.length > 0 ? value : fallback;
};

export const env = {
  apiBase: read("API_BASE", "/api"),
  appName: read("APP_NAME", "Fixture Invoicing"),
  pageSize: Number.parseInt(read("PAGE_SIZE", "20"), 10),
  isProd: read("NODE_ENV", "development") === "production",
};

export const apiUrl = (path: string): string => {
  const base = env.apiBase.replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${base}${suffix}`;
};
