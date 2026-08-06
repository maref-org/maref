---- MODULE MAREF_CrossInstance ----
EXTENDS Naturals, FiniteSets

CONSTANTS
    Instances,
    MinTrust,
    MaxInstances

VARIABLES
    trustScores,
    weights,
    poisonedFlags,
    consensusRound

vars == <<trustScores, weights, poisonedFlags, consensusRound>>

Init ==
    /\ trustScores = [i \in Instances |-> 50]
    /\ weights = [i \in Instances |-> 1.0]
    /\ poisonedFlags = [i \in Instances |-> FALSE]
    /\ consensusRound = 0

SyncTrust ==
    /\ \E i, j \in Instances : i /= j
        /\ trustScores' = [trustScores EXCEPT ![j] = trustScores[i]]
        /\ UNCHANGED <<weights, poisonedFlags, consensusRound>>

UpdateWeight(i, newWeight) ==
    /\ weights' = [weights EXCEPT ![i] = newWeight]
    /\ UNCHANGED <<trustScores, poisonedFlags, consensusRound>>

DetectPoison ==
    /\ \E i \in Instances :
        weights[i] > 3.0
        /\ poisonedFlags' = [poisonedFlags EXCEPT ![i] = TRUE]
    /\ UNCHANGED <<trustScores, weights, consensusRound>>

ConsensusRound ==
    /\ consensusRound < MaxInstances
    /\ consensusRound' = consensusRound + 1
    /\ UNCHANGED <<trustScores, weights, poisonedFlags>>

Next ==
    \/ SyncTrust
    \/ \E i \in Instances, w \in {0.1, 0.5, 1.0, 2.0, 5.0}:
        UpdateWeight(i, w)
    \/ DetectPoison
    \/ ConsensusRound

Safety ==
    \A i \in Instances :
        (poisonedFlags[i] = TRUE) => (weights[i] > 3.0)

Liveness ==
    <>[](consensusRound = MaxInstances)
    => \A i \in Instances : poisonedFlags[i] = FALSE

THEOREM Spec == Init /\ [][Next]_vars

====
