# Wiki RAG Module

Manages preprocessing, indexing, and chatting over a local wiki-derived knowledge base using LlamaIndex + Ollama.

## Endpoints
- GET /wiki_rag/healthz
- POST /wiki_rag/preprocess
- POST /wiki_rag/index/rebuild
- GET/POST /wiki_rag/chat (`apply_actions=true` parametresi Autonomy etiketi yürütmesini tetikler, yanıt `actions` alanını içerir)

## Persona
Personas live as folders under `modules/ollama/config/personalities/<name>/{persona.txt,urls.txt}`.
Active persona is chosen by config (`persona.active`) or via `POST /wiki_rag/persona/select`.

## Notes
Requires an Ollama server and llama-index packages installed.
RAG uses the same model name as configured. Ollama service can be separate; this module calls llama-index with Ollama backend directly.

## Gateway ile Kullanım
Gateway çalışırken RAG uçları tek portta `/wiki_rag/*` altında sunulur; modülü ayrı servis olarak çalıştırmaya gerek yoktur.
