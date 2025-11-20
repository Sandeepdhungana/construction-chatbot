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

    def delete_by_metadata(self, filename: Optional[str] = None, path: Optional[str] = None, source: Optional[str] = None) -> int:
        """Delete documents from Chroma by metadata filters."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Build the where clause for Chroma delete
            where_clause = {}
            
            if filename:
                where_clause["filename"] = filename
            if path:
                where_clause["path"] = path
            if source:
                where_clause["source"] = source
            
            if not where_clause:
                logger.warning("No metadata filters provided for deletion")
                return 0
            
            logger.info(f"🔍 Searching for documents to delete with filters: {where_clause}")
            
            # Access the underlying Chroma collection
            collection = self.vectorstore._collection
            
            # Query to get matching IDs
            # Chroma's get method returns a dict with 'ids', 'metadatas', 'documents', etc.
            results = collection.get(
                where=where_clause,
                include=["metadatas", "documents"]
            )
            
            if results and results.get("ids") and len(results["ids"]) > 0:
                ids_to_delete = results["ids"]
                logger.info(f"🗑️  Found {len(ids_to_delete)} document(s) to delete from vectorstore")
                
                # Delete by IDs using the collection's delete method
                collection.delete(ids=ids_to_delete)
                self.vectorstore.persist()
                logger.info(f"✅ Successfully deleted {len(ids_to_delete)} document(s) from vectorstore")
                return len(ids_to_delete)
            else:
                logger.info("No documents found matching the filters")
                return 0
                
        except Exception as e:
            logger.error(f"❌ Error deleting documents from vectorstore: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return 0

    def retriever(self, k: int = 6, source: Optional[str] = None):
        """Return a retriever optionally filtered by metadata source."""
        search_kwargs = {"k": k}
        if source:
            search_kwargs["filter"] = {"source": source}
        return self.vectorstore.as_retriever(search_kwargs=search_kwargs)


vector_manager = VectorStoreManager()


