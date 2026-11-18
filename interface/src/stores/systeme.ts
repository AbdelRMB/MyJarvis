import { create } from "zustand";
import { api } from "../lib/api";
import type { Systeme } from "../lib/types";

const MAX = 90; // 3 minutes à 2 s

type Serie = { cpu: number[]; ram: number[]; gpu: number[]; vram: number[] };

export const useSysteme = create<{ dernier: Systeme | null; serie: Serie; joignable: boolean }>(() => ({
  dernier: null,
  serie: { cpu: [], ram: [], gpu: [], vram: [] },
  joignable: true,
}));

const pousser = (a: number[], v: number) => [...a.slice(-(MAX - 1)), v];

export async function rafraichirSysteme() {
  try {
    const s = await api<Systeme>("/api/systeme");
    useSysteme.setState(({ serie }) => ({
      dernier: s,
      joignable: true,
      serie: {
        cpu: pousser(serie.cpu, s.cpu),
        ram: pousser(serie.ram, s.ram),
        gpu: pousser(serie.gpu, s.gpu?.util ?? 0),
        vram: pousser(serie.vram, s.gpu ? (s.gpu.vram_used / s.gpu.vram_total) * 100 : 0),
      },
    }));
  } catch {
    useSysteme.setState({ joignable: false });
  }
}
