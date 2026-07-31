-------------------------------- MODULE MarefLite --------------------------------
(*
  MAREF-Lite: 10-State Gray Code Governance State Machine

  This TLA+ specification formally models the 10-state (Hetu) governance
  overlay for multi-agent systems. The state machine uses Gray code encoding
  to ensure single-bit transitions between adjacent states, preventing
  race conditions during state changes.

  States:
  - 0: INIT      (0000) - System initialization
  - 1: OBSERVE   (0001) - Passive observation mode
  - 2: ANALYZE   (0011) - Entropy analysis
  - 3: EVALUATE  (0010) - Policy evaluation
  - 4: DECIDE    (0110) - Governance decision
  - 5: ACT       (0111) - Action execution
  - 6: VERIFY    (0101) - Post-action verification
  - 7: STABILIZE (0100) - System stabilization
  - 8: REPORT    (1100) - Status reporting
  - 9: HALT      (1101) - Graceful halt

  Gray Code Sequence (single-bit transitions):
  0(0000) -> 1(0001) -> 2(0011) -> 3(0010) -> 4(0110) -> 5(0111) -> 6(0101) -> 7(0100) -> 8(1100) -> 9(1101)
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  States,           (* Set of all 10 states: 0..9 *)
  Agents,           (* Set of agent identifiers *)
  MaxTransitions    (* Bound for model checking *)

ASSUME States = 0..9
ASSUME IsFiniteSet(Agents)
ASSUME MaxTransitions \in Nat

(* Gray code encoding for each state *)
GrayCode == [
  s \in States |-> CASE s = 0 -> <<0, 0, 0, 0>>
    [] s = 1 -> <<0, 0, 0, 1>>
    [] s = 2 -> <<0, 0, 1, 1>>
    [] s = 3 -> <<0, 0, 1, 0>>
    [] s = 4 -> <<0, 1, 1, 0>>
    [] s = 5 -> <<0, 1, 1, 1>>
    [] s = 6 -> <<0, 1, 0, 1>>
    [] s = 7 -> <<0, 1, 0, 0>>
    [] s = 8 -> <<1, 1, 0, 0>>
    [] s = 9 -> <<1, 1, 0, 1>>
]

(* State names for readability *)
StateName == [
  s \in States |-> CASE s = 0 -> "INIT"
    [] s = 1 -> "OBSERVE"
    [] s = 2 -> "ANALYZE"
    [] s = 3 -> "EVALUATE"
    [] s = 4 -> "DECIDE"
    [] s = 5 -> "ACT"
    [] s = 6 -> "VERIFY"
    [] s = 7 -> "STABILIZE"
    [] s = 8 -> "REPORT"
    [] s = 9 -> "HALT"
]

(* Valid transitions: adjacent in Gray code sequence *)
ValidTransition(s, t) ==
  LET gs == GrayCode[s]
      gt == GrayCode[t]
  IN
    (* Exactly one bit differs between adjacent states *)
    \E i \in 1..4 : /
        gs[i] # gt[i]
      /\ \A j \in 1..4 : j # i => gs[j] = gt[j]

(* Valid transitions matrix *)
Transitions ==
  { <<s, t>> \in States \X States : ValidTransition(s, t) }

(* State entropy levels (simulated metric for governance decisions) *)
EntropyLevel == [
  s \in States |-> CASE s = 0 -> 0    (* INIT: no entropy *)
    [] s = 1 -> 1                     (* OBSERVE: low *)
    [] s = 2 -> 2                     (* ANALYZE: medium *)
    [] s = 3 -> 2                     (* EVALUATE: medium *)
    [] s = 4 -> 3                     (* DECIDE: high *)
    [] s = 5 -> 4                     (* ACT: critical *)
    [] s = 6 -> 3                     (* VERIFY: high *)
    [] s = 7 -> 1                     (* STABILIZE: low *)
    [] s = 8 -> 0                     (* REPORT: none *)
    [] s = 9 -> 0                     (* HALT: none *)
]

(* Maximum allowed entropy before forced stabilization *)
MaxEntropy == 4

(* Is the state a terminal state? *)
IsTerminal(s) == s = 9  (* HALT *)

(* Can transition from state s to state t? *)
CanTransition(s, t) ==
  /\ <<s, t>> \in Transitions
  /\ ~IsTerminal(s)

================================================================================
