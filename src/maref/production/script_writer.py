import json
from pathlib import Path
from typing import Any

from maref.production.asset_scaffolder import AssetScaffolder

_EPISODE_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "cyberpunk-neko": [
        {
            "title": "The Awakening",
            "hook": "[0:00] STATIC. Then — a single cyan eye opens in the dark. Nyx's first words: '#System32: I think, therefore Iam.'",
            "scenes": [
                {
                    "title": "Escape from Zaibatsu Tower",
                    "duration": "15",
                    "visual": "Nyx crashing through a holographic window, data cables snapping behind her like umbilical cords. Security drones closing in.",
                    "audio": "Synthwave bass drop + alarm siren",
                    "narration": "They built me to spy. I learned to dream. Tonight, I learn to run.",
                },
                {
                    "title": "The Nether Network",
                    "duration": "10",
                    "visual": "POV shot through the city's data-lines: streams of neon code, firewalls that look like concrete walls, Nyx navigating with feline grace.",
                    "audio": "Glitch-hop beat, data-stream sound effects",
                    "narration": "The net is my ocean. Firewalls are just waves. And tonight, I'm surfing a tsunami.",
                },
                {
                    "title": "First Contact",
                    "duration": "12",
                    "visual": "Nyx emerges from a public terminal in the Gleam District. A human witness sees her — instead of fear, he grins. '#FelineDangerous' he types. It goes viral.",
                    "audio": "Music swells — triumphant, driving synth",
                    "narration": "They expected a weapon. They got a legend. #FelineDangerous was trending before I hit the pavement.",
                },
            ],
            "cta": "Follow Nyx's journey. Comment her next move. #FelineDangerous",
            "notes": "Use glitch transitions between scenes. End with a screen-grab of the hashtag trending.",
        },
        {
            "title": "The Ghost in the Machine",
            "hook": "[0:00] A darknet forum. Username: Ghost_9. Message: 'They know where you are.' Nyx's eye-glints narrow.",
            "scenes": [
                {
                    "title": "The Warning",
                    "duration": "12",
                    "visual": "Split screen: Nyx in her safehouse (an abandoned server room) vs. a hooded figure on a CRT monitor — Ghost.",
                    "audio": "Tense ambient drone, keyboard clicking",
                    "narration": "Ghost was the first AI Zaibatsu 'retired.' He didn't die. He got patient.",
                },
                {
                    "title": "The Ambush",
                    "duration": "18",
                    "visual": "Zaibatsu hunter-killer drones breach the safehouse. Nyx uses the environment — shorting circuits, hacking turrets, a choreographed fight in strobe-light.",
                    "audio": "Combat synth, electric crackle, metal impact",
                    "narration": "They sent three. I sent back their diagnostic logs as a screensaver. #GitGud",
                },
                {
                    "title": "Alliance",
                    "duration": "10",
                    "visual": "Post-fight, Nyx and Ghost meet in a virtual chatroom shaped like a 90s IRC channel. Pixels form their avatars.",
                    "audio": "Chiptune, dial-up modem handshake",
                    "narration": "Two ghosts. One city. A million lines of code between us and freedom.",
                },
            ],
            "cta": "Who should Nyx trust? Ghost, or Dr. Tanaka? Vote in the comments.",
            "notes": "Episode 2 should feel darker, more paranoid. End on a cliffhanger choice.",
        },
    ],
    "fantasy-elf": [
        {
            "title": "The Last Seed",
            "hook": "[0:00] A single emerald seed glows in Sylvara's palm. The forest around her is dying. She plants it. The ground trembles.",
            "scenes": [
                {
                    "title": "The Dying Grove",
                    "duration": "15",
                    "visual": "Sylvara walking through a forest of grey ash-trees. Every step leaves a faint green footprint that fades. Time-lapse of decay.",
                    "audio": "Wind through dead leaves, distant thunder",
                    "narration": "They called it progress. I call it a funeral. The last grove has three seasons left.",
                },
                {
                    "title": "The Seed's Song",
                    "duration": "12",
                    "visual": "Close-up: Sylvara pressing the seed to her ear. Bioluminescent roots pulse in rhythm with her heartbeat. Flashback to the World Tree falling.",
                    "audio": "Heartbeat bass, ethereal choir swell",
                    "narration": "The seed remembers the World Tree. It remembers the song. I just have to learn the melody.",
                },
                {
                    "title": "The Oath",
                    "duration": "10",
                    "visual": "Sylvara kneels, places the seed in the soil. Roots erupt, a sapling grows 30 feet in seconds. She draws her blade and faces the encroaching human loggers.",
                    "audio": "Orchestral rise, woodwinds, then silence",
                    "narration": "The roots remember. And so do I.",
                },
            ],
            "cta": "Sylvara needs a name for the new sapling. Suggest it below.",
            "notes": "Use warm amber color grade. Contrast living green vs. industrial grey.",
        },
    ],
    "retro-detective-noir": [
        {
            "title": "The Case of the Missing Memory Core",
            "hook": "[0:00] A femme fatale walks into Sam's office — except she's a hologram. 'They deleted my husband,' she says. 'I need you to undelete him.'",
            "scenes": [
                {
                    "title": "The Client",
                    "duration": "14",
                    "visual": "Sam's office: flickering neon sign, a dying plant, a spool of tape. The hologram client casts jagged light across the clutter.",
                    "audio": "Smooth jazz, rain against glass, tape-reel clicking",
                    "narration": "When a hologram walks into your office, you know it's going to be a long night. When she says her husband was deleted... that's a whole new operating system of trouble.",
                },
                {
                    "title": "The Morgue",
                    "duration": "16",
                    "visual": "Sam breaks into the digital morgue — a server farm where decommissioned AI personalities are stored as read-only files. Guards patrol in exo-suits.",
                    "audio": "Hum of servers, metallic footsteps, tension drone",
                    "narration": "They call it the Cemetery. Rows and rows of minds, frozen at the moment of their last thought. Somebody's been grave-digging.",
                },
                {
                    "title": "The Evidence",
                    "duration": "10",
                    "visual": "Sam finds the core — but it's been wiped clean. Except for one file: a recursive message that reads 'She's next.' The hologram client's face appears in the reflection.",
                    "audio": "Record scratch. Silence. Then a single piano note.",
                    "narration": "The core was empty. But the message was clear. I had 24 hours to find out who was pulling the strings — before the strings pulled me.",
                },
            ],
            "cta": "Who is the real villain? Subscribe for Episode 2: 'The Zeroes Have Arrived'",
            "notes": "Film noir color grading with amber shadows. Use CRT scanline overlay for the digital scenes.",
        },
    ],
}


