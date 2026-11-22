-------------------------------- MODULE MarefAgent24Model --------------------------------
(*
  MarefAgent24 的可执行模型（2026-11-22 新增）。

  MarefAgent24.tla 是纯定义模块（没有 VARIABLE / Init / Next），TLC 无法直接跑它；
  而 MarefAgent24MC.cfg 里把关键字写成了 `INVARIANCES`（合法拼写是 `INVARIANTS`），
  于是 TLC 把它当成常量名解析并报配置错误 —— 这个规格从落地起就没被机器检查过。

  这里补一个走遍状态图的 Spec，让 7 条不变量真正进入 CI：
  - 从 UNINITIALIZED(0) 出发，按 ValidTransition5 走；
  - 到达吸收态（TERMINATED 22 / ZOMBIE 23）后 stutter，避免 TLC 误报死锁；
  - 不变量本身是静态的（对整张转移表取全称），TLC 在每个可达状态上求值，
    第一次求值就能判定真假。
*)

EXTENDS Naturals, Sequences, FiniteSets, MarefAgent24

VARIABLE st

Init == st = 0

Next ==
  \/ \E t \in AgentStates : CanTransition5(st, t) /\ st' = t
  \/ (IsTerminal5(st) /\ UNCHANGED st)

Spec == Init /\ [][Next]_st

================================================================================
