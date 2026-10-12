"""Tiny retrieval evaluation: does the right section come back in the top-k?

Measuring retrieval separately from generation is the first thing to do when a
RAG system gives wrong answers: if the right passage is not retrieved, no prompt
will fix it.

    python rag/eval_retrieval.py          # hit rate @1 and @3
"""

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


def main() -> None:
    index = Index.load_or_build()
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
    n = len(GOLDEN_SET)
    print(f"\nHit@1: {hits_at_1}/{n}   Hit@3: {hits_at_3}/{n}")


if __name__ == "__main__":
    main()
