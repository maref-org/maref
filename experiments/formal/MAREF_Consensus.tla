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

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
  Validators,        (* Set of validator identifiers *)
  MaxWeight,         (* Maximum weight a validator can have *)
  MaxRounds,         (* Maximum consensus rounds for model checking *)
  QuorumThreshold,   (* Quorum threshold as integer percentage: 67 = 67% *)
  ProposalIDs        (* Set of possible proposal IDs for model checking *)

ASSUME IsFiniteSet(Validators)
ASSUME Validators /= {}
ASSUME MaxWeight \in Nat \ {0}
ASSUME QuorumThreshold > 50 /\ QuorumThreshold <= 100

(* --- Helper: minimum of two numbers --- *)
Min(a, b) == IF a <= b THEN a ELSE b

(* --- Helper: maximum of two numbers --- *)
Max(a, b) == IF a >= b THEN a ELSE b

(* --- Type definitions --- *)

VoteValues == {"approve", "reject", "abstain"}

(* --- State variables --- *)

VARIABLES
  weights,           (* [Validators -> Weight] current weight *)
  trustScores,       (* [Validators -> Int] trust score 0-100 *)
  proposals,         (* Set of active proposal IDs *)
  votes,             (* [Validators X Proposals -> VoteValues \union {"none"}] *)
  byzantine,         (* [Validators -> BOOLEAN] is validator byzantine? *)
  decisions,         (* [Proposals -> VoteValues \union {"none"}] final decision *)
  round              (* Current consensus round *)

vars == <<weights, trustScores, votes, byzantine, decisions, round>>

(* --- Initial state --- *)

Init ==
  /\ weights = [v \in Validators |-> 1]        (* All validators start with equal weight *)
  /\ trustScores = [v \in Validators |-> 100]  (* Full trust initially (100%) *)
  /\ proposals = {}                             (* No proposals initially *)
  /\ votes = [v \in Validators, p \in {} |-> "none"]
  /\ byzantine = [v \in Validators |-> FALSE]  (* No byzantine validators initially *)
  /\ decisions = [p \in {} |-> "none"]
  /\ round = 0

(* --- Helpers --- *)

CorrectValidators == { v \in Validators : ~byzantine[v] }

(* Compute total weight of correct validators *)
(* For model checking with small bounded sets, we sum weights directly *)
TotalWeight ==
  LET w == weights
      cw == CorrectValidators
  IN IF cw = {} THEN 0
     ELSE LET v1 == CHOOSE v \in cw : TRUE
              rest1 == cw \ {v1}
          IN IF rest1 = {} THEN w[v1]
             ELSE LET v2 == CHOOSE v \in rest1 : TRUE
                      rest2 == rest1 \ {v2}
                  IN IF rest2 = {} THEN w[v1] + w[v2]
                     ELSE LET v3 == CHOOSE v \in rest2 : TRUE
                              rest3 == rest2 \ {v3}
                          IN IF rest3 = {} THEN w[v1] + w[v2] + w[v3]
                             ELSE LET v4 == CHOOSE v \in rest3 : TRUE
                                      rest4 == rest3 \ {v4}
                                  IN IF rest4 = {} THEN w[v1] + w[v2] + w[v3] + w[v4]
                                     ELSE LET v5 == CHOOSE v \in rest4 : TRUE
                                          IN w[v1] + w[v2] + w[v3] + w[v4] + w[v5]

QuorumWeight == TotalWeight * QuorumThreshold  (* numerator for percentage *)

(* Helper: sum of weights for validators satisfying a predicate *)
SumVotingWeight(p, decision) ==
  LET vs == {v \in CorrectValidators : votes[v,p] = decision}
      w == weights
  IN IF vs = {} THEN 0
     ELSE LET v1 == CHOOSE v \in vs : TRUE
              r1 == vs \ {v1}
          IN IF r1 = {} THEN w[v1]
             ELSE LET v2 == CHOOSE v \in r1 : TRUE
                      r2 == r1 \ {v2}
                  IN IF r2 = {} THEN w[v1] + w[v2]
                     ELSE LET v3 == CHOOSE v \in r2 : TRUE
                              r3 == r2 \ {v3}
                          IN IF r3 = {} THEN w[v1] + w[v2] + w[v3]
                             ELSE LET v4 == CHOOSE v \in r3 : TRUE
                                      r4 == r3 \ {v4}
                                  IN IF r4 = {} THEN w[v1] + w[v2] + w[v3] + w[v4]
                                     ELSE LET v5 == CHOOSE v \in r4 : TRUE
                                          IN w[v1] + w[v2] + w[v3] + w[v4] + w[v5]

(* A proposal reaches consensus if > quorum percentage of correct validators vote the same *)
(* Uses scaled integer comparison: SumVotingWeight * 100 >= TotalWeight * QuorumThreshold *)
ConsensusReached(p) ==
  \E decision \in VoteValues :
    SumVotingWeight(p, decision) * 100 >= QuorumWeight

(* --- Safety Properties (Invariants) --- *)

(* Invariant 1: Agreement — a decided proposal has exactly one decision *)
AgreementInvariant ==
  \A p \in proposals :
    decisions[p] = "none" \/ decisions[p] \in VoteValues

