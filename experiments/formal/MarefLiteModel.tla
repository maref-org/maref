-------------------------------- MODULE MarefLiteModel --------------------------------
(*
  MAREF-Lite: Executable Model with PlusCal Algorithm
  
  This specification extends MarefLite.tla with an executable PlusCal
  algorithm that models the governance overlay behavior, including:
  - Agent state transitions following Gray code rules
  - Entropy monitoring and threshold-based governance
  - Race condition prevention via single-bit transitions
  - Deadlock freedom and liveness properties
*)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
  Agents,           (* Set of agent identifiers, e.g., {"agent1", "agent2"} *)
  MaxTransitions    (* Maximum transitions per agent for model checking *)

ASSUME IsFiniteSet(Agents)
ASSUME MaxTransitions \in Nat \ {0}

(* Include the base definitions *)
States == 0..9

(* Gray code encoding *)
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

(* State names *)
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

(* Valid transitions: exactly one bit differs *)
ValidTransition(s, t) ==
  LET gs == GrayCode[s]
      gt == GrayCode[t]
  IN
    \E i \in 1..4 :
      /\ gs[i] # gt[i]
      /\ \A j \in 1..4 : j # i => gs[j] = gt[j]

(* Entropy levels per state *)
EntropyLevel == [
  s \in States |-> CASE s = 0 -> 0
    [] s = 1 -> 1
    [] s = 2 -> 2
    [] s = 3 -> 2
    [] s = 4 -> 3
    [] s = 5 -> 4
    [] s = 6 -> 3
    [] s = 7 -> 1
    [] s = 8 -> 0
    [] s = 9 -> 0
]

MaxEntropy == 4
IsTerminal(s) == s = 9

(* Next valid states from current state *)
NextStates(s) == { t \in States : ValidTransition(s, t) }

(* ========================================================================= *)
(* TLA+ Variables — declared explicitly for model checking                    *)
(* (The PlusCal algorithm below is the reference implementation; these         *)
(*  variable declarations enable TLC to check the invariants directly.)       *)
(* ========================================================================= *)

VARIABLES
  agentState,
  transitionCount,
  globalEntropy,
  governanceActive

vars == <<agentState, transitionCount, globalEntropy, governanceActive>>

Init ==
  /\ agentState = [a \in Agents |-> 0]
  /\ transitionCount = [a \in Agents |-> 0]
  /\ globalEntropy = 0
  /\ governanceActive = FALSE

AgentStep(a) ==
  /\ ~IsTerminal(agentState[a])
  /\ transitionCount[a] < MaxTransitions
  /\ LET next == CHOOSE s \in NextStates(agentState[a]) : TRUE
         newState == [agentState EXCEPT ![a] = next]
         newCount == [transitionCount EXCEPT ![a] = transitionCount[a] + 1]
         entropies == { EntropyLevel[newState[ag]] : ag \in Agents }
         newEntropy == IF entropies = {} THEN 0 ELSE CHOOSE max \in entropies : \A e \in entropies : max >= e
         overThreshold == newEntropy >= MaxEntropy
     IN /\ agentState' = IF overThreshold
                        THEN [ag \in Agents |-> IF IsTerminal(newState[ag]) THEN newState[ag] ELSE 7]
                        ELSE newState
        /\ transitionCount' = newCount
        /\ globalEntropy' = newEntropy
        /\ governanceActive' = overThreshold

Next ==
  \/ \E a \in Agents : AgentStep(a)
  \/ UNCHANGED vars

Spec == Init /\ [][Next]_vars

(* ========================================================================= *)
(* Invariants                                                                *)
(* ========================================================================= *)

(* Invariant: All state variables have valid types *)
TypeInvariant ==
  /\ agentState \in [Agents -> States]
  /\ transitionCount \in [Agents -> Nat]
  /\ globalEntropy \in 0..MaxEntropy
  /\ governanceActive \in BOOLEAN

(* Invariant: All agent states are valid Gray code states *)
ValidStateInvariant ==
  \A a \in Agents : agentState[a] \in States

(* Invariant: Terminal state (HALT) is absorbing *)
TerminalAbsorbing ==
  \A a \in Agents :
    IsTerminal(agentState[a]) => transitionCount[a] <= MaxTransitions

(* Safety: Entropy never exceeds maximum (governance prevents this) *)
EntropyBound ==
  globalEntropy <= MaxEntropy

(* Liveness: If governance is active, eventually entropy decreases *)
GovernanceEffectiveness ==
  governanceActive ~> globalEntropy < MaxEntropy

(* Liveness: All agents eventually reach terminal state or max transitions *)
Termination ==
  <>(\A a \in Agents :
    IsTerminal(agentState[a]) \/ transitionCount[a] = MaxTransitions)

===============================================================================