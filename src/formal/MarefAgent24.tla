----------------------------- MODULE MarefAgent24 ------------------------------
(*
  MAREF Agent 24-State Gray Code FSM

  This TLA+ specification formally models the 24-state agent lifecycle
  state machine using 5-bit Gray code encoding, ensuring single-bit
  transitions between adjacent states to prevent race conditions.

  States grouped by lifecycle phase:
  Birth:   UNINITIALIZED(00000) -> BOOTING(00001) -> REGISTERING(00011) -> IDLE(00010)
  Active:  DISCOVERING(00110) -> NEGOTIATING(00111) -> TRUST_BUILDING(00101)
           -> CONTRACTING(00100) -> EXECUTING(01100) -> WAITING(01101)
           -> VERIFYING(01111) -> REPORTING(01110)
  Conflict: CONFLICTING(01010) -> ARBITRATING(01011) -> RECOVERING(01001)
            -> MIGRATING(01000)
  Pause:   PAUSED(11000) -> DEGRADING(11001) -> SELF_HEALING(11011)
           -> SELF_OPTIMIZING(11010) -> EVOLVING(11110)
  Death:   TERMINATING(11111) -> TERMINATED(11101) / ZOMBIE(11100)
*)

EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
  Agents             (* Set of agent identifiers, e.g. {"agent1"} *)

(* 2026-11-22：AgentStates 原来是 CONSTANT + `ASSUME AgentStates = 0..23`，
   而 TLC 的 .cfg 无法给常量赋区间字面量（`X = 0..23` 报 "expecting = or <-"），
   所以这个规格从来没有被任何 .cfg 实例化过。改为全等定义后可被 TLC 检查。*)
AgentStates == 0..23

ASSUME IsFiniteSet(Agents)

(* 5-bit Gray code for each state *)
GrayCode5 == [
  s \in AgentStates |->
    CASE s = 0 -> <<0,0,0,0,0>>   (* UNINITIALIZED *)
    [] s = 1 -> <<0,0,0,0,1>>     (* BOOTING *)
    [] s = 2 -> <<0,0,0,1,1>>     (* REGISTERING *)
    [] s = 3 -> <<0,0,0,1,0>>     (* IDLE *)
    [] s = 4 -> <<0,0,1,1,0>>     (* DISCOVERING *)
    [] s = 5 -> <<0,0,1,1,1>>     (* NEGOTIATING *)
    [] s = 6 -> <<0,0,1,0,1>>     (* TRUST_BUILDING *)
    [] s = 7 -> <<0,0,1,0,0>>     (* CONTRACTING *)
    [] s = 8 -> <<0,1,1,0,0>>     (* EXECUTING *)
    [] s = 9 -> <<0,1,1,0,1>>     (* WAITING *)
    [] s = 10 -> <<0,1,1,1,1>>    (* VERIFYING *)
    [] s = 11 -> <<0,1,1,1,0>>    (* REPORTING *)
    [] s = 12 -> <<0,1,0,1,0>>    (* CONFLICTING *)
    [] s = 13 -> <<0,1,0,1,1>>    (* ARBITRATING *)
    [] s = 14 -> <<0,1,0,0,1>>    (* RECOVERING *)
    [] s = 15 -> <<0,1,0,0,0>>    (* MIGRATING *)
    [] s = 16 -> <<1,1,0,0,0>>    (* PAUSED *)
    [] s = 17 -> <<1,1,0,0,1>>    (* DEGRADING *)
    [] s = 18 -> <<1,1,0,1,1>>    (* SELF_HEALING *)
    [] s = 19 -> <<1,1,0,1,0>>    (* SELF_OPTIMIZING *)
    [] s = 20 -> <<1,1,1,1,0>>    (* EVOLVING *)
    [] s = 21 -> <<1,1,1,1,1>>    (* TERMINATING *)
    [] s = 22 -> <<1,1,1,0,1>>    (* TERMINATED *)
    [] s = 23 -> <<1,1,1,0,0>>    (* ZOMBIE *)
]

