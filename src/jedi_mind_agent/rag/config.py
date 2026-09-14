EMBEDDING_PROVIDER = "local"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIMENSIONS = 384

CHROMA_HOST = "chroma"
CHROMA_PORT = 8000
CHROMA_COLLECTION = "jedi_mind_agent_chunks"

RAG_TOP_K = 5
RAG_SOURCE_DIR = "/app/data/sources"

CHUNK_TARGET_CHARS = 1400
CHUNK_OVERLAP_CHARS = 200
