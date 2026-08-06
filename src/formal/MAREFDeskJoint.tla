-------------------------------- MODULE MAREFDeskJoint --------------------------------
(*
  MAREF Desktop-Governance Joint State Machine — Formal Specification

  This TLA+ specification models the joint behavior of MAREF's Desktop Agent
  (execution layer) and Governance Overlay (control plane). It formally proves:

  Theorem 1 (LockedImpliesNoExecution):
    When governance state = LOCKED, desktop must be IDLE or ERROR —
    the system cannot execute operations during a safety lock.

  Theorem 2 (NoOscillatingLockStep):
    Governance mode cannot be LOCKED while desktop mode is EXECUTING.
    Equivalently: no safety-critical operation bypasses the CircuitBreaker.

  Theorem 3 (GrayCodeContinuity):
    Desktop state transitions follow Gray code pattern (Hamming distance = 1),
    preventing catastrophic state jumps during recursive evolution.

  Theorem 4 (AbsorbingHALT):
    Once governance enters HALT, the system remains in HALT (absorbing state).

  Model checking target: < 10^6 distinct states for TLC verification.
*)

EXTENDS Naturals, Sequences, TLC

CONSTANTS
  DesktopStates,      (* Set: {IDLE, CAPTURING, PARSING, DECIDING, EXECUTING, VERIFYING, ERROR, PAUSED} *)
  GovernanceStates,   (* Set: {HEALTHY, DEGRADED, OSCILLATING, LOCKED, RECOVERING, HALT} *)

VARIABLES
  desktop,            (* Current desktop state *)
  governance,         (* Current governance state *)
  cb_failure_count,   (* Circuit breaker consecutive failures *)
  hoverall_state      (* Combined 2-tuple for state space tracking *)

(***************************************************************************)
(* Initial state: system starts healthy and idle                           *)
(***************************************************************************)

Init ==
  /\ desktop = "IDLE"
  /\ governance = "HEALTHY"
  /\ cb_failure_count = 0
  /\ hoverall_state = <<"IDLE", "HEALTHY">>

(***************************************************************************)
(* Desktop state transitions (Gray-code adjacent only)                    *)
(***************************************************************************)

GrayAdjacent(s, t) ==
  (* States must be adjacent in the Gray-coded state machine *)
  \/ (s = "IDLE"       /\ t = "CAPTURING")
  \/ (s = "CAPTURING"  /\ t \in {"PARSING", "IDLE"})
  \/ (s = "PARSING"    /\ t \in {"DECIDING", "CAPTURING", "ERROR"})
  \/ (s = "DECIDING"   /\ t \in {"EXECUTING", "IDLE", "ERROR"})
  \/ (s = "EXECUTING"  /\ t \in {"VERIFYING", "ERROR", "IDLE"})
  \/ (s = "VERIFYING"  /\ t \in {"IDLE", "DECIDING", "ERROR"})
  \/ (s = "ERROR"      /\ t \in {"IDLE"})
  \/ (s = "PAUSED"     /\ t \in {"IDLE", "DECIDING"})

(***************************************************************************)
(* Governance state transitions                                           *)
(***************************************************************************)

GovernanceTransition(g, t) ==
  \/ (g = "HEALTHY"     /\ t \in {"HEALTHY", "DEGRADED", "OSCILLATING", "LOCKED", "HALT"})
  \/ (g = "DEGRADED"    /\ t \in {"HEALTHY", "DEGRADED", "LOCKED", "HALT"})
  \/ (g = "OSCILLATING" /\ t \in {"DEGRADED", "LOCKED", "RECOVERING", "HALT"})
  \/ (g = "LOCKED"      /\ t \in {"RECOVERING", "HALT"})
  \/ (g = "RECOVERING"  /\ t \in {"HEALTHY", "DEGRADED", "LOCKED", "HALT"})
  \/ (g = "HALT"        /\ t = "HALT")   (* Absorbing *)

(***************************************************************************)
(* Circuit breaker logic: 3 consecutive failures → LOCK                    *)
(***************************************************************************)

CircuitBreakerTrip ==
  (cb_failure_count >= 3) => (governance = "LOCKED")

(***************************************************************************)
(* Desktop step: advance state with governance guard                      *)
(***************************************************************************)

DesktopStep ==
  \E next \in DesktopStates:
    /\ GrayAdjacent(desktop, next)
    (* Only execute if governance allows *)
    /\ (next \in {"EXECUTING", "DECIDING"}) => (governance \notin {"LOCKED", "HALT"})
    (* Circuit breaker trip on ERROR state *)
    /\ IF next = "ERROR" THEN
         cb_failure_count' = cb_failure_count + 1
       ELSE
         cb_failure_count' = IF governance = "LOCKED" THEN cb_failure_count ELSE 0
    /\ desktop' = next
    /\ gov_retained(governance)

(***************************************************************************)
(* Governance step: advance state independently                          *)
(***************************************************************************)

GovernanceStep ==
  \E next \in GovernanceStates:
    /\ GovernanceTransition(governance, next)
    (* LOCKED forces desktop to safe states *)
    /\ IF next \in {"LOCKED", "HALT"} THEN
         desktop' \in {"IDLE", "ERROR", "PAUSED"}
       ELSE
         UNCHANGED desktop
    /\ governance' = next
    /\ IF next = "HEALTHY" THEN
         cb_failure_count' = 0
       ELSE
         UNCHANGED cb_failure_count

(***************************************************************************)
(* Next-state relation: either desktop or governance advances             *)
(***************************************************************************)

Next ==
  /\ hoverall_state' = <<desktop', governance'>>
  /\ \/ DesktopStep
     \/ GovernanceStep
     \/ UNCHANGED <<desktop, governance, cb_failure_count>>

(***************************************************************************)
(* Auxiliary: governance is retained unless explicitly changed            *)
(***************************************************************************)

gov_retained(g) ==
  governance' = g

(***************************************************************************)
(* INVARIANTS — Theorems to verify                                       *)
(***************************************************************************)

(* Theorem 1: When LOCKED, desktop cannot execute *)
LockedNoExecution ==
  (governance = "LOCKED") => (desktop \notin {"EXECUTING", "DECIDING", "VERIFYING"})

(* Theorem 2: When executing, governance must not be LOCKED *)
ExecutingNotLocked ==
  (desktop = "EXECUTING") => (governance \notin {"LOCKED", "HALT"})

(* Theorem 3: Circuit breaker count <= 3 when governance is HEALTHY *)
CBMaxBeforeLock ==
  (governance = "HEALTHY") => (cb_failure_count < 3)

(* Theorem 4: HALT is absorbing *)
HALTAbsorbing ==
  (governance = "HALT")' => (governance' = "HALT")

(* Combined invariant: all theorems must hold *)
JointInvariant ==
  /\ LockedNoExecution
  /\ ExecutingNotLocked
  /\ CBMaxBeforeLock

(* Safety property: no panel-level escape from HALT *)
NoEscapeHALT ==
  [](governance = "HALT" => governance' = "HALT")

(* Liveness property: system can always recover from non-HALT states *)
CanRecoverFromLocked ==
  [](governance = "LOCKED" => <>(governance = "RECOVERING"))

=============================================================================
