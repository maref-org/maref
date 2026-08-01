export interface PetSpecies {
  id: string; name: string; rarity: "凡尘" | "江湖" | "宗师" | "传说" | "神话";
  icon: string; color: string; weight: number; quote: string;
}

export interface PetStats { wu: number; yun: number; xi: number; ding: number; xia: number; }

export interface PetState { species: PetSpecies; stats: PetStats; acquiredAt: string; }

export const SPECIES: PetSpecies[] = [
  { id: "panda", name: "熊猫书生", rarity: "凡尘", icon: "🐼", color: "#22c55e", weight: 30, quote: "待我细细研读此篇文档" },
  { id: "bingmayong", name: "兵马俑小将", rarity: "凡尘", icon: "🗿", color: "#78716c", weight: 30, quote: "末将在此守护后台" },
  { id: "huadan", name: "粤剧花旦", rarity: "江湖", icon: "💃", color: "#ec4899", weight: 15, quote: "水袖轻摆，代码即成诗" },
  { id: "bianlian", name: "川剧变脸", rarity: "江湖", icon: "🎭", color: "#f59e0b", weight: 10, quote: "报错则黑脸，通过则大笑" },
  { id: "jingju", name: "京剧净角", rarity: "宗师", icon: "🎪", color: "#ef4444", weight: 6, quote: "此代码如包公断案，公正无私" },
  { id: "feitian", name: "敦煌飞天", rarity: "宗师", icon: "🧚", color: "#a855f7", weight: 4, quote: "飘带环绕，进度如云霞舒展" },
  { id: "wukong", name: "齐天大圣", rarity: "传说", icon: "🐵", color: "#f97316", weight: 3, quote: "俺老孙火眼金睛，Bug精哪里逃" },
  { id: "nianshou", name: "年兽宝宝", rarity: "传说", icon: "🦁", color: "#dc2626", weight: 1, quote: "里程碑达成，放个鞭炮庆贺" },
  { id: "pangu", name: "盘古元神", rarity: "神话", icon: "🌌", color: "#6366f1", weight: 0.5, quote: "混沌初开，代码由此创世" },
];

export const RARITY_COLORS_CLASS: Record<string, string> = {
  "凡尘": "border-gray-300 text-gray-500",
  "江湖": "border-green-300 text-green-600",
  "宗师": "border-purple-300 text-purple-600",
  "传说": "border-orange-300 text-orange-600",
  "神话": "border-indigo-300 text-indigo-600",
};

export const STAT_LABELS: { key: keyof PetStats; label: string; icon: string }[] = [
  { key: "wu", label: "悟性", icon: "💡" },
  { key: "yun", label: "筋斗云", icon: "☁️" },
  { key: "xi", label: "戏法", icon: "✨" },
  { key: "ding", label: "定力", icon: "🧘" },
  { key: "xia", label: "侠义", icon: "⚔️" },
];

const PET_STORAGE_KEY = "maref_pet";
const PETS_STORAGE_KEY = "maref_pets";
const PET_EVENT = "maref-pet-changed";

import { marefTauri } from "./tauri-bridge";

export function rollWeighted(): PetSpecies {
  const total = SPECIES.reduce((s, x) => s + x.weight, 0);
  let roll = Math.random() * total;
  for (const s of SPECIES) { roll -= s.weight; if (roll <= 0) return s; }
  return SPECIES[0];
}

export function genStats(rarity: string): PetStats {
  const b = rarity === "凡尘" ? 20 : rarity === "江湖" ? 35 : rarity === "宗师" ? 50 : rarity === "传说" ? 70 : 85;
  const r = () => Math.floor(Math.random() * 16) + b;
  return { wu: r(), yun: r(), xi: r(), ding: r(), xia: r() };
}

export function loadPet(): PetState | null {
  try { const r = localStorage.getItem(PET_STORAGE_KEY); return r ? JSON.parse(r) : null; } catch { return null; }
}

export function savePet(p: PetState | null) {
  if (p) {
    try { localStorage.setItem(PET_STORAGE_KEY, JSON.stringify(p)); } catch { /* ignore */ }
  } else {
    try { localStorage.removeItem(PET_STORAGE_KEY); } catch { /* ignore */ }
  }
}

export function loadPets(): PetState[] {
  try { const r = localStorage.getItem(PETS_STORAGE_KEY); return r ? JSON.parse(r) : []; } catch { return []; }
}

export function savePets(ps: PetState[]) {
  try { localStorage.setItem(PETS_STORAGE_KEY, JSON.stringify(ps)); } catch { /* ignore */ }
}

export function broadcastPetChange(pet: PetState | null) {
  window.dispatchEvent(new CustomEvent(PET_EVENT, { detail: { pet } }));
}

export function onPetChange(handler: (pet: PetState | null) => void) {
  const wrapper = (e: Event) => { const ce = e as CustomEvent; handler(ce.detail?.pet ?? null); };
  window.addEventListener(PET_EVENT, wrapper as EventListener);
  return () => window.removeEventListener(PET_EVENT, wrapper as EventListener);
}

export async function tauriShowPet(pet: PetState): Promise<void> {
  try { await marefTauri.pet.spawn(pet.species.id); } catch { /* ignore */ }
}

export async function tauriSwitchPet(pet: PetState): Promise<void> {
  try { await marefTauri.pet.switchSpecies(pet.species.id); } catch { /* ignore */ }
}

export async function tauriHidePet(): Promise<void> {
  try { await marefTauri.pet.hide(); } catch { /* ignore */ }
}

export async function tauriMovePet(x: number, y: number): Promise<void> {
  try { await marefTauri.pet.move(x, y); } catch { /* ignore */ }
}

export async function tauriPetSpeak(text: string): Promise<void> {
  try { await marefTauri.pet.speak(text); } catch { /* ignore */ }
}
