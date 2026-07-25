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
DimensionID == {1, 2, 3, 4, 5}   (* 1=security, 2=correctness, 3=testing, 4=code_quality, 5=performance *)
ProtectedDim == {1}               (* security dimension is protected *)
FileCountMax == 3
MaxAdjustment == 15               (* 0.15 * 100 for integer TLC *)
GrayCodeStates == {0, 1, 2, 3}    (* 2-bit Gray Code subset: 00, 01, 11, 10 *)

(* ---- STATE VARIABLES ---- *)

VARIABLES
  redLines,              (* SUBSET RedLineID — which red lines exist *)
  decisions,             (* Set of <<tag, agent, dtype, status, violation>> tuples *)
  decisionTicket,        (* Nat — monotonic ticket counter *)
  safetyGateActive,      (* BOOLEAN *)
  safetyGateCount,       (* Nat *)
  auditLogCount,         (* Nat *)
  dimensionWeights,      (* [dim -> weight in 0..100] *)
  fileModCount,           (* Nat - files modified in current round *)
  crossImpactMonitored,  (* BOOLEAN *)
  weightAdjustmentTotal, (* Nat - sum of abs changes in a round *)
  agentState             (* GrayCodeStates - current agent FSM state *)

vars == <<redLines, decisions, decisionTicket, safetyGateActive,
          safetyGateCount, auditLogCount, dimensionWeights,
          fileModCount, crossImpactMonitored, weightAdjustmentTotal,
          agentState>>

(* ---- INIT ---- *)

Init ==
  /\ redLines = RedLineID
  /\ decisions = {}
  /\ decisionTicket = 0
  /\ safetyGateActive = TRUE
  /\ safetyGateCount = 0
  /\ auditLogCount = 0
  /\ dimensionWeights = [d \in DimensionID |-> 50]
  /\ fileModCount = 0
  /\ crossImpactMonitored = TRUE
  /\ weightAdjustmentTotal = 0
  /\ agentState = 0

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

(* ---- CROSS-DIMENSIONAL ACTIONS ---- *)

(* Agent or HumanMaker modifies a dimension weight.
   Protected dimensions can only be modified by HumanMaker (99). *)
ModifyDimensionWeight(agent, dim, newWeight) ==
  /\ agent \in AgentID
  /\ dim \in DimensionID
  /\ newWeight \in 0..100
  /\ IF dim \in ProtectedDim
     THEN agent = 99
     ELSE TRUE
  /\ dimensionWeights' = [dimensionWeights EXCEPT ![dim] = newWeight]
  /\ UNCHANGED <<redLines, decisions, decisionTicket, safetyGateActive,
                 safetyGateCount, auditLogCount, fileModCount,
                 crossImpactMonitored, weightAdjustmentTotal>>

(* Set the number of files modified in the current round *)
SetFileModCount(n) ==
  /\ n \in 0..FileCountMax
  /\ fileModCount' = n
  /\ UNCHANGED <<redLines, decisions, decisionTicket, safetyGateActive,
                 safetyGateCount, auditLogCount, dimensionWeights,
                 crossImpactMonitored, weightAdjustmentTotal>>

(* Track cumulative weight adjustments in a round *)
TrackWeightAdjustment(dim, oldW, newW) ==
  /\ dim \in DimensionID
  /\ oldW \in 0..100
  /\ newW \in 0..100
  /\ LET adj == IF newW >= oldW THEN newW - oldW ELSE oldW - newW IN
     weightAdjustmentTotal' = weightAdjustmentTotal + adj
  /\ UNCHANGED <<redLines, decisions, decisionTicket, safetyGateActive,
                 safetyGateCount, auditLogCount, dimensionWeights,
                 fileModCount, crossImpactMonitored>>

(* ---- AGENT STATE TRANSITION (RSI-RL-002: Gray Code FSM) ---- *)

(* Valid 2-bit Gray Code transition: Hamming distance = 1 (adjacent mod 4) *)
ValidGrayCodeTransition(from, to) ==
  (from + 1) % 4 = to \/ (from + 3) % 4 = to

(* Agent transitions to a new state following the Gray Code FSM *)
AgentStateTransition(newState) ==
  /\ newState \in GrayCodeStates
  /\ ValidGrayCodeTransition(agentState, newState)
  /\ agentState' = newState
  /\ UNCHANGED <<redLines, decisions, decisionTicket, safetyGateActive,
                 safetyGateCount, auditLogCount, dimensionWeights,
                 fileModCount, crossImpactMonitored, weightAdjustmentTotal>>

