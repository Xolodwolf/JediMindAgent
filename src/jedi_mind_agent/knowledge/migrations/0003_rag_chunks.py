"""Book chunks with embeddings in PostgreSQL + pgvector, replacing ChromaDB.

The table is written and searched by the RAG service with raw SQL (rag_service/store.py), so it is created here
with SQL rather than as a Django model: the web image needs no pgvector client. The vector size must match
EMBEDDING_DIMENSIONS of the RAG service; another embedding model with another size needs a new migration.

On SQLite (local experiments, tests) the table is created without the vector type, so the cascade and counts work.
"""

from django.db import migrations

POSTGRES_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE rag_chunks (
    id text PRIMARY KEY,
    book_id bigint NOT NULL REFERENCES rag_books (id) ON DELETE CASCADE,
    source_slug varchar(120) NOT NULL,
    source_title text NOT NULL,
    source_filename text NOT NULL,
    file_hash varchar(64) NOT NULL,
    chunk_index integer NOT NULL,
    chunk_hash varchar(64) NOT NULL,
    page_start integer NOT NULL,
    page_end integer NOT NULL,
    level smallint NOT NULL,
    text text NOT NULL,
    embedding_model varchar(200) NOT NULL,
    embedding vector(384) NOT NULL
);
CREATE INDEX rag_chunks_book_id ON rag_chunks (book_id);
CREATE INDEX rag_chunks_level ON rag_chunks (level);
"""

SQLITE_SQL = """
CREATE TABLE rag_chunks (
    id text PRIMARY KEY,
    book_id bigint NOT NULL REFERENCES rag_books (id) ON DELETE CASCADE,
    source_slug varchar(120) NOT NULL,
    source_title text NOT NULL,
    source_filename text NOT NULL,
    file_hash varchar(64) NOT NULL,
    chunk_index integer NOT NULL,
    chunk_hash varchar(64) NOT NULL,
    page_start integer NOT NULL,
    page_end integer NOT NULL,
    level smallint NOT NULL,
    text text NOT NULL,
    embedding_model varchar(200) NOT NULL,
    embedding text NOT NULL
);
"""


def create_chunks_table(apps, schema_editor):
    sql = POSTGRES_SQL if schema_editor.connection.vendor == "postgresql" else SQLITE_SQL
    for statement in filter(str.strip, sql.split(";")):
        schema_editor.execute(statement)


def drop_chunks_table(apps, schema_editor):
    # The extension stays: other tables may use it, and dropping it needs more privileges than creating.
    schema_editor.execute("DROP TABLE IF EXISTS rag_chunks")


class Migration(migrations.Migration):
    dependencies = [("knowledge", "0002_drop_chroma_settings")]

    operations = [migrations.RunPython(create_chunks_table, drop_chunks_table)]
