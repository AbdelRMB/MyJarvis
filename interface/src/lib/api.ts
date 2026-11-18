import type { Session } from "./types";

let jeton = "";

export const getJeton = () => jeton;

export async function ouvrirSession(): Promise<Session> {
  const r = await fetch("/api/session");
  if (!r.ok) throw new Error(`Serveur injoignable (${r.status})`);
  const s = (await r.json()) as Session;
  jeton = s.jeton;
  return s;
}

type Options = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

export async function api<T>(chemin: string, options: Options = {}, essai = 0): Promise<T> {
  const { json, headers, ...opts } = options;
  const h: Record<string, string> = { "x-jeton": jeton, ...(headers as Record<string, string> | undefined) };
  let body = opts.body;
  if (json !== undefined) {
    h["content-type"] = "application/json";
    body = JSON.stringify(json);
  }
  const r = await fetch(chemin, { ...opts, body, headers: h });
  if (r.status === 403 && essai === 0) {
    await ouvrirSession();
    return api<T>(chemin, options, 1);
  }
  if (!r.ok) {
    let msg = r.statusText || String(r.status);
    try {
      msg = (await r.json()).detail ?? msg;
    } catch {
      /* corps non JSON */
    }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}
