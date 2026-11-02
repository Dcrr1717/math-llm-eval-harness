# Private held-out set

`--dataset private` runs a held-out set of 50 problems written for this harness on
2 Nov 2026. The problems, their builder script and the models' raw answers are
gitignored (`data/private/`, `results/raw/private.jsonl`), so the set cannot leak into
future training data. Only aggregate scores are published.

**Commitment.** SHA-256 of `data/private/problems.jsonl`:

```
3a2cc7eaf7eab57ec1844d3f0957904e22c4c6a43b1e1236d0f8450643de7afd
```

If the set is ever released, this hash shows it was not changed after the results
were reported.

**How the reference answers were obtained.** None is typed by hand. A builder script
computes each one by exhaustive enumeration, exact rational arithmetic (SymPy linear
systems, determinants, Markov chains), exact homology ranks, or 50-digit numerics
(mpmath) for analysis items, which ask for `floor(10^k * value)` and are rejected when
the value sits within 1e-4 of an integer boundary. Several answers were also checked
against closed forms (Burnside, Conway's leading numbers for Penney's game, the class
equation of GL_3(F_5), Adamaszek-Adams for Vietoris-Rips complexes of points on a
circle) and Monte Carlo.

**Topics (50 items).** Combinatorics 12, number theory 6, analysis 6, probability 6,
topology 6 (matching and chessboard complexes, independence complexes, Vietoris-Rips
barcodes), graph theory 5, linear algebra 5, group theory 2, algebra 1, game theory 1.
Items 1-32 are olympiad-style; items 33-50 were added to be harder (chained results,
parameters too large for hand enumeration, two-part answers).

To use your own copy: `PRIVATE_SET=path/to/problems.jsonl python -m src.cli run
--dataset private ...` with the same JSONL schema as `data/own/problems.jsonl`.
