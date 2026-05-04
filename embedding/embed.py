from langchain_huggingface import HuggingFaceEmbeddings

_model = None


def get_embedder():
    global _model
    if _model is None:
        _model = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    return _model
