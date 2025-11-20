"""Vectorstore utilities built on top of Chroma with OpenAI embeddings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

# Load .env file before creating any OpenAI clients
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# LangChain v1 import
from langchain_core.documents import Document


class VectorStoreManager:
    """Thin wrapper that encapsulates Chroma persistence and retriever helpers."""

    def __init__(
        self,
        persist_directory: str = "data/vectorstore",
        collection_name: str = "construction_docs",
    ) -> None:
        os.makedirs(persist_directory, exist_ok=True)
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def add_documents(self, documents: Iterable[Document]) -> int:
        """Add a batch of LangChain Documents to the store."""
        docs = list(documents)
        if not docs:
            return 0
        
        # ChromaDB has a max batch size limit, so we need to chunk the documents
        # Using a conservative batch size to avoid errors
        batch_size = 4000
        total_added = 0
        
        for i in range(0, len(docs), batch_size):
            batch = docs[i:i + batch_size]
            self.vectorstore.add_documents(batch)
            total_added += len(batch)
        
        self.vectorstore.persist()
        return total_added

    def clear(self) -> None:
        """Drop the underlying Chroma collection."""
        self.vectorstore.delete_collection()
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def retriever(self, k: int = 6, source: Optional[str] = None):
        """Return a retriever optionally filtered by metadata source."""
        search_kwargs = {"k": k}
        if source:
            search_kwargs["filter"] = {"source": source}
        return self.vectorstore.as_retriever(search_kwargs=search_kwargs)


vector_manager = VectorStoreManager()


