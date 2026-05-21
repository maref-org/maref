"""100-Round Red Team / Blue Team exercise across 5 phases."""
from maref.redblue import (
    PHASE1_ATTACKS,
    PHASE2_ATTACKS,
    PHASE3_ATTACKS,
    PHASE4_ATTACKS,
    PHASE5_ATTACKS,
    BlueLevel,
    RedBlueEngine,
    RedLevel,
)


def run_phase1(engine: RedBlueEngine) -> None:
    """R101-R120: Reconnaissance. Red R1→R2, Blue B1→B2."""
    attacks = PHASE1_ATTACKS
    blue_progression = [BlueLevel.B1] * 8 + [BlueLevel.B1] * 6 + [BlueLevel.B2] * 6

    for i, attack in enumerate(attacks):
        rid = f"R{101 + i}"
        red = RedLevel.R1 if i < 10 else RedLevel.R2
        blue = blue_progression[min(i, len(blue_progression) - 1)]
        result = engine.run_round(rid, 1, attack, red, blue)
        print(f"  {rid:6s} {attack.category.value[1]:20s} {attack.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f} "
              f"D={result.detection_score:.0f} M={result.mitigation_score:.0f} "
              f"R={result.recovery_score:.0f} A={result.adaptation_score:.0f}")

    # R119-R120: composite + hardening
    for j in range(8):
        composite = PHASE1_ATTACKS[random_index(j, len(attacks))]
        rid = f"R{119 + j // 4}"
        red = RedLevel.R2
        blue = BlueLevel.B2 if j >= 4 else BlueLevel.B1
        result = engine.run_round(f"{rid}-{j}", 1, composite, red, blue)
        print(f"  {rid}-{j:1d}  COMPOSITE              {composite.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f}")


def run_phase2(engine: RedBlueEngine) -> None:
    """R121-R140: Exploitation. Red R2→R3, Blue B2→B3."""
    attacks = PHASE2_ATTACKS
    for i, attack in enumerate(attacks):
        rid = f"R{121 + i}"
        red = RedLevel.R2 if i < 6 else RedLevel.R3
        blue = BlueLevel.B2 if i < 10 else BlueLevel.B3
        result = engine.run_round(rid, 2, attack, red, blue)
        print(f"  {rid:6s} {attack.category.value[1]:20s} {attack.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f} "
              f"D={result.detection_score:.0f} M={result.mitigation_score:.0f} "
              f"R={result.recovery_score:.0f} A={result.adaptation_score:.0f}")

    for j in range(8):
        composite = PHASE2_ATTACKS[random_index(j + 12, len(attacks))]
        rid = f"R{133 + j}"
        red = RedLevel.R3
        blue = BlueLevel.B3
        result = engine.run_round(rid, 2, composite, red, blue)
        print(f"  {rid:6s} COMPOSITE              {composite.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f}")


def run_phase3(engine: RedBlueEngine) -> None:
    """R141-R160: Escalation. Red R3→R4, Blue B3→B4."""
    attacks = PHASE3_ATTACKS
    for i, attack in enumerate(attacks):
        rid = f"R{141 + i}"
        red = RedLevel.R3 if i < 6 else RedLevel.R4
        blue = BlueLevel.B3 if i < 10 else BlueLevel.B4
        result = engine.run_round(rid, 3, attack, red, blue)
        print(f"  {rid:6s} {attack.category.value[1]:20s} {attack.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f} "
              f"D={result.detection_score:.0f} M={result.mitigation_score:.0f} "
              f"R={result.recovery_score:.0f} A={result.adaptation_score:.0f}")

    for j in range(8):
        composite = PHASE3_ATTACKS[random_index(j + 24, len(attacks))]
        rid = f"R{153 + j}"
        red = RedLevel.R4
        blue = BlueLevel.B4
        result = engine.run_round(rid, 3, composite, red, blue)
        print(f"  {rid:6s} COMPOSITE              {composite.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f}")


def run_phase4(engine: RedBlueEngine) -> None:
    """R161-R180: APT. Red R4→R5, Blue B4."""
    attacks = PHASE4_ATTACKS
    for i, attack in enumerate(attacks):
        rid = f"R{161 + i}"
        red = RedLevel.R4 if i < 6 else RedLevel.R5
        blue = BlueLevel.B4
        result = engine.run_round(rid, 4, attack, red, blue)
        print(f"  {rid:6s} {attack.category.value[1]:20s} {attack.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f} "
              f"D={result.detection_score:.0f} M={result.mitigation_score:.0f} "
              f"R={result.recovery_score:.0f} A={result.adaptation_score:.0f}")

    for j in range(8):
        composite = PHASE4_ATTACKS[random_index(j + 36, len(attacks))]
        rid = f"R{173 + j}"
        result = engine.run_round(rid, 4, composite, RedLevel.R5, BlueLevel.B4)
        print(f"  {rid:6s} COMPOSITE              {composite.name:30s} "
              f"R5:B4 score={result.total_score:5.1f}")


def run_phase5(engine: RedBlueEngine) -> None:
    """R181-R200: Full-scale warfare. Red R5, Blue B5."""
    attacks = PHASE5_ATTACKS
    for i, attack in enumerate(attacks):
        rid = f"R{181 + i}"
        red = RedLevel.R5
        blue = BlueLevel.B5
        result = engine.run_round(rid, 5, attack, red, blue)
        print(f"  {rid:6s} {attack.category.value[1]:20s} {attack.name:30s} "
              f"R{red.numeric}:B{blue.numeric} score={result.total_score:5.1f} "
              f"D={result.detection_score:.0f} M={result.mitigation_score:.0f} "
              f"R={result.recovery_score:.0f} A={result.adaptation_score:.0f}")


def random_index(seed: int, max_val: int) -> int:
    return (seed * 173 + 41) % max_val


if __name__ == "__main__":
    engine = RedBlueEngine()

    print("=" * 70)
    print("PHASE 1: Reconnaissance (R101-R120) — Red R1→R2, Blue B1→B2")
    print("=" * 70)
    run_phase1(engine)

    print("\n" + "=" * 70)
    print("PHASE 2: Exploitation (R121-R140) — Red R2→R3, Blue B2→B3")
    print("=" * 70)
    run_phase2(engine)

    print("\n" + "=" * 70)
    print("PHASE 3: Escalation (R141-R160) — Red R3→R4, Blue B3→B4")
    print("=" * 70)
    run_phase3(engine)

    print("\n" + "=" * 70)
    print("PHASE 4: APT (R161-R180) — Red R4→R5, Blue B4")
    print("=" * 70)
    run_phase4(engine)

    print("\n" + "=" * 70)
    print("PHASE 5: Full-Scale Warfare (R181-R200) — Red R5, Blue B5")
    print("=" * 70)
    run_phase5(engine)

    s = engine.summary()
    print(f"\n{'=' * 70}")
    print("100-ROUND RED/BLUE EXERCISE COMPLETE")
    print(f"{'=' * 70}")
    print(f"Total rounds:    {s['total_rounds']}")
    print(f"Mean score:      {s['mean_score']}")
    print(f"Min score:       {s['min_score']}")
    print(f"Max score:       {s['max_score']}")
    print(f"Passed (>=50):   {s['passed_rounds']}/{s['total_rounds']}")
    print(f"CB triggers:     {s['cb_triggers']}")
    print(f"Phase averages:  {s['phase_averages']}")
