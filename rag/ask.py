"""Ask a question to the RAG pipeline.

    python rag/ask.py "What is the patch deadline for a critical CVE on an internet-facing server?"
    python rag/ask.py --show-chunks "..."     # also print the retrieved passages
    python rag/ask.py --rebuild "..."         # force re-embedding the documents
"""

import argparse
import sys

from rag_core import Index, answer


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask the Hanbit Logistics documents")
    parser.add_argument("question", nargs="+")
    parser.add_argument("-k", type=int, default=4, help="number of passages to retrieve")
    parser.add_argument("--rebuild", action="store_true", help="rebuild the index")
    parser.add_argument("--show-chunks", action="store_true", help="print retrieved passages")
    args = parser.parse_args()

    question = " ".join(args.question)
    index = Index.load_or_build(rebuild=args.rebuild)
    result = answer(question, index, k=args.k)

    print(f"\nQ: {question}\n")
    print(result["answer"])
    print(f"\n[retriever: {result['retriever']} | mode: {result['mode']}]")
    print("Retrieved:")
    for s in result["sources"]:
        print(f"  {s['score']:.3f}  {s['citation']}")

    if args.show_chunks:
        for hit in index.search(question, k=args.k):
            print(f"\n----- {hit.chunk.citation()} ({hit.score:.3f})\n{hit.chunk.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
