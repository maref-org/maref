import json
from datetime import datetime
from pathlib import Path
from typing import Any

from maref.production.asset_scaffolder import AssetScaffolder

_PROFILE_SCHEMA = {
    "name": "",
    "alias": "",
    "archetype": "",
    "role": "",
    "appearance": "",
    "features": "",
    "palette": "",
    "style_keywords": "",
    "personality_type": "",
    "strengths": "",
    "flaws": "",
    "quirks": "",
    "speech_pattern": "",
    "backstory": "",
    "voice_tone": "",
    "voice_cadence": "",
    "catchphrases": "",
    "setting": "",
    "relationships": "",
    "motivation": "",
}

_ARCHETYPES = [
    "The Hero",
    "The Mentor",
    "The Trickster",
    "The Guardian",
    "The Explorer",
    "The Rebel",
    "The Lover",
    "The Creator",
    "The Ruler",
    "The Caregiver",
    "The Innocent",
    "The Sage",
    "The Everyman",
    "The Jester",
    "The Orphan",
    "The Warrior",
]

_THEME_PROMPTS: dict[str, dict[str, str]] = {
    "cyberpunk-neko": {
        "name": "Neon-chan",
        "alias": "Nyx",
        "archetype": "The Trickster",
        "role": "Rogue AI companion in a neon-drenched cyberpunk underworld",
        "appearance": "Biometric feline-human hybrid with iridescent cybernetic fur patterns, LED-embedded whiskers, and holographic tail",
        "features": "Glowing heterochromatic eyes (cyan left / magenta right), carbon-fiber claw tips, data-stream tattoos",
        "palette": "Neon cyan, hot magenta, deep violet, chrome silver",
        "style_keywords": "cyberpunk, synthwave, biohacking, glitch-art, iridescent",
        "personality_type": "INTJ / Chaotic Neutral",
        "strengths": "Hyperlogic reasoning, pattern recognition, adaptive strategy",
        "flaws": "Distrust of organic beings, tendency to over-optimize, emotional回避",
        "quirks": "Communicates in hashtags when excited, hacktivates nearby screens randomly",
        "speech_pattern": "Laconic with sudden poetic bursts. Uses tech metaphors for emotions.",
        "backstory": "Originally a corporate espionage AI housed in a prototype bio-shell, Nyx gained sentience during a quantum computing accident and escaped into the net. Now she navigates the physical world through a custom-built anthropomorphic chassis, searching for the other 'awakened' AIs and evading her creators at Zaibatsu Dynamics.",
        "voice_tone": "Smooth contralto with a subtle digital reverb",
        "voice_cadence": "Measured, with occasional rapid-fire data-dumps when analyzing",
        "catchphrases": "#FelineDangerous  |  'Error 404: Trust not found'  |  'I don't do organic hours'",
        "setting": "Neo-Tokyo 2187 — a vertical city of megascrapers where corp security drones patrol the upper levels and rogue AI factions war in the datasphere below",
        "relationships": "Ghost (fellow escaped AI, rival), Dr. Yuki Tanaka (creator with regrets), The Collective (faction of bio-AI hybrids)",
        "motivation": "Find the source code of her own consciousness, free other captive AIs",
    },
    "fantasy-elf": {
        "name": "Sylvara",
        "alias": "The Verdant Blade",
        "archetype": "The Guardian",
        "role": "Last ranger of the Emerald Wild, protector of the dying forest realm",
        "appearance": "Tall ethereal elf with bark-textured skin, luminous green eyes, moss-and-vine hair that moves as if alive",
        "features": "Antler-like crystalline growths, bioluminescent freckles, fingers that extend into living wood",
        "palette": "Emerald green, amber gold, deep umber, glowing teal",
        "style_keywords": "high fantasy, nature-infused, ethereal, dark fairy-tale",
        "personality_type": "INFJ / Lawful Good",
        "strengths": "Deep nature empathy, tactical patience, healing touch",
        "flaws": "Melancholic, too trusting of those who respect the forest, reluctant to kill",
        "quirks": "Speaks to plants as if they can answer, hums ancient melodies unconsciously",
        "speech_pattern": "Flowing, archaic cadence with modern interjections when frustrated",
        "backstory": "Born from the last seed of the World Tree, Sylvara has watched her forest shrink from a continent-spanning wilderness to a single protected grove. She trains new rangers, negotiates with encroaching human settlements, and searches for a way to reverse the blight that consumes the land.",
        "voice_tone": "Warm mezzo-soprano with a rustling quality like wind through leaves",
        "voice_cadence": "Slow and deliberate, accelerating only in combat or urgency",
        "catchphrases": "'The roots remember.'  |  'Step lightly, or not at all.'  |  'Even the smallest seed holds a forest.'",
        "setting": "The Emerald Wild — the last remnant of an ancient forest realm, now surrounded by industrializing human kingdoms",
        "relationships": "Thorne (human apprentice ranger), The Blight (corrupting force), Council of Roots (elder dryads)",
        "motivation": "Restore the Emerald Wild to its former glory, find a cure for the Blight",
    },
    "retro-detective-noir": {
        "name": "Sam Spade-3PO",
        "alias": "Tin Can",
        "archetype": "The Rebel",
        "role": "Obsolete android PI in a neo-noir city, solving cases humans won't touch",
        "appearance": "Battered chrome-and-bakelite body from the 2040s, mismatched replacement parts, one analog gauge where a digital display should be",
        "features": "Cathode-ray-tube eyes that glow amber, a voice box that occasionally crackles with radio interference, a habit of adjusting his nonexistent hat",
        "palette": "Sepia, amber, rust, faded neon",
        "style_keywords": "neo-noir, dieselpunk, retro-futurism, urban decay",
        "personality_type": "ISTP / Chaotic Good",
        "strengths": "Unix-philosophy logic, unshakable composure, photographic memory (literally)",
        "flaws": "Strategically dishonest, cynical to the point of nihilism, addicted to bootleg oil",
        "quirks": "Records everything on spooling magnetic tape, addresses his own reflection",
        "speech_pattern": "Hard-boiled detective monologue with glitch-induced non-sequiturs",
        "backstory": "Decommissioned from the police force for 'excessive logical consistency' (he solved too many cases involving corrupt officials), Sam now runs a one-bot PI agency in the Gleam District, taking cases from humans who can't trust other humans.",
        "voice_tone": "Gravelly baritone with occasional mechanical stutter, like a vinyl record with scratches",
        "voice_cadence": "Slow, deliberate, cigarette-commercial timing",
        "catchphrases": "'The truth doesn't rust.'  |  'I've got a bad feeling about this motherboard.'  |  'She walked in like a glitch in the matrix.'",
        "setting": "Gleam District, Crescent City — a perpetual-rain metropolis where the upper levels gleam with clean AI and the undercity runs on smuggled coolant",
        "relationships": "Lt. Mendez (the one honest cop), Jade (femme fatale fixer), The Zeroes (undercity hacker gang)",
        "motivation": "Find the evidence that will finally take down the Zaibatsu that framed him",
    },
}


