"""Build or update the local case-RAG index.

Run from the repository root:
    python scripts/build_knowledge_index.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ma_deliberation_demo.knowledge.config import load_knowledge_config
from ma_deliberation_demo.knowledge.embedding import SentenceTransformerEmbedder
from ma_deliberation_demo.knowledge.indexer import build_knowledge_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local deliberation case-RAG index.")
    parser.add_argument("--config", default="configs/knowledge_base.yaml", help="Path to RAG YAML config")
    args = parser.parse_args()
    config = load_knowledge_config(args.config)
    report = build_knowledge_index(config, SentenceTransformerEmbedder(config.embedding))
    print(
        "Knowledge index built: "
        f"cases={report.source_case_count}, chunks={report.chunk_count}, "
        f"embedded={report.embedded_count}, reused={report.reused_count}, backend={report.backend}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
