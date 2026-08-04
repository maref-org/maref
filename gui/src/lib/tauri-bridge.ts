// Tauri bridge — replaces Electron preload.cjs
// Provides the same marefElectron API using Tauri invoke

import { invoke } from "@tauri-apps/api/core";

export interface MarefTauri {
  pty: {
    spawn: (shell?: string, rows?: number, cols?: number) => Promise<number>;
    write: (data: string) => Promise<void>;
    resize: (rows: number, cols: number) => Promise<void>;
    kill: () => Promise<void>;
  };
  sidecar: {
    start: () => Promise<void>;
    stop: () => Promise<void>;
  };
  shell: {
    openExternal: (url: string) => Promise<void>;
  };
  dialog: {
    openDirectory: () => Promise<string | null>;
  };
  pet: {
    spawn: (species: string) => Promise<void>;
    move: (x: number, y: number) => Promise<void>;
    speak: (text: string) => Promise<void>;
    hide: () => Promise<void>;
    switchSpecies: (species: string) => Promise<void>;
  };
}

const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

export const marefTauri: MarefTauri = {
  pty: {
    spawn: (shell, rows = 24, cols = 80) =>
      isTauri ? invoke<number>("pty_spawn", { shell, rows, cols }) : Promise.resolve(0),
    write: (data) =>
      isTauri ? invoke("pty_write", { data }) : Promise.resolve(),
    resize: (rows, cols) =>
      isTauri ? invoke("pty_resize", { rows, cols }) : Promise.resolve(),
    kill: () =>
      isTauri ? invoke("pty_kill") : Promise.resolve(),
  },
  sidecar: {
    start: () =>
      isTauri ? invoke("sidecar_start") : Promise.resolve(),
    stop: () =>
      isTauri ? invoke("sidecar_stop") : Promise.resolve(),
  },
  shell: {
    openExternal: (url) =>
      isTauri ? invoke("open_external", { url }) : Promise.resolve(window.open(url, "_blank")).then(() => undefined),
  },
  dialog: {
    openDirectory: () =>
      isTauri ? invoke<string>("dialog_open") : Promise.resolve(null),
  },
  pet: {
    spawn: (species) =>
      isTauri ? invoke("spawn_pet_window", { species }) : Promise.resolve(),
    move: (x, y) =>
      isTauri ? invoke("move_pet_window", { x, y }) : Promise.resolve(),
    speak: (text) =>
      isTauri ? invoke("pet_speak_bubble", { text }) : Promise.resolve(),
    hide: () =>
      isTauri ? invoke("hide_pet_window") : Promise.resolve(),
    switchSpecies: (species) =>
      isTauri ? invoke("switch_pet_species", { species }) : Promise.resolve(),
  },
};

export function isTauriEnv(): boolean {
  return isTauri;
}
