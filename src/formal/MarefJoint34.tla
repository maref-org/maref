----------------------------- MODULE MarefJoint34 -----------------------------
(*
  MAREF 34-State Joint FSM: 10-State Governance + 24-State Agent

  This TLA+ specification models the joint state space of the governance
  and agent state machines. The joint state is a tuple <<gov_state, agent_state>>.

  Cross-layer invariants:
  - Gov HALT => all agents must be TERMINATED or ZOMBIE
  - Gov STABILIZE => no agents in CONFLICTING
  - Gov ACT => at least one agent in EXECUTING
  - Agent ZOMBIE => Gov must be in ANALYZE or higher entropy

  The joint space has 10 * 24 = 240 possible states (before Gray code constraints).
  With symmetry reduction, the reachable state space is much smaller.
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  GovStates,        (* 0..9 *)
  AgentStates,       (* 0..23 *)
  Agents,            (* Set of agent identifiers *)
  MaxTransitions

ASSUME GovStates = 0..9
ASSUME AgentStates = 0..23
ASSUME IsFiniteSet(Agents)
ASSUME MaxTransitions \in Nat

(* ── Import 10-state governance Gray code ── *)
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

(* ── Import 24-state agent Gray code ── *)
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

(* ── Governor state: which FSM can transition next ── *)
GovGovernor == {0, 1}  (* 0 = governance moves, 1 = agent moves *)

(* ── Valid governance transitions (from MarefLite) ── *)
GovTransition(s, t) ==
  LET gs == GovGray[s]  gt == GovGray[t] IN
  \E i \in 1..4 : /\ gs[i] # gt[i] /\ \A j \in 1..4 : j # i => gs[j] = gt[j]

(* ── Valid agent transitions (from MarefAgent24) ── *)
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

(* ── Joint state ── *)
JointState == GovStates \X AgentStates

(* ── Cross-layer safety invariants ── *)

(* SJ-001: Gov HALT => all agents must be TERMINATED(22) or ZOMBIE(23) *)
HaltImpliesAgentsDead ==
  \A <<gov, agent>> \in JointState :
    gov = 9 => (agent = 22 \/ agent = 23)

(* SJ-002: Gov STABILIZE(7) => no agents in CONFLICTING(12) *)
StabilizeImpliesNoConflict ==
  \A <<gov, agent>> \in JointState :
    gov = 7 => agent # 12

(* SJ-003: Gov ACT(5) => at least one agent in EXECUTING(8) *)
ActImpliesExecuting ==
  \E <<gov, agent>> \in JointState :
    gov = 5 /\ agent = 8

(* SJ-004: Gov HALT is absorbing for both FSMs *)
HaltGovAbsorbing ==
  \A g \in GovStates : GovTransition(9, g) => g = 9

(* SJ-005: Agent ZOMBIE(23) implies Gov entropy >= 2 (ANALYZE or higher) *)
ZombieImpliesGovAnalyzed ==
  \A <<gov, agent>> \in JointState :
    agent = 23 => gov >= 2

(* SJ-006: Agent TERMINATED(22) cannot re-enter lifecycle *)
TerminatedImmutability ==
  \A <<gov, agent>> \in JointState :
    agent = 22 => \A t \in AgentStates : ~AgentTransition(22, t)

(* SJ-007: Gov HALT(9) is terminal for joint state — no joint transitions possible *)
HaltJointAbsorbing ==
  \A <<gov, agent>> \in JointState :
    gov = 9 => ~\E t \in AgentStates : AgentTransition(agent, t)

(* ── Collective invariant ── *)
CrossLayerInvariants ==
  /\ HaltImpliesAgentsDead
  /\ StabilizeImpliesNoConflict
  /\ ActImpliesExecuting
  /\ HaltGovAbsorbing
  /\ ZombieImpliesGovAnalyzed
  /\ TerminatedImmutability
  /\ HaltJointAbsorbing

===============================================================================
