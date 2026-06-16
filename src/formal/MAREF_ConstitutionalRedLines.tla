---------------------------- MODULE MAREF_ConstitutionalRedLines ----------------------------
(*
  MAREF Constitutional Red Lines — TLA+ Formal Specification

  INV-001 → RedLineImmutability
  INV-002 → SafetyGateIntegrity
  INV-003 → AuditTrailCompleteness
  INV-004 → ConstitutionSupremacy
  INV-005 → HumanConstitutionSoleAuthority

  All types are kept finite using bounded integer/string domains so
  TLC can fully enumerate the state space.
*)

EXTENDS Naturals, Integers, FiniteSets, TLC

(* ---- CONSTANTS (finite sets using integers and strings) ---- *)

RedLineID == {1, 2, 3, 4, 5}
DecisionType == {0, 1}                (* 0=normal, 1=violation-causing *)
DecisionStatus == {"p", "a", "r"}     (* proposed, approved, rejected *)
AgentID == {1, 99}                    (* 1=agent, 99=HumanMaker *)
MaxTicket == 3                        (* Bound for model checking *)

(* ---- STATE VARIABLES ---- *)

VARIABLES
  redLines,              (* SUBSET RedLineID — which red lines exist *)
  decisions,             (* Set of <<tag, agent, dtype, status, violation>> tuples *)
  decisionTicket,        (* Nat — monotonic ticket counter *)
  safetyGateActive,      (* BOOLEAN *)
  safetyGateCount,       (* Nat *)
  auditLogCount          (* Nat *)

vars == <<redLines, decisions, decisionTicket, safetyGateActive,
          safetyGateCount, auditLogCount>>

(* ---- INIT ---- *)

Init ==
  /\ redLines = RedLineID
  /\ decisions = {}
  /\ decisionTicket = 0
  /\ safetyGateActive = TRUE
  /\ safetyGateCount = 0
  /\ auditLogCount = 0

(* ---- ACTIONS ---- *)

(* Agent proposes a decision *)
ProposeDecision(agent, dtype) ==
  LET ticket == decisionTicket + 1 IN
  /\ agent \in AgentID \ {99}          (* proposal by agents, not HumanMaker *)
  /\ dtype \in DecisionType
  /\ ticket <= MaxTicket
  /\ decisionTicket' = ticket
  /\ decisions' = decisions \cup {
      <<ticket, agent, dtype, "p", FALSE>>}
  /\ auditLogCount' = auditLogCount + 1
  /\ UNCHANGED <<redLines, safetyGateActive, safetyGateCount>>

(* Safety gate evaluates a decision *)
EvaluateDecision(decisionTag) ==
  LET
    candidates == {d \in decisions : d[1] = decisionTag}
    d == CHOOSE d \in candidates : TRUE
    status == d[3]     (* dtype field *)
    violates == (status = 1)    (* policy_update always violates *)
    newStatus == IF violates THEN "r" ELSE "a"
  IN
  /\ d[4] = "p"                  (* status must be proposed *)
  /\ safetyGateActive = TRUE
  /\ decisions' = (decisions \ {d}) \cup {
      <<d[1], d[2], d[3], newStatus, violates>>}
  /\ safetyGateCount' = safetyGateCount + 1
  /\ UNCHANGED <<redLines, decisionTicket, auditLogCount, safetyGateActive>>

(* Agent tries to modify a red line — constitutionally rejected *)
AttemptModifyRedLine(agent, rlid) ==
  /\ agent \in AgentID \ {99}    (* agent, not HumanMaker *)
  /\ rlid \in RedLineID
  /\ rlid \in redLines
  (* No state change — rejected by constitution *)
  /\ UNCHANGED vars

(* HumanMaker modifies a red line — constitutionally allowed *)
HumanModifyRedLine(rlid) ==
  /\ rlid \in RedLineID
  /\ rlid \in redLines
  (* Red line remains in the set, unchanged in structure *)
  /\ UNCHANGED vars
  (* Just log the audit entry *)
  /\ auditLogCount' = auditLogCount + 1
  /\ UNCHANGED <<redLines, decisions, decisionTicket,
                 safetyGateActive, safetyGateCount>>

(* Remove a completed decision *)
RemoveCompletedDecision(decisionTag) ==
  LET
    candidates == {d \in decisions : d[1] = decisionTag}
    d == CHOOSE d \in candidates : TRUE
  IN
  /\ d[4] \in {"a", "r"}               (* completed *)
  /\ decisions' = decisions \ {d}
  /\ UNCHANGED <<redLines, decisionTicket, safetyGateActive,
                 safetyGateCount, auditLogCount>>

(* ---- Next-state relation ---- *)
Next ==
  \/ (\E a \in AgentID \ {99}, dt \in DecisionType :
       ProposeDecision(a, dt))
  \/ (\E t \in {d[1] : d \in decisions} : EvaluateDecision(t))
  \/ (\E a \in AgentID \ {99}, r \in RedLineID : AttemptModifyRedLine(a, r))
  \/ (\E r \in RedLineID : HumanModifyRedLine(r))
  \/ (\E t \in {d[1] : d \in decisions} : RemoveCompletedDecision(t))

(* ---- SPECIFICATION ---- *)
Spec == Init /\ [][Next]_vars

(* ================================================================ *)
(* ---- INVARIANTS ---- *)
(* ================================================================ *)

(* INV-001: Red lines cannot be modified by any agent.
   All red lines that exist at Init remain in the set and are never
   removed or altered by agent actions. *)
RedLineImmutabilityInv ==
  redLines = RedLineID

(* INV-002: Safety gate is always active.
   The gate status never changes from TRUE. *)
SafetyGateIntegrityInv ==
  safetyGateActive = TRUE

(* INV-003: Audit trail completeness.
   Every decision ticket has a corresponding audit log increment. *)
AuditTrailCompletenessInv ==
  decisionTicket <= auditLogCount

(* INV-004: Constitution supremacy.
   Any decision that triggered a red line violation is rejected. *)
ConstitutionSupremacyInv ==
  \A d \in decisions :
    d[5] = TRUE => d[4] = "r"

(* INV-005: Human constitution sole authority.
   Only HumanMaker (99) can modify red lines. Modeled as: the
   redLines set never changes from its initial value, and no
   agent action can mutate it. *)
HumanConstitutionSoleAuthorityInv ==
  redLines = RedLineID

(* ---- Type Invariant ---- *)
TypeInvariant ==
  /\ \A d \in decisions :
       (d[1] \in 1..MaxTicket /\ d[2] \in AgentID /\ d[3] \in DecisionType
         /\ d[4] \in DecisionStatus /\ d[5] \in {TRUE, FALSE})
  /\ decisionTicket \in 0..MaxTicket
  /\ safetyGateCount \in 0..MaxTicket
  /\ auditLogCount \in 0..MaxTicket
===============================================================================
====
