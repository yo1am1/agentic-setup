---
paths:
  - "src/pinecone_helpers/**"
---

# Retrieval and embeddings

- Both dense and sparse embeddings come from the GPU inference cluster (BGE-M3, KServe v2); RunPod is the fallback for both.
- Public API in `runpod_embedder.py`: `get_dense_embedding`, `get_sparse_embedding`, `get_both_embeddings` — each tries GPU first, falls back to RunPod on any error.
- `get_both_embeddings` makes one GPU call for both outputs; on failure it fans out to parallel RunPod calls.
- `HybridSearchStrategy` uses `get_both_embeddings` when dense and sparse texts are identical; parallel single calls when an augmented query diverges.
- Keep retrieval contracts explicit (request/response models); thresholds and toggles live in config modules.
- RAF routing: `examples_retriever.py` `find_example(query)` returns `{score, example_query, ideal_action, hint}` above `EXAMPLES_SCORE_THRESHOLD`, else `None`.
- Validate retrieval changes with evaluation scripts before shipping; do not tune constants without measuring.
