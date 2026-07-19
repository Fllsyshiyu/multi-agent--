# Local case RAG

`data/knowledge/external_cases.jsonl` is the editable source of truth for external reference cases. It is not an index and it is never modified by the build command.

## Build or update the index

Install the optional RAG dependencies, then run:

```powershell
python scripts/build_knowledge_index.py
```

The command writes generated artifacts to `data/knowledge/index/`:

- `knowledge.db`: SQLite text and metadata store with FTS5 full-text search.
- `case_chunks.jsonl`: auditable chunks derived from each source case.
- `vectors.jsonl`: portable stored embeddings, used to avoid recomputing unchanged chunks.
- `vectors.faiss` and `vector_ids.json`: FAISS similarity index when `faiss-cpu` is available.
- `index_manifest.json`: embedding model, dimensions, and build summary.

The generated directory is ignored by Git. Add or update a source JSONL line and rebuild; only chunks with a changed content hash are re-embedded. If the `embedding.model_name` in `configs/knowledge_base.yaml` changes, rebuild every vector.

## Shared corpus, different Agent views

All Agents retrieve from one corpus. At session start, each Agent query combines the deliberation topic, question, role, relationship to the issue, and stated interests. Hybrid lexical/vector results are de-duplicated with a per-case quota and returned as normal evidence cards scoped to that Agent ID.

Every RAG evidence card retains its case fragment ID, source URL, evidence level, and verification gaps. It must be described as an external reference case, never as a fact about the current community.
