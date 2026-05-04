from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
from embedding.embed import get_embedder

CLIENT = QdrantClient(":memory:")


def _embedding_size(embedder):
    return len(embedder.embed_query("dimension probe"))


def _ensure_collection(collection_name, vector_size):
    existing = [c.name for c in CLIENT.get_collections().collections]
    if collection_name not in existing:
        CLIENT.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
        )


def build_store(chunks, collection_name="submission"):
    embedder = get_embedder()
    _ensure_collection(collection_name, _embedding_size(embedder))
    docs = [
        Document(
            page_content=chunk["text"],
            metadata={"source": chunk["source"], "reference": chunk["reference"]}
        )
        for chunk in chunks
    ]
    store = QdrantVectorStore(
        client=CLIENT,
        collection_name=collection_name,
        embedding=embedder
    )
    store.add_documents(docs)
    return store


def search(store, query, k=5, source=None):
    filter_ = None
    if source:
        filter_ = Filter(
            must=[FieldCondition(key="metadata.source", match=MatchValue(value=source))]
        )
    results = store.similarity_search(query, k=k, filter=filter_)
    return [
        {
            "text": doc.page_content,
            "source": doc.metadata.get("source"),
            "reference": doc.metadata.get("reference")
        }
        for doc in results
    ]
