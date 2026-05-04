from langchain_ollama import OllamaLLM

_llm = None


def get_llm(model="llama3"):
    global _llm
    if _llm is None:
        _llm = OllamaLLM(model=model, temperature=0)
    return _llm


def call(prompt, model="llama3"):
    llm = get_llm(model)
    try:
        return llm.invoke(prompt)
    except Exception as exc:
        raise RuntimeError(
            f"Could not connect to Ollama model '{model}'. "
            "Make sure Ollama is installed, running, and the model is pulled. "
            "Run `ollama serve` in one terminal and `ollama pull llama3` if needed."
        ) from exc
