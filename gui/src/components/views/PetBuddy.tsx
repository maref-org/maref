import { useState, useEffect, useCallback } from "react";
import { Shuffle, Sparkles, Heart, Grid3X3, Check, UserX } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  SPECIES, RARITY_COLORS_CLASS, STAT_LABELS, type PetState,
  rollWeighted, genStats, loadPet, savePet, loadPets, savePets,
  broadcastPetChange, tauriShowPet, tauriSwitchPet, tauriHidePet,
} from "@/lib/pet-bus";

export function PetBuddy() {
  const [pet, setPet] = useState<PetState | null>(null);
  const [collection, setCollection] = useState<PetState[]>([]);
  const [rolling, setRolling] = useState(false);
  const [view, setView] = useState<"current" | "gallery">("current");

  useEffect(() => { setPet(loadPet()); setCollection(loadPets()); }, []);

  const summon = useCallback(() => {
    setRolling(true);
    setTimeout(() => {
      const s = rollWeighted();
      const st: PetState = { species: s, stats: genStats(s.rarity), acquiredAt: new Date().toISOString() };
      savePet(st); setPet(st);
      const updated = [...loadPets().filter(p => p.species.id !== s.id || p.acquiredAt !== st.acquiredAt), st];
      savePets(updated); setCollection(updated);
      setRolling(false);
      broadcastPetChange(st);
      tauriShowPet(st);
    }, 400);
  }, []);

  const select = useCallback((p: PetState) => {
    savePet(p); setPet(p); setView("current");
    broadcastPetChange(p);
    tauriSwitchPet(p);
  }, []);

  const retire = useCallback(() => {
    savePet(null); setPet(null);
    broadcastPetChange(null);
    tauriHidePet();
  }, []);

  if (view === "gallery") {
    return (
      <div className="space-y-3">
        <button onClick={() => setView("current")} className="text-xs text-maref-accent hover:underline">← 返回</button>
        <div className="grid grid-cols-2 gap-2">
          {collection.map((p, i) => (
            <button key={i} onClick={() => select(p)} className={cn(
              "flex items-center gap-2 rounded-lg border p-2.5 text-left hover:border-maref-accent transition-colors",
              pet?.acquiredAt === p.acquiredAt ? "border-maref-accent bg-maref-surface-alt" : "border-maref-border"
            )}>
              <span className="text-xl">{p.species.icon}</span>
              <div className="min-w-0 flex-1">
                <div className="text-xs font-medium text-maref-text truncate">{p.species.name}</div>
                <span className={cn("inline-flex items-center rounded-full border px-1.5 py-0 text-[9px]", RARITY_COLORS_CLASS[p.species.rarity])}>{p.species.rarity}</span>
              </div>
              {pet?.acquiredAt === p.acquiredAt && <Check className="h-3.5 w-3.5 text-maref-accent flex-shrink-0" />}
            </button>
          ))}
          <button onClick={summon} disabled={rolling} className="flex flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed border-maref-border p-3 text-maref-text-muted hover:border-maref-accent hover:text-maref-accent transition-colors disabled:opacity-50">
            <Sparkles className={cn("h-4 w-4", rolling && "animate-spin")} />
            <span className="text-[10px]">召唤新伙伴</span>
          </button>
        </div>
        <div className="rounded-lg border border-maref-border bg-maref-surface-alt/50 p-3">
          <div className="flex items-center gap-1.5 mb-2">
            <Grid3X3 className="h-3.5 w-3.5 text-maref-text-muted" />
            <span className="text-xs font-medium text-maref-text">图鉴</span>
            <span className="text-[10px] text-maref-text-muted ml-auto">{collection.length}/{SPECIES.length}</span>
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {SPECIES.map((s) => {
              const owned = collection.some((p) => p.species.id === s.id);
              return (
                <div key={s.id} className={cn("flex flex-col items-center gap-0.5 rounded-lg border p-2 text-center", owned ? "border-maref-border bg-maref-surface" : "border-dashed border-maref-border opacity-40")}>
                  <span className="text-lg">{owned ? s.icon : "❓"}</span>
                  <span className="text-[9px] text-maref-text-muted truncate max-w-full">{owned ? s.name : "???"}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    );
  }

  if (!pet) {
    return (
      <div className="flex flex-col items-center gap-4 py-6">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-maref-surface-alt border-2 border-dashed border-maref-border text-3xl">❓</div>
        <p className="text-sm text-maref-text-muted">尚未获得修行伙伴</p>
        <button onClick={summon} disabled={rolling} className="inline-flex items-center gap-2 rounded-lg bg-purple-600 hover:bg-purple-700 px-5 py-2.5 text-sm font-medium text-white transition-colors disabled:opacity-50 shadow-md">
          <Sparkles className={cn("h-4 w-4", rolling && "animate-spin")} />
          {rolling ? "召唤中…" : "召唤修行伙伴"}
        </button>
      </div>
    );
  }

  const { species, stats } = pet;
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        <div className="relative flex-shrink-0">
          <div className="flex h-16 w-16 items-center justify-center rounded-full text-3xl animate-[breathe_3s_ease-in-out_infinite]" style={{ background: `${species.color}18`, boxShadow: `0 0 20px ${species.color}30` }}>
            {species.icon}
          </div>
          <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full text-[10px]" style={{ backgroundColor: species.color, color: "#fff" }}><Heart className="h-2.5 w-2.5" /></span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-semibold text-maref-text">{species.name}</h4>
            <span className={cn("inline-flex items-center rounded-full border px-2 py-0 text-[10px] font-medium", RARITY_COLORS_CLASS[species.rarity])}>{species.rarity}</span>
          </div>
          <p className="text-[11px] text-maref-text-muted/70 mt-0.5 italic">「{species.quote}」</p>
          <p className="text-[10px] text-maref-text-muted mt-0.5">结缘于 {new Date(pet.acquiredAt).toLocaleDateString("zh-CN")}</p>
        </div>
        <div className="flex gap-1.5 flex-shrink-0">
          <button onClick={() => setView("gallery")} className="rounded-lg border border-maref-border p-2 text-maref-text-muted hover:text-maref-text hover:border-maref-accent transition-colors" title="伙伴列表"><Grid3X3 className="h-3.5 w-3.5" /></button>
          <button onClick={summon} disabled={rolling} className="rounded-lg border border-maref-border p-2 text-maref-text-muted hover:text-maref-text hover:border-maref-accent transition-colors disabled:opacity-50" title="重新召唤"><Shuffle className={cn("h-3.5 w-3.5", rolling && "animate-spin")} /></button>
          <button onClick={retire} className="rounded-lg border border-maref-border p-2 text-maref-text-muted hover:text-red-500 hover:border-red-300 transition-colors" title="放生"><UserX className="h-3.5 w-3.5" /></button>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {STAT_LABELS.map(({ key, label, icon }) => (
          <div key={key} className="rounded-lg border border-maref-border bg-maref-surface-alt/50 px-2.5 py-1.5">
            <div className="flex items-center gap-1 text-[10px] text-maref-text-muted"><span>{icon}</span><span>{label}</span></div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="flex-1 h-1 rounded-full bg-maref-border overflow-hidden"><div className="h-full rounded-full" style={{ width: `${stats[key]}%`, backgroundColor: species.color }} /></div>
              <span className="text-[10px] text-maref-text-muted tabular-nums w-6 text-right">{stats[key]}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
