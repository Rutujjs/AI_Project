import json
import logging
import os
import sqlite3
import numpy as np

logger = logging.getLogger(__name__)


class SQLiteVectorCollection:
    """Resilient local vector collection fallback matching ChromaDB interface."""

    def __init__(self, db_path="./chroma_db/esg_documents.db"):
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS esg_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT,
                        text TEXT,
                        embedding TEXT,
                        metadata TEXT
                    )
                """)
        finally:
            conn.close()

    def count(self):
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM esg_chunks")
            return cur.fetchone()[0]
        finally:
            conn.close()

    def upsert(self, ids, documents, embeddings, metadatas):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                for cid, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
                    doc_id = meta.get("document_id", "") if isinstance(meta, dict) else ""
                    conn.execute("""
                        INSERT OR REPLACE INTO esg_chunks (chunk_id, document_id, text, embedding, metadata)
                        VALUES (?, ?, ?, ?, ?)
                    """, (cid, doc_id, doc, json.dumps(emb), json.dumps(meta)))
        finally:
            conn.close()

    def get(self, ids=None, where=None):
        conn = sqlite3.connect(self.db_path)
        try:
            query = "SELECT chunk_id, text, metadata FROM esg_chunks"
            params = []
            if ids:
                placeholders = ",".join("?" for _ in ids)
                query += f" WHERE chunk_id IN ({placeholders})"
                params.extend(ids)
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            res_ids, res_docs, res_metas = [], [], []
            for cid, text, meta_str in rows:
                meta = json.loads(meta_str) if meta_str else {}
                if where:
                    match = all(meta.get(k) == v for k, v in where.items())
                    if not match:
                        continue
                res_ids.append(cid)
                res_docs.append(text)
                res_metas.append(meta)
            return {"ids": res_ids, "documents": res_docs, "metadatas": res_metas}
        finally:
            conn.close()

    def update(self, ids, metadatas):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                for cid, meta in zip(ids, metadatas):
                    doc_id = meta.get("document_id", "") if isinstance(meta, dict) else ""
                    conn.execute("""
                        UPDATE esg_chunks SET metadata = ?, document_id = ? WHERE chunk_id = ?
                    """, (json.dumps(meta), doc_id, cid))
        finally:
            conn.close()

    def delete(self, ids=None, where=None):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                if ids:
                    placeholders = ",".join("?" for _ in ids)
                    conn.execute(f"DELETE FROM esg_chunks WHERE chunk_id IN ({placeholders})", ids)
                elif where:
                    res = self.get(where=where)
                    if res["ids"]:
                        placeholders = ",".join("?" for _ in res["ids"])
                        conn.execute(f"DELETE FROM esg_chunks WHERE chunk_id IN ({placeholders})", res["ids"])
        finally:
            conn.close()

    def query(self, query_embeddings, n_results=3):
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT chunk_id, text, embedding, metadata FROM esg_chunks")
            rows = cursor.fetchall()
        finally:
            conn.close()

        if not rows:
            return {
                "ids": [[] for _ in query_embeddings],
                "documents": [[] for _ in query_embeddings],
                "metadatas": [[] for _ in query_embeddings],
                "distances": [[] for _ in query_embeddings],
            }

        ret_ids, ret_docs, ret_metas, ret_dists = [], [], [], []
        for q in query_embeddings:
            q_arr = np.array(q, dtype=np.float32)
            dim = len(q_arr)
            q_norm = np.linalg.norm(q_arr)
            if q_norm == 0:
                q_norm = 1e-10
            q_norm_arr = q_arr / q_norm

            valid_rows = []
            for r in rows:
                try:
                    emb = json.loads(r[2])
                    if len(emb) == dim:
                        valid_rows.append((r[0], r[1], emb, json.loads(r[3]) if r[3] else {}))
                except Exception:
                    continue

            if not valid_rows:
                ret_ids.append([])
                ret_docs.append([])
                ret_metas.append([])
                ret_dists.append([])
                continue

            all_ids = [r[0] for r in valid_rows]
            all_docs = [r[1] for r in valid_rows]
            all_embs = np.array([r[2] for r in valid_rows], dtype=np.float32)
            all_metas = [r[3] for r in valid_rows]

            norms = np.linalg.norm(all_embs, axis=1, keepdims=True)
            norms[norms == 0] = 1e-10
            norm_embs = all_embs / norms

            sims = np.dot(norm_embs, q_norm_arr)
            dists = 1.0 - sims
            dists = np.clip(dists, 0.0, 2.0)
            top_indices = np.argsort(dists)[:n_results]

            ret_ids.append([all_ids[i] for i in top_indices])
            ret_docs.append([all_docs[i] for i in top_indices])
            ret_metas.append([all_metas[i] for i in top_indices])
            ret_dists.append([float(dists[i]) for i in top_indices])

        return {
            "ids": ret_ids,
            "documents": ret_docs,
            "metadatas": ret_metas,
            "distances": ret_dists,
        }


try:
    import chromadb

    client = chromadb.PersistentClient(
        path="./chroma_db"
    )

    collection = client.get_or_create_collection(
        name="esg_documents"
    )

except Exception as e:
    chromadb = None  # type: ignore
    client = None    # type: ignore
    logger.info(f"ChromaDB unavailable ({e}); using SQLiteVectorCollection fallback.")
    collection = SQLiteVectorCollection(db_path="./chroma_db/esg_documents.db")


# --------------------------------------------------
# Store chunks + embeddings
# --------------------------------------------------

def store_chunks(chunks, embeddings, esg_analyses=None):

    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(chunks):

        ids.append(chunk["chunk_id"])

        documents.append(chunk["text"])

        # Get ESG analysis if available
        if esg_analyses:
            esg_analysis = esg_analyses[index]
        else:
            esg_analysis = {
                "commitments": []
            }

        metadatas.append({
            "document_id": chunk["document_id"],
            "filename": chunk["filename"],
            "page": chunk["page"],
            "esg_analysis": json.dumps(esg_analysis)
        })

    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    return len(chunks)


# --------------------------------------------------
# Search chunks
# --------------------------------------------------

def search_chunks(query_embedding, n_results=3):

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results
    )

    return results


# --------------------------------------------------
# Update ESG analysis
# --------------------------------------------------

def update_esg_analysis(esg_analysis_map):

    """
    Update ESG analysis for existing chunks.

    esg_analysis_map should look like:

    {
        "chunk-id-1": {
            "commitments": [...]
        },

        "chunk-id-2": {
            "commitments": [...]
        }
    }
    """

    for chunk_id, analysis in esg_analysis_map.items():

        # Get existing chunk
        result = collection.get(
            ids=[chunk_id]
        )

        if not result["ids"]:
            continue

        # Get existing metadata
        metadata = result["metadatas"][0]

        # Replace ESG analysis
        metadata["esg_analysis"] = json.dumps(
            analysis
        )

        # Update metadata
        collection.update(
            ids=[chunk_id],
            metadatas=[metadata]
        )

    return len(esg_analysis_map)
