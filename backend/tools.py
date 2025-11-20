"""Shared data registry and LangChain v1 tool definitions with generic spreadsheet support.

Based on: https://docs.langchain.com/oss/python/langchain/tools
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional
import json

import pandas as pd
from langchain_experimental.agents.agent_toolkits import (
    create_pandas_dataframe_agent,
)
# LangChain v1 imports - standardized paths
from langchain_core.documents import Document
from langchain_core.tools import Tool, StructuredTool
from pydantic import BaseModel, Field

from .vectorstore import VectorStoreManager, vector_manager

logger = logging.getLogger(__name__)


class DataRegistry:
    """Stores uploaded DataFrames grouped by semantic category with structure metadata."""

    def __init__(self) -> None:
        self._frames: Dict[str, Dict[str, pd.DataFrame]] = defaultdict(dict)
        self._structures: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)

    def clear_category(self, category: str) -> None:
        self._frames.pop(category, None)
        self._structures.pop(category, None)

    def clear_all(self) -> None:
        self._frames.clear()
        self._structures.clear()

    def register(self, category: str, name: str, df: pd.DataFrame, structure: Optional[Dict[str, Any]] = None) -> None:
        self._frames[category][name] = df
        if structure:
            self._structures[category][name] = structure

    def unregister(self, category: str, name: str) -> None:
        self._frames.get(category, {}).pop(name, None)
        self._structures.get(category, {}).pop(name, None)

    def categories(self) -> List[str]:
        return list(self._frames.keys())

    def names(self, category: str) -> List[str]:
        return list(self._frames.get(category, {}).keys())

    def get(self, category: str, name: Optional[str] = None) -> Optional[pd.DataFrame]:
        frames = self._frames.get(category)
        if not frames:
            return None
        if name:
            return frames.get(name)
        if len(frames) == 0:
            return None
        combined = pd.concat(frames.values(), ignore_index=True)
        return combined

    def get_structure(self, category: str, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get structure metadata for a table."""
        structures = self._structures.get(category)
        if not structures:
            return None
        if name:
            return structures.get(name)
        # Return combined structure info
        all_structures = list(structures.values())
        if not all_structures:
            return None
        return {
            "combined_tables": len(all_structures),
            "tables": {name: struct for name, struct in structures.items()}
        }

    def list_all_tables(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all available tables with their metadata."""
        result = {}
        for category, frames in self._frames.items():
            tables = []
            for name, df in frames.items():
                structure = self._structures.get(category, {}).get(name, {})
                tables.append({
                    "name": name,
                    "category": category,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": list(df.columns),
                    "structure": structure,
                })
            result[category] = tables
        return result

    def summary(self) -> Dict[str, List[str]]:
        return {category: list(names.keys()) for category, names in self._frames.items()}


data_registry = DataRegistry()


def _format_docs(docs: Iterable[Document]) -> str:
    docs_list = list(docs)
    if not docs_list:
        logger.info("📄 No documents found for retrieval")
        return "No documents found for this request."
    
    logger.info(f"📄 Retrieved {len(docs_list)} document(s)")
    rendered = []
    for i, doc in enumerate(docs_list, 1):
        meta = ", ".join(
            f"{k}:{v}"
            for k, v in doc.metadata.items()
            if k in {"source", "filename", "page", "row_index", "sheet_name", "table_name"}
        )
        logger.info(f"   {i}. {meta} (content length: {len(doc.page_content)} chars)")
        rendered.append(f"[{meta}] {doc.page_content}")
    return "\n\n".join(rendered)


def _build_pandas_agent(llm, df: pd.DataFrame) -> Any:
    """Build a pandas dataframe agent (returns a runnable/graph in LangChain v1)."""
    return create_pandas_dataframe_agent(
        llm,
        df,
        allow_dangerous_code=True,  # Required for pandas agent to execute code
        handle_parsing_errors=True,
        verbose=False,
    )


def _generic_spreadsheet_runner(llm):
    """Generic spreadsheet tool runner that works with any uploaded table."""
    def _run(query: str) -> str:
        """
        Query any spreadsheet table using natural language.
        The agent will automatically determine which table(s) to use.
        Format: table=<table_name>::question=<your question>
        Or just: <your question> (agent will infer the table)
        """
        logger.info(f"📊 Generic Spreadsheet Query - Input: {query[:200]}...")
        
        # Try to parse table name if provided
        if "::" in query and "table=" in query:
            parts = query.split("::")
            table_name = None
            question = query
            for part in parts:
                if part.startswith("table="):
                    table_name = part.split("=", 1)[1].strip()
                    question = "::".join([p for p in parts if not p.startswith("table=")])
                    break
        else:
            table_name = None
            question = query
        
        # Get all spreadsheet tables
        tables = data_registry.list_all_tables().get("spreadsheet", [])
        if not tables:
            logger.warning("⚠️  No spreadsheet tables available")
            return "No spreadsheet data has been uploaded yet. Please upload CSV or Excel files first."
        
        logger.info(f"📋 Found {len(tables)} spreadsheet table(s)")
        
        # If table name specified, use that one
        if table_name:
            logger.info(f"🎯 Using specific table: {table_name}")
            df = data_registry.get("spreadsheet", table_name)
            if df is None or df.empty:
                available = [t["name"] for t in tables]
                logger.warning(f"⚠️  Table '{table_name}' not found. Available: {available}")
                return f"Table '{table_name}' not found. Available tables: {available}"
            logger.info(f"✅ Loaded table '{table_name}' with {len(df)} rows, {len(df.columns)} columns")
            agent = _build_pandas_agent(llm, df)
        else:
            # Combine all tables for analysis
            logger.info("🔄 Combining all tables for analysis")
            df = data_registry.get("spreadsheet")
            if df is None or df.empty:
                return "No spreadsheet data available."
            logger.info(f"✅ Combined dataset: {len(df)} rows, {len(df.columns)} columns")
            agent = _build_pandas_agent(llm, df)
        
        # Execute query
        logger.info(f"🔍 Executing pandas query: {question[:200]}...")
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    output = getattr(last_msg, "content", str(last_msg))
                    logger.info(f"✅ Query completed. Output length: {len(output)} chars")
                    return output
        except Exception as e:
            logger.warning(f"⚠️  First invocation method failed: {e}, trying fallback")
            try:
                result = agent.invoke({"input": question})
                output = result.get("output", "No output produced.")
                logger.info(f"✅ Query completed (fallback). Output length: {len(output)} chars")
                return output
            except Exception as e2:
                logger.error(f"❌ Query execution failed: {e2}")
                return f"Error executing query: {str(e2)}"
        logger.warning("⚠️  No output produced")
        return "No output produced."

    return _run


def _multi_table_analysis_runner(llm):
    """Tool for analyzing across multiple tables with joins and aggregations."""
    def _run(analysis_request: str) -> str:
        """
        Perform complex multi-table analysis including joins, filters, aggregations.
        Format: tables=<table1,table2>::operation=<description>
        Or natural language describing the multi-table operation.
        """
        tables = data_registry.list_all_tables().get("spreadsheet", [])
        if len(tables) < 1:
            return "Need at least one table for analysis. Upload CSV/Excel files first."
        
        # Parse if structured format provided
        if "::" in analysis_request and "tables=" in analysis_request:
            parts = analysis_request.split("::")
            table_names = []
            operation = analysis_request
            for part in parts:
                if part.startswith("tables="):
                    table_names = [t.strip() for t in part.split("=", 1)[1].split(",")]
                    operation = "::".join([p for p in parts if not p.startswith("tables=")])
                    break
        else:
            # Let agent figure out which tables to use
            table_names = None
            operation = analysis_request
        
        # Get DataFrames
        dfs = {}
        if table_names:
            for name in table_names:
                df = data_registry.get("spreadsheet", name)
                if df is not None:
                    dfs[name] = df
        else:
            # Use all tables
            for table_info in tables:
                df = data_registry.get("spreadsheet", table_info["name"])
                if df is not None:
                    dfs[table_info["name"]] = df
        
        if not dfs:
            return "No valid tables found for analysis."
        
        # Build a combined agent with all tables
        # For multi-table operations, we'll create a description and let pandas agent handle it
        if len(dfs) == 1:
            df = list(dfs.values())[0]
        else:
            # Combine with a source column
            combined_dfs = []
            for name, df in dfs.items():
                df_copy = df.copy()
                df_copy["_source_table"] = name
                combined_dfs.append(df_copy)
            df = pd.concat(combined_dfs, ignore_index=True)
        
        agent = _build_pandas_agent(llm, df)
        
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": operation}]})
            if isinstance(result, dict) and "messages" in result:
                messages = result["messages"]
                if messages:
                    last_msg = messages[-1]
                    return getattr(last_msg, "content", str(last_msg))
        except Exception:
            try:
                result = agent.invoke({"input": operation})
                return result.get("output", "No output produced.")
            except Exception as e:
                return f"Error executing multi-table analysis: {str(e)}"
        return "No output produced."

    return _run


class ListTablesInput(BaseModel):
    """Input schema for List_Available_Tables tool."""
    query: str = Field(default="", description="Optional query string. Can be empty - tool lists all tables regardless.")

def _list_tables_runner(query: str = "") -> str:
    """List all available spreadsheet tables with their structures.
    
    Args:
        query: Optional query string (can be empty). The tool works the same regardless of query.
    """
    # Handle different input types (string or dict from agent)
    if isinstance(query, dict):
        # Extract the actual query string from dict format
        query_str = query.get('__arg1', query.get('query', ''))
    else:
        query_str = str(query) if query else ""
    
    logger.info(f"📋 Listing all available tables...")
    
    # Check what's in the registry
    all_categories = data_registry.categories()
    logger.info(f"📊 Data registry categories: {all_categories}")
    
    tables_info = data_registry.list_all_tables()
    logger.info(f"📊 Tables info: {tables_info}")
    
    if not tables_info:
        logger.warning("⚠️  No tables found in registry, attempting to reload from file registry...")
        # Try to reload tables from file registry
        try:
            from .ingestion import reload_tables_from_registry
            reloaded = reload_tables_from_registry()
            if reloaded > 0:
                logger.info(f"✅ Reloaded {reloaded} table(s) from file registry")
                tables_info = data_registry.list_all_tables()
            else:
                summary = data_registry.summary()
                logger.info(f"📊 Registry summary: {summary}")
                return "No tables have been uploaded yet. Please upload CSV or Excel files first."
        except Exception as e:
            logger.error(f"❌ Error reloading tables: {e}")
            summary = data_registry.summary()
            logger.info(f"📊 Registry summary: {summary}")
            return "No tables have been uploaded yet. Please upload CSV or Excel files first."
    
    result_lines = []
    for category, tables in tables_info.items():
        result_lines.append(f"\n{category.upper()} Tables:")
        logger.info(f"📋 Category '{category}': {len(tables)} table(s)")
        for table in tables:
            result_lines.append(f"\n  Table: {table['name']}")
            result_lines.append(f"    Rows: {table['rows']}, Columns: {table['columns']}")
            result_lines.append(f"    Columns: {', '.join(table['column_names'])}")
            if table.get('structure'):
                structure = table['structure']
                if structure.get('numeric_columns'):
                    result_lines.append(f"    Numeric columns: {', '.join(structure['numeric_columns'])}")
                if structure.get('potential_keys'):
                    result_lines.append(f"    Potential keys: {', '.join(structure['potential_keys'])}")
    
    result = "\n".join(result_lines)
    logger.info(f"✅ Listed {sum(len(tables) for tables in tables_info.values())} table(s)")
    return result


def _synthesis_tool_runner(llm):
    def _run(context: str) -> str:
        system = (
            "You synthesize final answers by combining information from structured data (spreadsheets) "
            "and unstructured documents (PDFs, DOCX, etc.). Use the provided context, include bullet insights, "
            "and cite sources (table names, row indices, document filenames)."
        )
        response = llm.invoke(
            [
                ("system", system),
                (
                    "user",
                    "Context to synthesize:\n"
                    f"{context}\n\n"
                    "Produce the final response with citations inline.",
                ),
            ]
        )
        return response.content

    return _run


def build_tools(llm, manager: VectorStoreManager = vector_manager) -> List[Tool]:
    """Build all available tools for the agent."""
    
    # Document retrievers
    pdf_retriever = manager.retriever(source="pdf")
    docx_retriever = manager.retriever(source="docx")
    pptx_retriever = manager.retriever(source="pptx")
    csv_retriever = manager.retriever(source="csv")
    excel_retriever = manager.retriever(source="excel")
    image_retriever = manager.retriever(source="image")
    general_retriever = manager.retriever()

    tools = [
        # General retrieval - PUT FIRST to encourage proactive searching
        Tool(
            name="General_Document_Retriever",
            func=lambda q: _format_docs(general_retriever.invoke(q)),
            description=(
                "PRIMARY SEARCH TOOL: Use this FIRST when you don't have concrete information to answer a question. "
                "Searches across ALL uploaded documents (PDFs, DOCX, PPTX, CSV rows, Excel rows, images). "
                "USE THIS PROACTIVELY - if a question might be answered in documents, search here FIRST. "
                "This is your go-to tool for questions about project details, timelines, contracts, requirements, specifications, etc. "
                "NEVER say 'I cannot find' without using this tool with multiple search term variations."
            ),
        ),
        
        # Document retrieval tools
        Tool(
            name="PDF_Document_Retriever",
            func=lambda q: _format_docs(pdf_retriever.invoke(q)),
            description=(
                "Use to search and retrieve relevant content from PDF documents (contracts, manuals, regulations, project plans). "
                "Always cite the filename and page number when referencing PDF content. "
                "USE THIS PROACTIVELY for questions about contracts, timelines, project details, compliance, regulations, specifications. "
                "If a question might be answered in a contract or document, search it automatically. "
                "Use this AFTER General_Document_Retriever if you need PDF-specific results."
            ),
        ),
        Tool(
            name="DOCX_Document_Retriever",
            func=lambda q: _format_docs(docx_retriever.invoke(q)),
            description=(
                "Use to search and retrieve relevant content from Word documents (DOCX files). "
                "Cite the filename when referencing DOCX content. "
                "USE THIS PROACTIVELY for questions about project details, contracts, specifications, requirements that might be in Word documents."
            ),
        ),
        Tool(
            name="PPTX_Document_Retriever",
            func=lambda q: _format_docs(pptx_retriever.invoke(q)),
            description=(
                "Use to search and retrieve relevant content from PowerPoint presentations (PPTX files). "
                "Cite the filename when referencing PPTX content. "
                "USE THIS PROACTIVELY for questions about project presentations, plans, or summaries."
            ),
        ),
        Tool(
            name="Image_Text_Retriever",
            func=lambda q: _format_docs(image_retriever.invoke(q)),
            description=(
                "Use to search text extracted from images using OCR. "
                "Cite the image filename when referencing image content."
            ),
        ),
        
        # Spreadsheet tools (generic, file-agnostic)
        Tool(
            name="Generic_Spreadsheet_Query_Tool",
            func=_generic_spreadsheet_runner(llm),
            description=(
                "Use to query ANY uploaded spreadsheet table (CSV or Excel) using natural language. "
                "This tool automatically understands table structures and can perform filtering (>, <, >=, <=, =, !=, contains, in/not in), "
                "grouping, aggregations (sum, avg, count, min, max), and basic analysis. "
                "You can specify a table name with 'table=<name>::question=<query>' or just ask a question and the tool will infer the right table(s). "
                "This is the PRIMARY tool for structured data queries. "
                "USE THIS PROACTIVELY for questions about timelines, schedules, durations, costs, budgets, quantities, resources, etc. "
                "If a question involves numbers, dates, or calculations, search spreadsheets automatically."
            ),
        ),
        Tool(
            name="Multi_Table_Analysis_Tool",
            func=_multi_table_analysis_runner(llm),
            description=(
                "Use for complex operations across multiple spreadsheet tables. "
                "Supports joining tables, cross-table filtering, aggregations across tables, and combining data from multiple sources. "
                "Format: 'tables=<table1,table2>::operation=<description>' or use natural language describing the multi-table operation. "
                "The tool will automatically infer relationships and join keys when possible."
            ),
        ),
        StructuredTool.from_function(
            func=_list_tables_runner,
            name="List_Available_Tables",
            description=(
                "Use to see what spreadsheet tables are available, their column names, row counts, and structure information. "
                "Call this first if you're unsure what tables exist or what columns they contain. "
                "You can call this tool with an empty string or any query - it will list all tables regardless."
            ),
            args_schema=ListTablesInput,
        ),
        
        # Row-level retrieval tools
        Tool(
            name="CSV_Row_Retriever",
            func=lambda q: _format_docs(csv_retriever.invoke(q)),
            description=(
                "Use to retrieve specific CSV rows by semantic similarity to the query. "
                "Useful for finding examples or specific records. Cite row indices."
            ),
        ),
        Tool(
            name="Excel_Row_Retriever",
            func=lambda q: _format_docs(excel_retriever.invoke(q)),
            description=(
                "Use to retrieve specific Excel rows by semantic similarity. "
                "Useful for finding examples or specific records. Cite sheet name and row indices."
            ),
        ),
        
        # Synthesis
        Tool(
            name="Answer_Synthesizer",
            func=_synthesis_tool_runner(llm),
            description=(
                "Use at the end once you've collected evidence from both structured (spreadsheet) and unstructured (document) sources. "
                "Provide all collected context to generate a comprehensive, well-cited final answer."
            ),
        ),
    ]
    
    return tools
