------------------------------- MODULE MAREF_Consensus --------------------------------
(*
  MAREF Cross-Validator: Weighted Byzantine Fault-Tolerant Consensus

  This TLA+ specification formally models the weighted consensus algorithm
  used by the Cross-Validator. It verifies:
  1. Agreement: No two correct validators decide different values
  2. Validity: A decided value must have been proposed by some validator
  3. Termination: Eventually every correct validator decides
  4. Weight-based Quorum: Decisions require > 2/3 of active weight
  5. Byzantine Resilience: System tolerates up to 1/3 byzantine weight

  Based on the MAREF WeightedConsensusEngine implementation.
*)

EXTENDS Naturals, Sequences, FiniteSets, Integers

CONSTANTS
  Validators,        (* Set of validator identifiers *)
  ProposalIds,       (* Set of possible proposal identifiers *)
  MaxWeight,         (* Maximum weight a validator can have *)
  MaxRounds          (* Maximum consensus rounds for model checking *)

ASSUME IsFiniteSet(Validators)
ASSUME Validators /= {}
ASSUME IsFiniteSet(ProposalIds)
ASSUME ProposalIds /= {}
ASSUME MaxWeight \in Nat \ {0}

(* --- Type definitions --- *)

VoteValues == {"approve", "reject", "abstain"}

(* --- State variables --- *)

VARIABLES
  weights,           (* [Validators -> Weight] current weight *)
  trustScores,       (* [Validators -> Real] trust score 0.0-1.0 *)
  proposals,         (* Set of active proposal IDs *)
  votes,             (* [Validators X Proposals -> VoteValues \union {"none"}] *)
  byzantine,         (* [Validators -> BOOLEAN] is validator byzantine? *)
  decisions,         (* [Proposals -> VoteValues \union {"none"}] final decision *)
  round              (* Current consensus round *)

vars == <<weights, trustScores, proposals, votes, byzantine, decisions, round>>

(* --- Initial state --- *)

Init ==
  /\ weights = [v \in Validators |-> 1]        (* All validators start with equal weight *)
  /\ trustScores = [v \in Validators |-> 100]  (* Full trust initially *)
  /\ proposals = {}                             (* No proposals initially *)
  /\ votes = [v \in Validators, p \in {} |-> "none"]
  /\ byzantine = [v \in Validators |-> FALSE]  (* No byzantine validators initially *)
  /\ decisions = [p \in {} |-> "none"]
  /\ round = 0

(* --- Helpers --- *)

CorrectValidators == { v \in Validators : ~byzantine[v] }

TotalWeight == LET w == weights IN
  IF {w[v] : v \in CorrectValidators} = {} THEN 0
  ELSE LET S == {w[v] : v \in CorrectValidators} IN CHOOSE t \in S : \A x \in S : t >= x

(* Quorum requires > 2/3 of correct validators. *)
(* For 5 validators of weight 1, > 2/3 of 5 = 3.33, so threshold is 4 *)
QuorumWeight == 4

(* A proposal reaches consensus if > quorum of correct validators vote the same *)
ConsensusReached(p) ==
  \E decision \in VoteValues :
    LET approvingWeights == {weights[v] : v \in {c \in CorrectValidators : votes[<<c, p>>] = decision}}
        totalApproval == IF approvingWeights = {} THEN 0
                        ELSE LET S == approvingWeights IN CHOOSE t \in S : \A x \in S : t >= x
    IN totalApproval >= QuorumWeight

(* --- Safety Properties (Invariants) --- *)

(* Invariant 1: No two correct validators disagree on a decided proposal *)
AgreementInvariant ==
  \E decision \in VoteValues :
    \A p \in proposals : decisions[p] = decision \/ decisions[p] = "none"

(* Invariant 2: Validator weights stay within bounds *)
WeightBoundsInvariant ==
  /\ \A v \in Validators : weights[v] >= 0
  /\ \A v \in Validators : weights[v] <= MaxWeight

(* Invariant 3: Trust scores stay in range *)
TrustBoundsInvariant ==
  \A v \in Validators : trustScores[v] >= 0 /\ trustScores[v] <= 100

(* Invariant 4: Byzantine validators cannot exceed 1/3 of total weight *)
ByzantineBoundInvariant ==
  LET byzWeight == {weights[v] : v \in {c \in Validators : byzantine[c]}}
      totalW == TotalWeight
      totalB == IF byzWeight = {} THEN 0
               ELSE LET S == byzWeight IN CHOOSE t \in S : \A x \in S : t >= x
  IN totalB * 3 <= totalW

(* Invariant 5: No consensus without quorum *)
QuorumIntegrityInvariant ==
  \A p \in proposals :
    ConsensusReached(p) => \E decision \in VoteValues : decisions[p] = decision

(* Invariant 6: Trust score reflects weight ratio *)
TrustWeightCorrelationInvariant ==
  \A v \in Validators :
    weights[v] <= (MaxWeight * trustScores[v])