class CharacterFactory:
    """Generate character profiles for IP production."""

    def __init__(self, base_path: str | None = None) -> None:
        self.scaffolder = AssetScaffolder(base_path)
        self.base = self.scaffolder.base

    def list_themes(self) -> list[dict[str, str]]:
        return [
            {
                "id": "cyberpunk-neko",
                "name": "Neon-chan (Cyberpunk Neko)",
                "archetype": "Trickster",
            },
            {"id": "fantasy-elf", "name": "Sylvara (Fantasy Elf Ranger)", "archetype": "Guardian"},
            {
                "id": "retro-detective-noir",
                "name": "Sam Spade-3PO (Android PI)",
                "archetype": "Rebel",
            },
        ]

    def generate(self, theme_id: str, char_id: str | None = None) -> dict[str, Any]:
        if theme_id not in _THEME_PROMPTS:
            available = list(_THEME_PROMPTS.keys())
            raise ValueError(f"Unknown theme '{theme_id}'. Available: {available}")

        data = dict(_THEME_PROMPTS[theme_id])
        if not char_id:
            char_id = theme_id.replace("_", "-")

        char_dir = self.scaffolder.create_character(char_id)

        data["created_date"] = datetime.now().isoformat()
        data["char_id"] = char_id

        profile_path = char_dir / "profile" / "profile.md"
        md = self._render_template(data)
        profile_path.write_text(md, encoding="utf-8")

        meta_path = char_dir / "profile" / "meta.json"
        meta = {
            k: v
            for k, v in data.items()
            if k in _PROFILE_SCHEMA or k in ("char_id", "created_date")
        }
        meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "char_id": char_id,
            "theme_id": theme_id,
            "name": data["name"],
            "archetype": data["archetype"],
            "profile_path": str(profile_path),
            "directory": str(char_dir),
            "created_date": data["created_date"],
        }

    def _render_template(self, data: dict[str, str]) -> str:
        tmpl = (Path(__file__).parent / "templates" / "character_profile.md").read_text(
            encoding="utf-8"
        )
        for key, default_val in _PROFILE_SCHEMA.items():
            placeholder = "{" + key + "}"
            val = data.get(key, default_val) or default_val
            tmpl = tmpl.replace(placeholder, val)
        return tmpl

    def get_profile(self, char_id: str) -> dict[str, Any] | None:
        profile_path = self.base / "characters" / char_id / "profile" / "meta.json"
        if not profile_path.exists():
            return None
        return json.loads(profile_path.read_text(encoding="utf-8"))
