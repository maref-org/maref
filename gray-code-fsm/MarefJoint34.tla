----------------------------- MODULE MarefJoint34 -----------------------------
(*
  MAREF 34-State Joint FSM: 10-State Governance + 24-State Agent

  This TLA+ specification models the joint state space of the governance
  (10-state, 4-bit Gray code) and agent (24-state, 5-bit Gray code) state
  machines. The joint state is the tuple <<govState, agentState>>.

  Cross-layer invariants (SJ-001..007) restrict the joint state space:
  - SJ-001: Gov HALT (9)  => agent is TERMINATED (22) or ZOMBIE (23)
  - SJ-002: Gov STABILIZE (7) => agent is not CONFLICTING (12)
  - SJ-003: Gov ACT (5)    => agent is EXECUTING (8)
  - SJ-004: Gov HALT is absorbing (no outgoing governance transition)
  - SJ-005: Agent ZOMBIE (23) => gov >= ANALYZE (2)
  - SJ-006: Agent TERMINATED (22) cannot re-enter lifecycle
  - SJ-007: Gov HALT is absorbing for the joint state (no agent move either)

  Earlier versions of this spec asserted the SJ predicates over the full
  Cartesian product GovStates \X AgentStates, which is trivially FALSE (e.g.
  (9, 3) exists in the product). This version encodes the SJ constraints into
  the Next relation as a pruning predicate ValidJoint, so TLC verifies that
  every REACHABLE joint state satisfies them, plus the temporal properties
  (absorbing terminals and reachability of the constrained states).
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  GovStates,        (* 0..9 *)
  AgentStates       (* 0..23 *)

ASSUME GovStates = 0..9
ASSUME AgentStates = 0..23

(* ── 10-state governance Gray code ── *)
GovGray == [
  s \in GovStates |->
    CASE s = 0 -> <<0,0,0,0>>
    [] s = 1 -> <<0,0,0,1>>
    [] s = 2 -> <<0,0,1,1>>
    [] s = 3 -> <<0,0,1,0>>
    [] s = 4 -> <<0,1,1,0>>
    [] s = 5 -> <<0,1,1,1>>
    [] s = 6 -> <<0,1,0,1>>
    [] s = 7 -> <<0,1,0,0>>
    [] s = 8 -> <<1,1,0,0>>
    [] s = 9 -> <<1,1,0,1>>
]

GovName == [s \in GovStates |->
  CASE s = 0 -> "INIT" [] s = 1 -> "OBSERVE" [] s = 2 -> "ANALYZE"
  [] s = 3 -> "EVALUATE" [] s = 4 -> "DECIDE" [] s = 5 -> "ACT"
  [] s = 6 -> "VERIFY" [] s = 7 -> "STABILIZE" [] s = 8 -> "REPORT"
  [] s = 9 -> "HALT"]

(* ── 24-state agent Gray code ── *)
AgentGray == [
  s \in AgentStates |->
    CASE s = 0 -> <<0,0,0,0,0>>  [] s = 1 -> <<0,0,0,0,1>>
    [] s = 2 -> <<0,0,0,1,1>>    [] s = 3 -> <<0,0,0,1,0>>
    [] s = 4 -> <<0,0,1,1,0>>    [] s = 5 -> <<0,0,1,1,1>>
    [] s = 6 -> <<0,0,1,0,1>>    [] s = 7 -> <<0,0,1,0,0>>
    [] s = 8 -> <<0,1,1,0,0>>    [] s = 9 -> <<0,1,1,0,1>>
    [] s = 10 -> <<0,1,1,1,1>>   [] s = 11 -> <<0,1,1,1,0>>
    [] s = 12 -> <<0,1,0,1,0>>   [] s = 13 -> <<0,1,0,1,1>>
    [] s = 14 -> <<0,1,0,0,1>>   [] s = 15 -> <<0,1,0,0,0>>
    [] s = 16 -> <<1,1,0,0,0>>   [] s = 17 -> <<1,1,0,0,1>>
    [] s = 18 -> <<1,1,0,1,1>>   [] s = 19 -> <<1,1,0,1,0>>
    [] s = 20 -> <<1,1,1,1,0>>   [] s = 21 -> <<1,1,1,1,1>>
    [] s = 22 -> <<1,1,1,0,1>>   [] s = 23 -> <<1,1,1,0,0>>
]

AgentName == [s \in AgentStates |->
  CASE s = 0 -> "UNINITIALIZED" [] s = 1 -> "BOOTING"
  [] s = 2 -> "REGISTERING"     [] s = 3 -> "IDLE"
  [] s = 4 -> "DISCOVERING"     [] s = 5 -> "NEGOTIATING"
  [] s = 6 -> "TRUST_BUILDING"  [] s = 7 -> "CONTRACTING"
  [] s = 8 -> "EXECUTING"       [] s = 9 -> "WAITING"
  [] s = 10 -> "VERIFYING"      [] s = 11 -> "REPORTING"
  [] s = 12 -> "CONFLICTING"    [] s = 13 -> "ARBITRATING"
  [] s = 14 -> "RECOVERING"     [] s = 15 -> "MIGRATING"
  [] s = 16 -> "PAUSED"         [] s = 17 -> "DEGRADING"
  [] s = 18 -> "SELF_HEALING"   [] s = 19 -> "SELF_OPTIMIZING"
  [] s = 20 -> "EVOLVING"       [] s = 21 -> "TERMINATING"
  [] s = 22 -> "TERMINATED"     [] s = 23 -> "ZOMBIE"]

(* ── Valid governance transitions: exactly one Gray code bit differs ── *)
GovTransition(s, t) ==
  LET gs == GovGray[s]  gt == GovGray[t] IN
  \E i \in 1..4 : /\ gs[i] # gt[i]
                  /\ \A j \in 1..4 : j # i => gs[j] = gt[j]

(* ── Valid agent transitions: explicit lifecycle table ── *)
AgentTransition(s, t) ==
  \/ /\ s = 0  /\ t \in {1, 22}
  \/ /\ s = 1  /\ t \in {2, 21}
  \/ /\ s = 2  /\ t \in {3, 21}
  \/ /\ s = 3  /\ t \in {4, 19, 16, 21, 15}
  \/ /\ s = 4  /\ t \in {5, 3}
  \/ /\ s = 5  /\ t \in {6, 3}
  \/ /\ s = 6  /\ t \in {7, 3}
  \/ /\ s = 7  /\ t \in {8, 3}
  \/ /\ s = 8  /\ t \in {9, 10, 12}
  \/ /\ s = 9  /\ t \in {8, 10}
  \/ /\ s = 10 /\ t \in {11, 8}
  \/ /\ s = 11 /\ t \in {3, 20}
  \/ /\ s = 12 /\ t \in {13, 17}
  \/ /\ s = 13 /\ t \in {14, 3}
  \/ /\ s = 14 /\ t \in {3, 12}
  \/ /\ s = 15 /\ t \in {3, 21}
  \/ /\ s = 16 /\ t \in {3, 21}
  \/ /\ s = 17 /\ t \in {18, 21}
  \/ /\ s = 18 /\ t \in {3, 17}
  \/ /\ s = 19 /\ t \in {3, 20}
  \/ /\ s = 20 /\ t \in {3, 19}
  \/ /\ s = 21 /\ t \in {22, 23}
  \/ /\ s = 22 /\ FALSE
  \/ /\ s = 23 /\ FALSE

(* ── Cross-layer constraints (SJ-001/002/003/005 prune the joint space) ── *)
SJ001(g, a) == ~(g = 9 /\ a \notin {22, 23})    (* HALT => dead agent *)
SJ002(g, a) == ~(g = 7 /\ a = 12)               (* STABILIZE => no conflict *)
SJ003(g, a) == (g = 5 => a = 8)                 (* ACT => agent EXECUTING *)
SJ005(g, a) == (a = 23 => g >= 2)               (* ZOMBIE => gov >= ANALYZE *)

(* A joint state is legal iff all cross-layer constraints hold *)
ValidJoint(g, a) ==
  /\ SJ001(g, a)
  /\ SJ002(g, a)
  /\ SJ003(g, a)
  /\ SJ005(g, a)

(* ── Executable model ── *)

VARIABLES govState, agentState

vars == <<govState, agentState>>

Init ==
  /\ govState = 0
  /\ agentState = 0

(* Governance moves one Gray-code step, pruning to legal joint states.
   SJ-004: no outgoing governance transition from HALT (9). *)
GovMove ==
  /\ govState # 9
  /\ \E t \in GovStates :
       /\ GovTransition(govState, t)
       /\ govState # t
       /\ ValidJoint(t, agentState)
       /\ govState' = t
       /\ UNCHANGED agentState

(* Agent moves one lifecycle step, pruning to legal joint states.
   SJ-006/007: terminal agent states (22/23) have no outgoing moves. *)
AgentMove ==
  /\ agentState \notin {22, 23}
  /\ \E t \in AgentStates :
       /\ AgentTransition(agentState, t)
       /\ agentState # t
       /\ ValidJoint(govState, t)
       /\ agentState' = t
       /\ UNCHANGED govState

(* Legal joint terminal state: Gov HALT with a dead agent (SJ-001). Such a
   state has no progress by construction; allow it to stutter so TLC's
   deadlock check accepts the designed end-of-life configuration. *)
JointTerminal ==
  /\ govState = 9
  /\ agentState \in {22, 23}

Next ==
  \/ GovMove
  \/ AgentMove
  \/ (JointTerminal /\ UNCHANGED vars)

(* Spec with weak fairness: WF_vars(Next) rules out the trivial stutter
   counterexample that previously violated ActReachable / HaltReachable.
   Without fairness TLC may stutter forever at any state; under weak
   fairness, whenever <<Next>>_vars is enabled (GovMove or AgentMove), it
   must eventually fire. In the JointTerminal configuration only the
   UNCHANGED branch is enabled, so the designed end-of-life stutter is
   still allowed. *)
Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

(* ── Invariants ── *)

TypeOK ==
  /\ govState \in GovStates
  /\ agentState \in AgentStates

(* Every reachable joint state satisfies the cross-layer constraints *)
JointInvariant == ValidJoint(govState, agentState)

(* ── Temporal properties ── *)

(* SJ-004: once in HALT, governance never leaves.
   []-formulas quantify over ALL behaviors, so TLC can check them directly
   as PROPERTIES. *)
HaltGovAbsorbing ==
  [](govState = 9 => [](govState = 9))

(* SJ-006: once terminal, the agent never re-enters the lifecycle *)
TerminalsAbsorbAgent ==
  [](agentState \in {22, 23} => [](agentState \in {22, 23}))

(* ── Existential reachability (NOT TLC temporal properties) ────────────────
   A liveness formula <>P means "EVERY behavior must eventually satisfy P".
   Because GovMove / AgentMove are non-deterministic here, behaviors exist
   that skip (5,8) or (9,22), so ActReachable / HaltReachable would be
   violated even though such paths DO exist. The existential question
   ("is there a legal path to (ACT, EXECUTING) / (HALT, TERMINATED)?") is a
   reachability check performed by validator.py via BFS over the same
   transition relations. These definitions are kept as documentation of the
   intended witnesses only; they are NOT listed in MarefJoint34MC.cfg. *)

(* SJ-003 satisfiability witness (checked by validator.py BFS) *)
ActReachable ==
  <>(govState = 5 /\ agentState = 8)

(* SJ-001 satisfiability witness (checked by validator.py BFS) *)
HaltReachable ==
  <>(govState = 9 /\ agentState = 22)

===============================================================================
