import Database from "better-sqlite3";

let handle: Database.Database | null = null;

export const db = (): Database.Database => {
  if (!handle) {
    handle = new Database("data/cache.sqlite3", { readonly: false });
    handle.pragma("journal_mode = WAL");
  }
  return handle;
};

export const query = <T>(sql: string, params: unknown[] = []): T[] => {
  return db().prepare(sql).all(...params) as T[];
};

export const one = <T>(sql: string, params: unknown[] = []): T | undefined => {
  return db().prepare(sql).get(...params) as T | undefined;
};

export const run = (sql: string, params: unknown[] = []): void => {
  db().prepare(sql).run(...params);
};