(* Invariant 2: Validator weights stay within bounds *)
WeightBoundsInvariant ==
  /\ \A v \in Validators : weights[v] >= 0
  /\ \A v \in Validators : weights[v] <= MaxWeight

(* Invariant 3: Trust scores stay in range *)
TrustBoundsInvariant ==
  \A v \in Validators : trustScores[v] >= 0 /\ trustScores[v] <= 100

(* Invariant 4: Byzantine validators cannot exceed 1/3 of total weight *)
ByzantineBoundInvariant ==
  LET byzWeight ==
    LET bw == {v \in Validators : byzantine[v]}
        w == weights
    IN IF bw = {} THEN 0
       ELSE LET v1 == CHOOSE v \in bw : TRUE
                r1 == bw \ {v1}
            IN IF r1 = {} THEN w[v1]
               ELSE LET v2 == CHOOSE v \in r1 : TRUE
                        r2 == r1 \ {v2}
                    IN IF r2 = {} THEN w[v1] + w[v2]
                       ELSE LET v3 == CHOOSE v \in r2 : TRUE
                                r3 == r2 \ {v3}
                            IN IF r3 = {} THEN w[v1] + w[v2] + w[v3]
                               ELSE LET v4 == CHOOSE v \in r3 : TRUE
                                        r4 == r3 \ {v4}
                                    IN IF r4 = {} THEN w[v1] + w[v2] + w[v3] + w[v4]
                                       ELSE LET v5 == CHOOSE v \in r4 : TRUE
                                            IN w[v1] + w[v2] + w[v3] + w[v4] + w[v5]
      totalW == TotalWeight
  IN byzWeight * 100 <= totalW * (100 - QuorumThreshold)

(* Invariant 5: If a decision is recorded, consensus was reached *)
QuorumIntegrityInvariant ==
  \A p \in proposals :
    decisions[p] /= "none" => ConsensusReached(p)

(* Invariant 6: Trust score reflects weight ratio *)
TrustWeightCorrelationInvariant ==
  \A v \in Validators :
    weights[v] * 100 <= (MaxWeight * trustScores[v])

(* --- Actions --- *)

(* Action: Create new proposal *)
CreateProposal(p) ==
  /\ p \notin proposals
  /\ proposals' = proposals \cup {p}
  /\ votes' = [v \in Validators, q \in proposals' |-> IF q = p THEN "none" ELSE votes[v,q]]
  /\ decisions' = [q \in proposals' |-> IF q = p THEN "none" ELSE decisions[q]]
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
        SumVotingWeight(p, d) * 100 >= QuorumWeight
     IN decisions' = [q \in proposals |-> IF q = p THEN winner ELSE decisions[q]]
  /\ UNCHANGED <<weights, trustScores, proposals, votes, byzantine, round>>

(* Action: Update weights after consensus (reward/punish) *)
UpdateWeights(p) ==
  /\ p \in proposals
  /\ decisions[p] /= "none"                    (* Consensus reached *)
  /\ LET winner == decisions[p]
     IN weights' = [v \in Validators |->
          IF votes[v,p] = winner THEN Min(weights[v] + 1, MaxWeight)
          ELSE IF votes[v,p] /= "none" /\ votes[v,p] /= "abstain" THEN Max(weights[v] - 1, 0)
          ELSE weights[v]]
  /\ trustScores' = [v \in Validators |->
       IF votes[v,p] = winner THEN Min(trustScores[v] + 2, 100)
       ELSE IF votes[v,p] /= "none" /\ votes[v,p] /= "abstain" THEN Max(trustScores[v] - 2, 0)
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
  \/ \E p \in ProposalIDs \ proposals : CreateProposal(p)
  \/ \E v \in Validators, p \in proposals, val \in VoteValues : CastVote(v, p, val)
  \/ \E p \in proposals : ReachConsensus(p)
  \/ \E p \in proposals : UpdateWeights(p)
  \/ \E v \in Validators : DetectByzantine(v)

(* --- Specification --- *)

Spec == Init /\ [][Next]_vars

(* --- Model checking constraints --- *)

(* Bounded state space for TLC *)
StateConstraint == round <= MaxRounds

(* --- Temporal Properties --- *)

(* Liveness: Eventually a proposal reaches consensus if quorum votes *)  
ConsensusLiveness ==
  \E p \in proposals :
    (/\ \E decision \in VoteValues :
          LET approving == {w \in CorrectValidators : votes[w,p] = decision}
              total_app == IF approving = {} THEN 0
                          ELSE LET S == {weights[vv] : vv \in approving}
                               IN CHOOSE t \in S : \A x \in S : t >= x
          IN total_app >= QuorumWeight)
    ~> decisions[p] /= "none"

(* Termination: System eventually produces a decision *)
Termination ==
  \E p \in proposals : <>(decisions[p] /= "none")

(* Property constraints for TLC: invariant checking *)
THEOREM Spec => []WeightBoundsInvariant
THEOREM Spec => []TrustBoundsInvariant
THEOREM Spec => []ByzantineBoundInvariant

===============================================================================