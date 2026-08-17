------------------------------ MODULE Vortex369 ------------------------------
(*
  Formal model checking of the "369" digital-root theorems.

  Background: the so-called "vortex math 369 mystery" (Nikola Tesla / Marko
  Rodin urban legend) is entirely an artifact of base-10 digital roots, i.e.
  arithmetic modulo 9. This spec machine-checks the claims with TLC up to a
  constant bound N and documents the number-theoretic reason why each claim
  generalizes to all naturals.

  Key facts (proved, not assumed):
    - For any n, digitroot(2^n) lives in the cycle {1,2,4,8,7,5} because 2 is
      a generator of the units group (Z/9Z)*, of order 6: 2^6 = 64 = 1 (mod 9).
      Hence DR(2^(n+6)) = DR(2^n) and 3/6/9 never appear.
    - Digitroot(3*2^n) in {3,6} because multiples of 3 are 0, 3 or 6 (mod 9),
      and 3*2^k is never 0 (mod 9) for k >= 0.
    - Digitroot(9*2^n) = 9 because 9 == 0 (mod 9) and the digital root of a
      multiple of 9 is 9 (casting out nines).
    - All closed shapes with side count >= 3 have interior angle sum
      (n-2)*180, always a multiple of 9, hence digital root 9.
    - 360, 180, 90, 45, 108, 432 and 0+..+8 = 36 are all multiples of 9.

  TLC limitation: TLC enumerates a finite state space (1..N). The infinite
  generalization is justified by the modular-arithmetic facts above rather
  than by the finite model check alone.
*)
EXTENDS Naturals

CONSTANT N

\* The doubling cycle that excludes 3, 6 and 9.
R == {1, 2, 4, 8, 7, 5}

\* 2^n reduced modulo 9, computed by recurrence so values stay in 0..8.
\* (Direct 2^n would overflow TLC's 64-bit naturals; digital roots only care
\* about the value modulo 9 anyway.)
RECURSIVE Pow2mod9(_)
Pow2mod9(n) == IF n = 0 THEN 1 ELSE (Pow2mod9(n - 1) * 2) % 9

\* Digital root of a positive integer: n mod 9, mapping 0 -> 9.
\* For n = 0 the digital root is 0 by convention.
DR(n) == IF n = 0 THEN 0 ELSE IF n % 9 = 0 THEN 9 ELSE n % 9

\* Digital root of a value already reduced to its residue modulo 9.
\* A residue of 0 corresponds to a digital root of 9.
DRm(v) == IF v = 0 THEN 9 ELSE v

\* INV1: powers of 2 stay on the 1-2-4-8-7-5 circuit; 3/6/9 never appear.
\* 2 is a generator of (Z/9Z)* of order 6, so DR(2^n) = DRm(2^n mod 9).
INV1 == \A n \in 1..N : Pow2mod9(n) \in R

\* INV2: doubling starting at 3 oscillates forever between 3 and 6.
INV2 == \A n \in 1..N : (3 * Pow2mod9(n)) % 9 \in {3, 6}

\* INV3: doubling ever from 9 always digital-roots to 9 (9 is the mod-9 zero).
INV3 == \A n \in 1..N : DRm((9 * Pow2mod9(n)) % 9) = 9

\* INV4: the doubling circuit has period 6 because 2^6 = 1 (mod 9).
INV4 == \A n \in 1..N : Pow2mod9(n + 6) = Pow2mod9(n)

\* INV5: any polygon with n >= 3 sides has angle sum (n-2)*180 -> digital root 9.
INV5 == \A n \in 3..N : DR((n - 2) * 180) = 9

\* INV6: repeatedly bisecting a circle keeps the digital root at 9.
INV6 == DR(360) = 9 /\ DR(180) = 9 /\ DR(90) = 9 /\ DR(45) = 9

\* INV7: 0+1+..+8 = 36, and the "sacred" 108 / 432 all reduce to 9.
INV7 == DR(36) = 9 /\ DR(108) = 9 /\ DR(432) = 9

\* Trivial state machine that advances a counter to drive TLC over 0..N.
VARIABLE k

Init == k = 0
Next == k' = IF k < N THEN k + 1 ELSE k

Spec == Init /\ [][Next]_k

TypeOK == k \in 0..N
=============================================================================