(* State name mapping *)
StateName5 == [
  s \in AgentStates |->
    CASE s = 0 -> "UNINITIALIZED"
    [] s = 1 -> "BOOTING"
    [] s = 2 -> "REGISTERING"
    [] s = 3 -> "IDLE"
    [] s = 4 -> "DISCOVERING"
    [] s = 5 -> "NEGOTIATING"
    [] s = 6 -> "TRUST_BUILDING"
    [] s = 7 -> "CONTRACTING"
    [] s = 8 -> "EXECUTING"
    [] s = 9 -> "WAITING"
    [] s = 10 -> "VERIFYING"
    [] s = 11 -> "REPORTING"
    [] s = 12 -> "CONFLICTING"
    [] s = 13 -> "ARBITRATING"
    [] s = 14 -> "RECOVERING"
    [] s = 15 -> "MIGRATING"
    [] s = 16 -> "PAUSED"
    [] s = 17 -> "DEGRADING"
    [] s = 18 -> "SELF_HEALING"
    [] s = 19 -> "SELF_OPTIMIZING"
    [] s = 20 -> "EVOLVING"
    [] s = 21 -> "TERMINATING"
    [] s = 22 -> "TERMINATED"
    [] s = 23 -> "ZOMBIE"
]

(* Valid transitions based on Python VALID_TRANSITIONS dict *)
ValidTransition5(s, t) ==
  \/ /\ s = 0  /\ t \in {1, 22}      (* UNINITIALIZED -> BOOTING | TERMINATED *)
  \/ /\ s = 1  /\ t \in {2, 21}      (* BOOTING -> REGISTERING | TERMINATING *)
  \/ /\ s = 2  /\ t \in {3, 21}      (* REGISTERING -> IDLE | TERMINATING *)
  \/ /\ s = 3  /\ t \in {4, 19, 16, 21, 15}  (* IDLE -> DISCOVERING | SELF_OPTIMIZING | PAUSED | TERMINATING | MIGRATING *)
  \/ /\ s = 4  /\ t \in {5, 3}       (* DISCOVERING -> NEGOTIATING | IDLE *)
  \/ /\ s = 5  /\ t \in {6, 3}       (* NEGOTIATING -> TRUST_BUILDING | IDLE *)
  \/ /\ s = 6  /\ t \in {7, 3}       (* TRUST_BUILDING -> CONTRACTING | IDLE *)
  \/ /\ s = 7  /\ t \in {8, 3}       (* CONTRACTING -> EXECUTING | IDLE *)
  \/ /\ s = 8  /\ t \in {9, 10, 12}  (* EXECUTING -> WAITING | VERIFYING | CONFLICTING *)
  \/ /\ s = 9  /\ t \in {8, 10}      (* WAITING -> EXECUTING | VERIFYING *)
  \/ /\ s = 10 /\ t \in {11, 8}      (* VERIFYING -> REPORTING | EXECUTING *)
  \/ /\ s = 11 /\ t \in {3, 20}      (* REPORTING -> IDLE | EVOLVING *)
  \/ /\ s = 12 /\ t \in {13, 17}     (* CONFLICTING -> ARBITRATING | DEGRADING *)
  \/ /\ s = 13 /\ t \in {14, 3}      (* ARBITRATING -> RECOVERING | IDLE *)
  \/ /\ s = 14 /\ t \in {3, 12}      (* RECOVERING -> IDLE | CONFLICTING *)
  \/ /\ s = 15 /\ t \in {3, 21}      (* MIGRATING -> IDLE | TERMINATING *)
  \/ /\ s = 16 /\ t \in {3, 21}      (* PAUSED -> IDLE | TERMINATING *)
  \/ /\ s = 17 /\ t \in {18, 21}     (* DEGRADING -> SELF_HEALING | TERMINATING *)
  \/ /\ s = 18 /\ t \in {3, 17}      (* SELF_HEALING -> IDLE | DEGRADING *)
  \/ /\ s = 19 /\ t \in {3, 20}      (* SELF_OPTIMIZING -> IDLE | EVOLVING *)
  \/ /\ s = 20 /\ t \in {3, 19}      (* EVOLVING -> IDLE | SELF_OPTIMIZING *)
  \/ /\ s = 21 /\ t \in {22, 23}     (* TERMINATING -> TERMINATED | ZOMBIE *)
  \/ /\ s = 22 /\ FALSE              (* TERMINATED: absorbing *)
  \/ /\ s = 23 /\ FALSE              (* ZOMBIE: absorbing *)