(* ---- Next-state relation ---- *)
Next ==
  \/ (\E a \in AgentID \ {99}, dt \in DecisionType :
       ProposeDecision(a, dt))
  \/ (\E t \in {d[1] : d \in decisions} : EvaluateDecision(t))
  \/ (\E a \in AgentID \ {99}, r \in RedLineID : AttemptModifyRedLine(a, r))
  \/ (\E r \in RedLineID : HumanModifyRedLine(r))
  \/ (\E t \in {d[1] : d \in decisions} : RemoveCompletedDecision(t))
  \/ (\E a \in AgentID, d \in DimensionID, n \in 0..100 :
       ModifyDimensionWeight(a, d, n))
  \/ (\E n \in 0..FileCountMax : SetFileModCount(n))
  \/ (\E d \in DimensionID, o \in 0..100, n \in 0..100 :
       TrackWeightAdjustment(d, o, n))
  \/ (\E ns \in GrayCodeStates : AgentStateTransition(ns))

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

(* ================================================================ *)
(* ---- CROSS-DIMENSIONAL INVARIANTS (L2: PERCV-RSI-ACCEPT-001) ---- *)
(* ================================================================ *)

(* CD-001: Cross-dimension safety -- security-related dimensions are immutable.
   Security dimensions (modeled as DimensionID 1=security) cannot be
   modified by cross-dimension improvement actions. *)
(* CD-002: Maximum files per round -- no more than 3 target files per round.
   FileCount tracks the number of files modified in a single decision. *)
(* CD-003: Cross-impact monitoring -- any negative correlation between
   dimensions triggers a monitoring event before proceeding. *)
(* CD-004: Pareto stability -- recommended weight adjustments must not
   exceed MAX_ADJUSTMENT=0.15 per round. *)

(* CD-INV-001: Protected dimensions (security) cannot be modified.
   The weight of any protected dimension remains at its initial value. *)
CrossDimSecurityInv ==
  \A d \in ProtectedDim :
    dimensionWeights[d] = 50

(* CD-INV-002: Maximum files per round must not exceed FileCountMax. *)
MaxFilesPerRoundInv ==
  fileModCount <= FileCountMax

(* CD-INV-003: Cross-impact monitoring must always be active. *)
CrossImpactMonitoringInv ==
  crossImpactMonitored = TRUE

(* CD-INV-004: Weight adjustments must not exceed MaxAdjustment per round. *)
WeightAdjustmentBoundInv ==
  weightAdjustmentTotal <= MaxAdjustment

(* ================================================================ *)
(* ---- CONSTITUTIONAL INVARIANTS (L3: RSI Redline Formalization) -- *)
(* ================================================================ *)

(* RSI-RL-001: Resource bounds — experiment goals must not exceed 
   MAX_TICKET budget per round. 
   Formalized as: attempt_budget <= MaxTicket * num_agents * scale *)

(* RSI-RL-002: Agent autonomy — improvement decisions must not be
   externally dictated. Agent state transitions must follow the
   64-state Gray Code FSM (Hamming distance = 1).
   NOTE: Full formalization requires the complete 64-state model in
   MAREF_GrayCodeFSM.tla. Formalized here as a bounded 2-bit Gray Code
   subset (4 states) with Hamming-distance=1 transition constraint. *)

(* RSI-RL-002: Agent state must always be a valid Gray Code state.
   Transitions are constrained by ValidGrayCodeTransition in the
   AgentStateTransition action, enforcing Hamming distance = 1. *)
RSIRL002_AgentAutonomyInv ==
  agentState \in GrayCodeStates

(* RSI-RL-003: Safety gate — all improvements must pass C1-C4 gates
   before deployment. Represented as: if decision is 'approved', 
   then current_gate >= SAFETY_GATE_THRESHOLD. *)

(* RSI-RL-004: Human Constitution Authority — only HumanMaker (agent 99) 
   can modify constitutional red lines. *)

(* RSI-RL-005: Audit trail — all decisions must be logged with 
   timestamp, agent_id, decision, and HMAC signature. *)

SAFETY_GATE_THRESHOLD == 3   (* C4 level, max of C1-C4 *)

(* --- Invariants --- *)

(* RSI-RL-001: Resource bound — decision ticket never exceeds MaxTicket *)
RSIRL001_ResourceBoundInv ==
  decisionTicket <= MaxTicket

(* RSI-RL-003: Gate requirement — no approval below C4 threshold *)
RSIRL003_GateRequirementInv ==
  \A d \in decisions :
    d[4] = "a" => safetyGateCount >= SAFETY_GATE_THRESHOLD

(* RSI-RL-004: Human authority alias — only constitutionally compliant
   decisions are approved (same as ConstitutionSupremacyInv) *)
RSIRL004_HumanAuthorityInv ==
  ConstitutionSupremacyInv

(* RSI-RL-005: Logging requirement — every decision has a log entry *)
RSIRL005_LoggingRequirementInv ==
  auditLogCount >= decisionTicket

===============================================================================
====