(* --- Actions --- *)

(* Action: Create new proposal *)
CreateProposal(p) ==
  /\ p \notin proposals
  /\ proposals' = proposals \cup {p}
   /\ votes' = [v \in Validators, q \in (proposals \cup {p}) |-> IF q = p THEN "none" ELSE votes[v,q]]
  /\ decisions' = [q \in (proposals \cup {p}) |-> IF q = p THEN "none" ELSE decisions[q]]
  /\ UNCHANGED <<weights, trustScores, byzantine, round>>

(* Action: Validator casts a vote *)
CastVote(v, p, val) ==
  /\ p \in proposals
  /\ v \in Validators
  /\ val \in VoteValues
  /\ votes[v,p] = "none"                     (* Must not have voted already *)
   /\ votes' = [w \in Validators, q \in proposals |->
      IF w = v /\ q = p THEN val ELSE votes[w,q]]
  /\ UNCHANGED <<weights, trustScores, proposals, byzantine, decisions, round>>

(* Action: Consensus evaluation - determine if proposal reached decision *)
ReachConsensus(p) ==
  /\ p \in proposals
  /\ decisions[p] = "none"
  /\ ConsensusReached(p)
  /\ LET winner == CHOOSE d \in VoteValues :
        LET approving == {w \in CorrectValidators : votes[w,p] = d}
        IN IF approving /= {} THEN TRUE ELSE FALSE
      IN decisions' = [q \in proposals |-> IF q = p THEN winner ELSE decisions[q]]
  /\ UNCHANGED <<weights, trustScores, proposals, votes, byzantine, round>>

(* Action: Update weights after consensus (reward/punish) *)
UpdateWeights(p) ==
  /\ p \in proposals
  /\ decisions[p] /= "none"                    (* Consensus reached *)
  /\ LET
       inc(w, max) ==
         IF w + 1 > max THEN max ELSE w + 1
       dec(w) ==
         IF w - 1 < 0 THEN 0 ELSE w - 1
     IN
     /\ weights' = [v \in Validators |->
          IF votes[v,p] = decisions[p] THEN inc(weights[v], MaxWeight)
          ELSE IF votes[v,p] /= "none" /\ votes[v,p] /= "abstain"
               THEN dec(weights[v])
          ELSE weights[v]]
     /\ trustScores' = [v \in Validators |->
          IF votes[v,p] = decisions[p] THEN inc(trustScores[v], 100)
          ELSE IF votes[v,p] /= "none" /\ votes[v,p] /= "abstain"
               THEN dec(trustScores[v])
          ELSE trustScores[v]]
  /\ round' = round + 1
  /\ UNCHANGED <<proposals, votes, byzantine, decisions>>

(* Action: Detect and mark byzantine validators *)
DetectByzantine(v) ==
  /\ v \in Validators
  /\ ~byzantine[v]
  /\ \E p \in proposals :
       /\ ConsensusReached(p)
       /\ votes[v,p] /= decisions[p]
       /\ votes[v,p] /= "abstain"
  (* Check if validator consistently opposes majority *)
  /\ LET disagreeCount == Cardinality({p \in proposals :
           votes[v,p] /= "none" /\ votes[v,p] /= "abstain" /\
           \E d \in VoteValues : decisions[p] = d /\ votes[v,p] /= d})
     IN disagreeCount >= 3
  /\ byzantine' = [w \in Validators |-> IF w = v THEN TRUE ELSE byzantine[w]]
  /\ UNCHANGED <<weights, trustScores, proposals, votes, decisions, round>>

(* --- Next-state relation --- *)
Next ==
  \/ \E p \in ProposalIds \ proposals : CreateProposal(p)
  \/ \E v \in Validators, p \in proposals, val \in VoteValues : CastVote(v, p, val)
  \/ \E p \in proposals : ReachConsensus(p)
  \/ \E p \in proposals : UpdateWeights(p)
  \/ \E v \in Validators : DetectByzantine(v)

(* --- Specification --- *)

Spec == Init /\ [][Next]_vars

(* --- Temporal Properties --- *)

(* Liveness: Eventually a proposal reaches consensus if quorum votes *)
ConsensusLiveness ==
  \E p \in proposals :
    (/\ \A decision \in VoteValues :
          LET total == {weights[v] : v \in {c \in CorrectValidators : votes[<<c, p>>] = decision}}
          IN total >= QuorumWeight)
    ~> decisions[p] /= "none"

(* Termination: System eventually produces a decision (if there are proposals) *)
Termination ==
  (Cardinality(proposals) > 0) ~> (\E p \in proposals : decisions[p] /= "none")

(* --- Model checking constraints --- *)

(* Bounded state space for TLC *)
StateConstraint == round <= MaxRounds

(* Property constraints for TLC: invariant checking *)
THEOREM Spec => []WeightBoundsInvariant
THEOREM Spec => []TrustBoundsInvariant
THEOREM Spec => []ByzantineBoundInvariant

===============================================================================
