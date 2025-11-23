"""Vectorstore utilities built on top of Chroma with OpenAI embeddings."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Iterable, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

from dotenv import load_dotenv
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

# Load .env file before creating any OpenAI clients
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# LangChain v1 import
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """Thin wrapper that encapsulates Chroma persistence and retriever helpers."""

    def __init__(
        self,
        user_id: int,
        persist_directory: str = "data/vectorstore",
        collection_name: Optional[str] = None,
    ) -> None:
        os.makedirs(persist_directory, exist_ok=True)
        self.persist_directory = persist_directory
        # Use user-specific collection name (should be email-based if provided via get_vector_manager)
        self.collection_name = collection_name or f"construction_docs_user_{user_id}"
        self.user_id = user_id
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
        logger.info(f"🔐 Creating vectorstore for user {user_id} - Collection: {self.collection_name}, Directory: {self.persist_directory}")
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def add_documents(self, documents: Iterable[Document]) -> int:
        """Add a batch of LangChain Documents to the store with parallel threading for faster embedding."""
        docs = list(documents)
        if not docs:
            return 0
        
        logger.info(f"📥 Adding {len(docs)} documents to vectorstore...")
        
        # Use ThreadPoolExecutor to speed up embedding (I/O bound operation)
        # Split documents into batches for parallel processing
        num_workers = min(8, len(docs) // 50 + 1)  # Limit to 8 workers max to avoid API rate limits
        batch_size = max(50, len(docs) // num_workers)  # At least 50 docs per batch
        
        logger.info(f"⚡ Using {num_workers} threads for parallel embedding (batch size: {batch_size})")
        
        # Process documents in parallel batches
        batches = [docs[i:i + batch_size] for i in range(0, len(docs), batch_size)]
        
        # Embed documents in parallel using threads
        all_embeddings = []
        all_metadatas = []
        all_doc_texts = []
        all_ids = []
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # Submit all batches
            future_to_batch = {executor.submit(_embed_documents_batch, batch): batch for batch in batches}
            
            # Collect results as they complete
            for future in as_completed(future_to_batch):
                try:
                    embeddings, metadatas, doc_texts, ids = future.result()
                    all_embeddings.extend(embeddings)
                    all_metadatas.extend(metadatas)
                    all_doc_texts.extend(doc_texts)
                    all_ids.extend(ids)
                except Exception as e:
                    batch = future_to_batch[future]
                    logger.error(f"❌ Error embedding batch of {len(batch)} documents: {e}")
        
        if not all_embeddings:
            logger.error("❌ No documents were successfully embedded")
            return 0
        
        logger.info(f"✅ Embedded {len(all_embeddings)} documents, adding to ChromaDB...")
        
        # Add to ChromaDB using collection.add with pre-computed embeddings
        collection = self.vectorstore._collection
        
        # ChromaDB has a max batch size limit, so we need to chunk
        chroma_batch_size = 4000
        total_added = 0
        
        for i in range(0, len(all_ids), chroma_batch_size):
            batch_ids = all_ids[i:i + chroma_batch_size]
            batch_embeddings = all_embeddings[i:i + chroma_batch_size]
            batch_metadatas = all_metadatas[i:i + chroma_batch_size]
            batch_documents = all_doc_texts[i:i + chroma_batch_size]
            
            collection.add(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas,
                documents=batch_documents
            )
            total_added += len(batch_ids)
        
        self.vectorstore.persist()
        logger.info(f"✅ Successfully added {total_added} documents to vectorstore")
        return total_added

    def clear(self) -> None:
        """Drop the underlying Chroma collection."""
        self.vectorstore.delete_collection()
        self.vectorstore = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )

    def delete_by_metadata(self, filename: Optional[str] = None, path: Optional[str] = None, source: Optional[str] = None, user_id: Optional[int] = None) -> int:
        """Delete documents from Chroma by metadata filters."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Build the where clause for Chroma delete
            where_clause = {}
            
            # Always filter by user_id if provided
            if user_id is not None:
                where_clause["user_id"] = user_id
            
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
        """Return a retriever optionally filtered by metadata source and user_id."""
        search_kwargs = {"k": k}
        # Always filter by user_id to ensure data isolation
        filter_dict = {"user_id": self.user_id}
        if source:
            filter_dict["source"] = source
        search_kwargs["filter"] = filter_dict
        return self.vectorstore.as_retriever(search_kwargs=search_kwargs)


def _embed_documents_batch(docs_batch: List[Document]) -> tuple:
    """Helper function to embed a batch of documents in a worker thread.
    
    Returns:
        tuple: (embeddings, metadatas, documents, ids)
    """
    # Initialize embeddings (thread-safe)
    embeddings = OpenAIEmbeddings(model="text-embedding-3-large")
    
    # Extract text content and metadata
    texts = [doc.page_content for doc in docs_batch]
    metadatas = [doc.metadata for doc in docs_batch]
    
    # Generate embeddings
    try:
        embedded_vectors = embeddings.embed_documents(texts)
        
        # Generate unique IDs for each document
        ids = [str(uuid.uuid4()) for _ in docs_batch]
        
        # Add user_id to metadata if present
        user_id = metadatas[0].get("user_id") if metadatas else None
        if user_id:
            for meta in metadatas:
                meta["user_id"] = user_id
            
        return (embedded_vectors, metadatas, texts, ids)
    except Exception as e:
        logger.error(f"❌ Error embedding batch: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Return empty results on error
        return ([], [], [], [])


# Global vector manager - will be created per user
# This is kept for backward compatibility but should not be used directly
# Instead, create VectorStoreManager instances per user
def get_vector_manager(user_id: int) -> VectorStoreManager:
    """Get a VectorStoreManager instance for a specific user with email-based isolation."""
    # Get user email for better isolation
    try:
        from .auth import get_user_by_id
        user = get_user_by_id(user_id)
        if user:
            user_email = user.get("email", "").replace("@", "_at_").replace(".", "_")
            # Use email-based collection name and persist directory
            collection_name = f"construction_docs_user_{user_email}"
            persist_directory = f"data/vectorstore/user_{user_email}"
        else:
            # Fallback to user_id if email not found
            collection_name = f"construction_docs_user_{user_id}"
            persist_directory = f"data/vectorstore/user_{user_id}"
    except Exception as e:
        logger.warning(f"Failed to get user email for user {user_id}: {e}, using user_id")
        collection_name = f"construction_docs_user_{user_id}"
        persist_directory = f"data/vectorstore/user_{user_id}"
    
    return VectorStoreManager(
        user_id=user_id,
        persist_directory=persist_directory,
        collection_name=collection_name
    )