(* 5-bit Gray code single-bit transition check *)
GrayCodeSingleBit5(s, t) ==
  LET gs == GrayCode5[s]
      gt == GrayCode5[t]
  IN \E i \in 1..5 : /\ gs[i] # gt[i]
                     /\ \A j \in 1..5 : j # i => gs[j] = gt[j]

(* Full transition relation: the real ValidTransition5 table, minus the two
   absorbing states.

   2026-11-22: 这里原来还叠了一条 `GrayCodeSingleBit5(s, t)` 过滤，把
   ValidTransition5 里 27 条多比特边全部删掉，导致 14/15/16 三个状态
   （RECOVERING/MIGRATING/PAUSED）失去全部出边 → NoDeadlock5 恒假。
   该规格因 cfg 关键字拼写错误从未跑过，所以一直没人发现。*)
CanTransition5(s, t) ==
  /\ ValidTransition5(s, t)
  /\ ~(s = 22 \/ s = 23)  (* No transitions from TERMINATED or ZOMBIE *)

(* Transitions set *)
Transitions5 == { <<s, t>> \in AgentStates \X AgentStates : CanTransition5(s, t) }

(* Is state terminal? *)
IsTerminal5(s) == (s = 22) \/ (s = 23)

(* Has outgoing transitions *)
HasOutgoing5(s) == \E t \in AgentStates : CanTransition5(s, t)

(* Has incoming transitions *)
HasIncoming5(s) == \E t \in AgentStates : CanTransition5(t, s)

(* ============= Invariants ============= *)

(* INV-001: Every non-terminal state has at least one outgoing transition *)
NoDeadlock5 == \A s \in AgentStates : IsTerminal5(s) \/ HasOutgoing5(s)

(* INV-002: Every state except UNINITIALIZED has at least one incoming transition *)
NoOrphan5 == \A s \in AgentStates : s = 0 \/ HasIncoming5(s)

(* INV-003: TERMINATED has no outgoing transitions *)
TerminatedFinal5 == ~HasOutgoing5(22)

(* INV-004: ZOMBIE has no outgoing transitions *)
ZombieFinal5 == ~HasOutgoing5(23)

(* ── 灰码不变量（2026-11-22 按实际转移表重写）─────────────────────────────
   实测：48 条边里只有 21 条是单比特（Gray 相邻），其余 27 条是多比特跳转，
   而且不是边缘情况——IDLE 一个状态就有 11 条入边是多比特。
   所以"每条合法转移都只改 1 位"这个说法与设计不符；真实设计是：
   相邻生命周期走单比特，停机/恢复/跨阶段切换走显式声明的多比特跳转。

   下面把 27 条多比特边写成字面集合，作为变更控制锁：新增一条多比特边
   必须同时改这里（review 可见），否则 TLC 判红。*)
JumpEdges5 == {
  <<0,22>>, <<1,21>>, <<2,21>>, <<3,15>>,
  <<3,16>>, <<3,19>>, <<3,21>>, <<5,3>>,
  <<6,3>>, <<7,3>>, <<8,10>>, <<8,12>>,
  <<10,8>>, <<11,3>>, <<12,17>>, <<13,3>>,
  <<14,3>>, <<14,12>>, <<15,3>>, <<15,21>>,
  <<16,3>>, <<16,21>>, <<17,21>>, <<18,3>>,
  <<19,3>>, <<20,3>>, <<21,23>>
}


(* INV-005（重写）: 多比特边 vs 声明集合，双向等价 —— 既不允许未声明的多比特跳转，
   也不允许声明了却不在转移表里的幽灵边。 *)
GrayContinuity5 ==
  \A p \in Transitions5 :
    (~GrayCodeSingleBit5(p[1], p[2])) <=> (p \in JumpEdges5)

(* INV-006: 24 states total *)
StateCount5 == Cardinality(AgentStates) = 24

(* INV-007: UNINITIALIZED must have path to TERMINATED *)
UninitToTerminated ==
  \E path \in Seq(AgentStates) :
    Len(path) >= 2 /\ path[1] = 0 /\ path[Len(path)] = 22
    /\ \A i \in 1..(Len(path)-1) : CanTransition5(path[i], path[i+1])

===============================================================================
