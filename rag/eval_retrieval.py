"""Tiny retrieval evaluation: does the right section come back in the top-k?

Measuring retrieval separately from generation is the first thing to do when a
RAG system gives wrong answers: if the right passage is not retrieved, no prompt
will fix it.

    python rag/eval_retrieval.py                          # hit rate @1 and @3
    python rag/eval_retrieval.py --min-hit1 0.8 --min-hit3 0.9   # CI gate: exit 1 below thresholds
"""

import argparse
import os
import sys

from rag_core import Index

# (question, expected source file, expected section prefix)
GOLDEN_SET = [
    ("How fast must we patch a critical vulnerability on an internet-facing server?",
     "03-security-patch-policy.md", "4."),
    ("Who should I page if the primary on-call does not acknowledge an alert?",
     "01-incident-runbook.md", "4."),
    ("How much downtime per month does a 99.9% SLO allow?",
     "02-support-sla-policy.md", "3."),
    ("What credit does an Enterprise customer get if availability is 98.5%?",
     "02-support-sla-policy.md", "4."),
    ("Where must API keys and database passwords be stored?",
     "03-security-patch-policy.md", "3."),
    ("When is the post-incident review due after a SEV1?",
     "01-incident-runbook.md", "6."),
    ("What are the support hours of the Business plan?",
     "02-support-sla-policy.md", "1."),
    ("How do I roll back a bad deployment?",
     "01-incident-runbook.md", "5."),
    ("Within how many hours must a personal data breach be reported to the regulator?",
     "03-security-patch-policy.md", "6."),
    ("Are releases frozen when the error budget is almost spent?",
     "02-support-sla-policy.md", "3."),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieval evaluation on the golden set")
    parser.add_argument("--min-hit1", type=float, default=0.0, help="minimum Hit@1 ratio (0-1)")
    parser.add_argument("--min-hit3", type=float, default=0.0, help="minimum Hit@3 ratio (0-1)")
    args = parser.parse_args()

    index = Index.load_or_build()
    rows = []
    hits_at_1 = hits_at_3 = 0
    print(f"Retriever: {index.backend}\n")
    for question, source, section in GOLDEN_SET:
        results = index.search(question, k=3)
        ranks = [
            i for i, h in enumerate(results)
            if h.chunk.source == source and h.chunk.section.startswith(section)
        ]
        rank = ranks[0] + 1 if ranks else None
        hits_at_1 += rank == 1
        hits_at_3 += rank is not None
        status = f"rank {rank}" if rank else "MISS  "
        print(f"  {status:7} {question}")
        if not rank:
            print(f"          expected {source} § {section}  got {results[0].chunk.citation()}")
        rows.append((question, rank, results[0].chunk.citation()))
    n = len(GOLDEN_SET)
    hit1, hit3 = hits_at_1 / n, hits_at_3 / n
    print(f"\nHit@1: {hits_at_1}/{n}   Hit@3: {hits_at_3}/{n}")

    passed = hit1 >= args.min_hit1 and hit3 >= args.min_hit3
    if args.min_hit1 or args.min_hit3:
        print(f"Thresholds: Hit@1 >= {args.min_hit1:.0%}, Hit@3 >= {args.min_hit3:.0%} -> "
              f"{'PASS' if passed else 'FAIL'}")
    _write_github_summary(index.backend, hits_at_1, hits_at_3, n, rows, passed)
    return 0 if passed else 1


def _write_github_summary(backend, h1, h3, n, rows, passed) -> None:
    """In GitHub Actions, show the results as a table on the run's summary page."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"## Retrieval evaluation ({backend}): {'PASS' if passed else 'FAIL'}",
        "",
        f"**Hit@1 {h1}/{n} · Hit@3 {h3}/{n}**",
        "",
        "| Question | Rank | Top result |",
        "|---|---|---|",
    ]
    lines += [f"| {q} | {r or 'miss'} | {top} |" for q, r, top in rows]
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
