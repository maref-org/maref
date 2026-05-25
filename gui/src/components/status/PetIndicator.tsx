import { useState, useEffect } from "react";
import { Heart } from "lucide-react";
import { cn } from "@/lib/utils";
import { type PetState, loadPet, onPetChange, RARITY_COLORS_CLASS, STAT_LABELS } from "@/lib/pet-bus";

export function PetIndicator() {
  const [pet, setPet] = useState<PetState | null>(() => loadPet());
  const [open, setOpen] = useState(false);
  const [animClass, setAnimClass] = useState("");

  useEffect(() => {
    return onPetChange((next) => setPet(next));
  }, []);

  useEffect(() => {
    if (!pet) return;
    const states = [
      "animate-[breathe_3s_ease-in-out_infinite]",
      "animate-[breathe_3s_ease-in-out_infinite] scale-110",
      "animate-[breathe_3s_ease-in-out_infinite]",
      "animate-[breathe_3s_ease-in-out_infinite] -translate-y-1",
    ];
    let i = 0;
    const timer = setInterval(() => {
      setAnimClass(states[i % states.length]);
      i++;
    }, 3000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pet?.acquiredAt]);

  if (!pet) return null;

  const { species, stats } = pet;

  return (
    <div className="relative flex-shrink-0">
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          "flex items-center justify-center h-6 w-6 rounded-full transition-all cursor-pointer",
          animClass || "animate-[breathe_3s_ease-in-out_infinite]"
        )}
        style={{ background: `${species.color}20`, boxShadow: `0 0 6px ${species.color}40` }}
        title={species.name}
      >
        <span className="text-sm leading-none">{species.icon}</span>
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute bottom-8 right-0 z-50 w-56 rounded-xl border-2 bg-white dark:bg-gray-900 border-gray-200 dark:border-gray-700 shadow-xl animate-[fadeIn_150ms_ease-out]">
            <div className="flex items-center gap-3 p-3 border-b border-gray-100 dark:border-gray-800">
              <div className="flex h-10 w-10 items-center justify-center rounded-full text-xl animate-[breathe_3s_ease-in-out_infinite]" style={{ background: `${species.color}20` }}>{species.icon}</div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">{species.name}</span>
                  <Heart className="h-3 w-3 flex-shrink-0" style={{ color: species.color }} />
                </div>
                <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-0.5 italic line-clamp-2">「{species.quote}」</p>
              </div>
            </div>
            <div className="p-2.5">
              {STAT_LABELS.map(({ key, label, icon }) => (
                <div key={key} className="flex items-center gap-2 py-0.5">
                  <span className="text-[10px] w-5">{icon}</span>
                  <span className="text-[10px] text-gray-500 dark:text-gray-400 w-10">{label}</span>
                  <div className="flex-1 h-1 rounded-full bg-gray-100 dark:bg-gray-800 overflow-hidden">
                    <div className="h-full rounded-full transition-all" style={{ width: `${stats[key]}%`, backgroundColor: species.color }} />
                  </div>
                  <span className="text-[9px] text-gray-400 dark:text-gray-500 tabular-nums w-5 text-right">{stats[key]}</span>
                </div>
              ))}
            </div>
            <div className="border-t border-gray-100 dark:border-gray-800 px-3 py-1.5 flex items-center justify-between">
              <span className="text-[9px] text-gray-400">{new Date(pet.acquiredAt).toLocaleDateString("zh-CN")}</span>
              <span className={cn("inline-flex items-center rounded-full border px-1.5 py-0 text-[8px] font-medium", RARITY_COLORS_CLASS[species.rarity])}>{species.rarity}</span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