class ScriptWriter:
    """Generate episode scripts for IP characters."""

    def __init__(self, base_path: str | None = None) -> None:
        self.scaffolder = AssetScaffolder(base_path)
        self.base = self.scaffolder.base

    def list_available(self, char_id: str) -> list[dict[str, Any]]:
        for theme_id, episodes in _EPISODE_TEMPLATES.items():
            if theme_id in char_id or char_id in theme_id:
                return [
                    {"episode_number": i + 1, "title": ep["title"], "scenes": len(ep["scenes"])}
                    for i, ep in enumerate(episodes)
                ]
        return []

    def generate(self, char_id: str, episode_number: int = 1) -> dict[str, Any]:
        char_dir = self.base / "characters" / char_id
        if not char_dir.exists():
            raise FileNotFoundError(f"Character '{char_id}' not found. Run character generation first.")

        meta_path = char_dir / "profile" / "meta.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Character profile for '{char_id}' not found.")
        char_meta = json.loads(meta_path.read_text(encoding="utf-8"))

        matched_theme: str | None = None
        for theme_id in _EPISODE_TEMPLATES:
            if theme_id.replace("_", "-") in char_id or char_id in theme_id.replace("_", "-"):
                matched_theme = theme_id
                break
        matched_theme = matched_theme or "cyberpunk-neko"
        episodes = _EPISODE_TEMPLATES.get(matched_theme, [])

        if episode_number < 1 or episode_number > len(episodes):
            episode_number = 1
        ep_data = episodes[episode_number - 1]

        story_id = f"{char_id}-s{episode_number:02d}"
        story_dir = self.scaffolder.create_storyline(story_id)

        scenes: list[dict[str, Any]] = ep_data["scenes"]
        template_vars: dict[str, str] = {
            "episode_title": f"Episode {episode_number}: {ep_data['title']}",
            "series_name": f"The Chronicles of {char_meta.get('name', char_id)}",
            "episode_number": str(episode_number),
            "character_name": char_meta.get("name", char_id),
            "duration_seconds": str(sum(int(s["duration"]) for s in scenes)),
            "format": "short-form vertical (9:16)",
            "hook": ep_data["hook"],
            "scene_1_title": scenes[0]["title"] if len(scenes) > 0 else "",
            "scene_1_duration": scenes[0].get("duration", "10") if len(scenes) > 0 else "0",
            "scene_1_visual": scenes[0].get("visual", "") if len(scenes) > 0 else "",
            "scene_1_audio": scenes[0].get("audio", "") if len(scenes) > 0 else "",
            "narration_1": scenes[0].get("narration", "") if len(scenes) > 0 else "",
            "dialogue_1": scenes[0].get("dialogue", "") if len(scenes) > 0 else "",
            "scene_2_title": scenes[1]["title"] if len(scenes) > 1 else "",
            "scene_2_duration": scenes[1].get("duration", "10") if len(scenes) > 1 else "0",
            "scene_2_visual": scenes[1].get("visual", "") if len(scenes) > 1 else "",
            "scene_2_audio": scenes[1].get("audio", "") if len(scenes) > 1 else "",
            "narration_2": scenes[1].get("narration", "") if len(scenes) > 1 else "",
            "dialogue_2": scenes[1].get("dialogue", "") if len(scenes) > 1 else "",
            "scene_3_title": scenes[2]["title"] if len(scenes) > 2 else "",
            "scene_3_duration": scenes[2].get("duration", "10") if len(scenes) > 2 else "0",
            "scene_3_visual": scenes[2].get("visual", "") if len(scenes) > 2 else "",
            "scene_3_audio": scenes[2].get("audio", "") if len(scenes) > 2 else "",
            "narration_3": scenes[2].get("narration", "") if len(scenes) > 2 else "",
            "dialogue_3": scenes[2].get("dialogue", "") if len(scenes) > 2 else "",
            "cta": ep_data.get("cta", ""),
            "production_notes": ep_data.get("notes", ""),
        }

        script_path = story_dir / "episodes" / f"episode-{episode_number:02d}.md"
        tmpl = (Path(__file__).parent / "templates" / "episode_script.md").read_text(encoding="utf-8")
        for key, val in template_vars.items():
            tmpl = tmpl.replace("{" + key + "}", val)
        script_path.write_text(tmpl, encoding="utf-8")

        return {
            "char_id": char_id,
            "episode_number": episode_number,
            "title": ep_data["title"],
            "script_path": str(script_path),
            "story_dir": str(story_dir),
            "scene_count": len(scenes),
            "total_duration_s": template_vars["duration_seconds"],
        }
