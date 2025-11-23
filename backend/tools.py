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

from .vectorstore import VectorStoreManager


logger = logging.getLogger(__name__)


class DataRegistry:

    """Stores uploaded DataFrames grouped by semantic category with structure metadata."""

    def __init__(self, user_id: Optional[int] = None) -> None:
        # Store data per user: {user_id: {category: {name: df}}}
        self._frames: Dict[int, Dict[str, Dict[str, pd.DataFrame]]] = defaultdict(lambda: defaultdict(dict))
        self._structures: Dict[int, Dict[str, Dict[str, Dict[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
        self.user_id = user_id

    def clear_category(self, category: str, user_id: Optional[int] = None) -> None:
        uid = user_id or self.user_id
        if uid is None:
            return
        self._frames[uid].pop(category, None)
        self._structures[uid].pop(category, None)

    def clear_all(self, user_id: Optional[int] = None) -> None:
        uid = user_id or self.user_id
        if uid is None:
            self._frames.clear()
            self._structures.clear()
        else:
            self._frames.pop(uid, None)
            self._structures.pop(uid, None)

    def register(self, category: str, name: str, df: pd.DataFrame, structure: Optional[Dict[str, Any]] = None, user_id: Optional[int] = None) -> None:
        uid = user_id or self.user_id
        if uid is None:
            raise ValueError("user_id must be provided")
        self._frames[uid][category][name] = df
        if structure:
            self._structures[uid][category][name] = structure

    def unregister(self, category: str, name: str, user_id: Optional[int] = None) -> None:
        uid = user_id or self.user_id
        if uid is None:
            return
        self._frames[uid].get(category, {}).pop(name, None)
        self._structures[uid].get(category, {}).pop(name, None)

    def categories(self, user_id: Optional[int] = None) -> List[str]:
        uid = user_id or self.user_id
        if uid is None:
            return []
        return list(self._frames[uid].keys())

    def names(self, category: str, user_id: Optional[int] = None) -> List[str]:
        uid = user_id or self.user_id
        if uid is None:
            return []
        return list(self._frames[uid].get(category, {}).keys())

    def get(self, category: str, name: Optional[str] = None, user_id: Optional[int] = None) -> Optional[pd.DataFrame]:
        uid = user_id or self.user_id
        if uid is None:
            return None
        frames = self._frames[uid].get(category)
        if not frames:
            return None
        if name:
            return frames.get(name)
        if len(frames) == 0:
            return None
        combined = pd.concat(frames.values(), ignore_index=True)
        return combined

    def get_structure(self, category: str, name: Optional[str] = None, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Get structure metadata for a table."""
        uid = user_id or self.user_id
        if uid is None:
            return None
        structures = self._structures[uid].get(category)
        if not structures:
            return None
        if name:
            return structures.get(name)
        all_structures = list(structures.values())
        if not all_structures:
            return None
        return {
            "combined_tables": len(all_structures),
            "tables": {name: struct for name, struct in structures.items()}
        }

    def list_all_tables(self, user_id: Optional[int] = None) -> Dict[str, List[Dict[str, Any]]]:
        """List all available tables with their metadata."""
        uid = user_id or self.user_id
        if uid is None:
            return {}
        result = {}
        for category, frames in self._frames[uid].items():
            tables = []
            for name, df in frames.items():
                structure = self._structures[uid].get(category, {}).get(name, {})
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

    def summary(self, user_id: Optional[int] = None) -> Dict[str, List[str]]:
        uid = user_id or self.user_id
        if uid is None:
            return {}
        return {category: list(names.keys()) for category, names in self._frames[uid].items()}


# Global registry instance (backward compatibility)
data_registry = DataRegistry()

# Cache for DataRegistry instances per user
_registry_cache: Dict[int, DataRegistry] = {}

# Function to get user-specific registry
def get_data_registry(user_id: int, reload: bool = True) -> DataRegistry:
    """Get a DataRegistry instance for a specific user and reload tables from file registry."""
    # Always create a new instance to ensure data isolation - don't use cache
    # Cache can cause data leakage between requests
    registry = DataRegistry(user_id=user_id)
    
    # Reload tables from file registry to ensure data is available
    if reload:
        try:
            # Import here to avoid circular import
            from .ingestion import reload_tables_from_registry
            logger.info(f"🔄 Reloading data registry for user {user_id}")
            reload_tables_from_registry(user_id, data_registry_instance=registry)
            # Log what was loaded
            tables = registry.list_all_tables(user_id=user_id)
            logger.info(f"📊 Loaded tables for user {user_id}: {tables}")
        except Exception as e:
            logger.warning(f"Failed to reload tables for user {user_id}: {e}")
    
    return registry


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


def _build_pandas_agent(llm, df: pd.DataFrame, table_name: Optional[str] = None) -> Any:
    """Build a pandas dataframe agent (returns a runnable/graph in LangChain v1).
    
    IMPORTANT: Only pass a SINGLE table DataFrame - never pass merged/concatenated DataFrames.
    """
    # Ensure we're working with a clean copy to avoid any accidental modifications
    df_clean = df.copy()
    
    # Validate that DataFrame doesn't look like it was merged (check for excessive NaN columns)
    nan_ratio = df_clean.isna().sum().sum() / (len(df_clean) * len(df_clean.columns))
    if nan_ratio > 0.5:
        logger.warning(f"⚠️  DataFrame has high NaN ratio ({nan_ratio:.2%}) - may be incorrectly merged")
    
    if table_name:
        logger.info(f"🔧 Building pandas agent for table '{table_name}' with {len(df_clean)} rows, {len(df_clean.columns)} columns")
    
    # CRITICAL: Pass as a SINGLE DataFrame (not a list) to ensure agent only works with this ONE table
    # Passing a list would give the agent access to multiple DataFrames and enable merging/joining
    
    # Custom prefix to ensure agent shows actual data values
    prefix = """You are working with a pandas DataFrame. When answering questions:
1. ALWAYS execute pandas code to retrieve the actual data values
2. NEVER say "not shown in the observation" or "can be found in the dataframe" - SHOW THE ACTUAL VALUES
3. For each field requested, display the actual value from the DataFrame
4. Use df.loc, df.iloc, or df[df['column'] == value] to retrieve specific rows
5. Print or display the actual DataFrame values, not placeholders
6. Format your answer clearly showing all requested information with actual values
7. Example: If asked about Worker_ID 12, show: Worker_ID: 12, Name: John Doe, Trade: Electrician, etc.
8. DO NOT use placeholders - always show the real data from the DataFrame"""
    
    return create_pandas_dataframe_agent(
        llm,
        df_clean,  # Single DataFrame - agent will only work with this table
        allow_dangerous_code=True,  # Required for pandas agent to execute code
        handle_parsing_errors=True,
        verbose=False,
        prefix=prefix,  # Custom prefix to force showing actual values
    )


def _clean_pandas_output(output: str) -> str:
    """Clean pandas output to remove NaN-heavy results and improve readability."""
    if not output:
        return output
    
    # Check if output contains mostly NaN values
    lines = output.split('\n')
    cleaned_lines = []
    skip_next_nan_row = False
    
    for i, line in enumerate(lines):
        # Skip rows that are mostly NaN (e.g., "1026        NaN  NaN   NaN  ...")
        if 'NaN' in line and line.count('NaN') > 3:
            # Check if this is a data row (not a header)
            if not any(keyword in line.lower() for keyword in ['worker_id', 'name', 'trade', 'columns', 'rows', 'index']):
                logger.warning(f"⚠️  Skipping NaN-heavy row: {line[:100]}")
                skip_next_nan_row = True
                continue
        
        # Skip empty DataFrames or results with only NaN
        if '[1 rows x' in line and 'columns]' in line and i > 0:
            # Check previous line for NaN content
            if i > 0 and 'NaN' in lines[i-1]:
                logger.warning(f"⚠️  Skipping empty/NaN DataFrame result")
                continue
        
        cleaned_lines.append(line)
    
    cleaned_output = '\n'.join(cleaned_lines)
    
    # If cleaned output is significantly shorter, it likely had NaN issues
    if len(cleaned_output) < len(output) * 0.5:
        logger.warning("⚠️  Output was heavily cleaned due to NaN values")
    
    return cleaned_output



def _generic_spreadsheet_runner(llm, registry: DataRegistry, uid: Optional[int] = None):
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
        tables = registry.list_all_tables(user_id=uid).get("spreadsheet", [])
        if not tables:
            logger.warning("⚠️  No spreadsheet tables available")
            return "No spreadsheet data has been uploaded yet. Please upload CSV or Excel files first."
        
        logger.info(f"📋 Found {len(tables)} spreadsheet table(s)")
        
        # If table name specified, use that one
        if table_name:
            logger.info(f"🎯 Using specific table: {table_name}")
            df = registry.get("spreadsheet", table_name, user_id=uid)
            if df is None or df.empty:
                available = [t["name"] for t in tables]
                logger.warning(f"⚠️  Table '{table_name}' not found. Available: {available}")
                return f"Table '{table_name}' not found. Available tables: {available}"
            if df is None:
                logger.error(f"❌ Failed to load table '{table_name}' - DataFrame is None")
                return f"Error: Could not load table '{table_name}'. The table may not be properly registered. Please try uploading the file again."
            logger.info(f"✅ Loaded table '{table_name}' with {len(df)} rows, {len(df.columns)} columns")
            agent = _build_pandas_agent(llm, df, table_name=table_name)
        else:
            # CRITICAL: Search ALL relevant tables individually, not merged
            # This ensures comprehensive answers when data spans multiple tables
            question_lower = question.lower()
            relevant_tables = []
            
            # Find all tables that might be relevant to the query
            for table_info in tables:
                table_name_check = table_info["name"].lower()
                column_names = table_info.get("column_names", [])
                columns = [col.lower() for col in column_names] if column_names else []
                
                # Check if query mentions table name or any columns
                is_relevant = (
                    table_name_check in question_lower or 
                    any(col in question_lower for col in columns if col and len(col) > 3) or
                    # If query is general (no specific table mentioned), include all tables
                    len(tables) <= 3  # If 3 or fewer tables, search all
                )
                
                if is_relevant:
                    relevant_tables.append(table_info["name"])
                    logger.info(f"🎯 Table '{table_info['name']}' identified as potentially relevant")
            
            # If no tables matched, search all tables (comprehensive search)
            if not relevant_tables:
                logger.info("📋 No specific tables matched, searching ALL tables for comprehensive results")
                relevant_tables = [t["name"] for t in tables]
            
            # If only one relevant table, use it directly
            if len(relevant_tables) == 1:
                table_name = relevant_tables[0]
                df = registry.get("spreadsheet", table_name, user_id=uid)
                if df is None or df.empty:
                    logger.error(f"❌ Failed to load table '{table_name}'")
                    return f"Error: Could not load table '{table_name}'. Please try uploading the file again."
                logger.info(f"✅ Using table '{table_name}' with {len(df)} rows, {len(df.columns)} columns")
                agent = _build_pandas_agent(llm, df, table_name=table_name)
            else:
                # Multiple relevant tables - search each one INDIVIDUALLY and return separate results
                logger.info(f"🔍 Searching {len(relevant_tables)} relevant table(s) individually: {relevant_tables}")
                all_results = []
                
                for table_name in relevant_tables:
                    try:
                        df = registry.get("spreadsheet", table_name, user_id=uid)
                        if df is None or df.empty:
                            logger.warning(f"⚠️  Skipping empty table '{table_name}'")
                            continue
                        
                        logger.info(f"📊 Querying table '{table_name}' individually ({len(df)} rows)...")
                        # Log DataFrame info to debug
                        logger.info(f"📋 DataFrame columns: {list(df.columns)}")
                        logger.info(f"📋 DataFrame shape: {df.shape}")
                        
                        table_agent = _build_pandas_agent(llm, df, table_name=table_name)
                        
                        # Enhance question to prevent NaN results and merging, and ensure actual data is shown
                        enhanced_question = (
                            f"{question}\n\n"
                            "CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:\n"
                            "1. Work ONLY with the current DataFrame - do NOT merge, join, or concatenate with other tables\n"
                            "2. You MUST execute pandas code to retrieve and DISPLAY the actual data values\n"
                            "3. NEVER say 'not shown in the observation' or 'can be found in the dataframe' - SHOW THE ACTUAL VALUES\n"
                            "4. For each field requested, display the actual value from the DataFrame\n"
                            "5. Use df.loc or df[df['column'] == value] to retrieve specific rows and SHOW all column values\n"
                            "6. Filter out rows with all NaN values before returning results\n"
                            "7. If a query would result in mostly NaN values, return 'No matching data found' instead\n"
                            "8. Provide a clear answer with ACTUAL DATA VALUES, formatted clearly\n"
                            "9. Example format: 'Worker_ID: 12, Name: John Doe, Trade: Electrician, Daily_Wage: 150.00, ...'\n"
                            "10. DO NOT use placeholders or say data exists without showing it - SHOW THE ACTUAL VALUES"
                        )
                        
                        # Query this specific table individually
                        # Pandas agent expects {"input": ...} format, not {"messages": ...}
                        try:
                            result = table_agent.invoke({"input": enhanced_question})
                            # Handle different response formats
                            if isinstance(result, dict):
                                # Try to get output from various possible keys
                                output = result.get("output", "")
                                if not output and "messages" in result:
                                    messages = result["messages"]
                                    if messages:
                                        last_msg = messages[-1]
                                        output = getattr(last_msg, "content", str(last_msg))
                                if not output:
                                    output = str(result)
                            else:
                                output = str(result)
                            
                            # Clean output to remove NaN-heavy results
                            output = _clean_pandas_output(output)
                            if output and output.strip() and "nan" not in output.lower()[:200]:
                                # Return results from each table separately, not merged
                                all_results.append(f"=== Results from table '{table_name}' ===\n{output}\n")
                                logger.info(f"✅ Found results in table '{table_name}'")
                            else:
                                logger.warning(f"⚠️  Skipping NaN-heavy output from table '{table_name}'")
                        except Exception as e:
                            logger.warning(f"⚠️  Error querying table '{table_name}': {e}")
                            # Try fallback with simpler question
                            try:
                                result = table_agent.invoke({"input": question})
                                output = result.get("output", "") if isinstance(result, dict) else str(result)
                                output = _clean_pandas_output(output)
                                if output and output.strip() and "nan" not in output.lower()[:200]:
                                    all_results.append(f"=== Results from table '{table_name}' ===\n{output}\n")
                                else:
                                    logger.warning(f"⚠️  Skipping NaN-heavy fallback output from table '{table_name}'")
                            except Exception as e2:
                                logger.error(f"❌ Fallback also failed for table '{table_name}': {e2}")
                                pass
                    except Exception as e:
                        logger.error(f"❌ Error processing table '{table_name}': {e}")
                        continue
                
                if all_results:
                    # Return results from each table separately, clearly labeled
                    combined_result = "\n".join(all_results)
                    logger.info(f"✅ Returned results from {len(all_results)} table(s) individually")
                    return combined_result
                else:
                    # Fallback: use first table if all searches failed
                    if tables:
                        first_table = tables[0]["name"]
                        df = registry.get("spreadsheet", first_table, user_id=uid)
                        if df is None or df.empty:
                            return f"Error: Could not load any tables. Please try uploading the files again."
                        logger.info(f"⚠️  All multi-table searches failed, using first table '{first_table}'")
                        agent = _build_pandas_agent(llm, df, table_name=first_table)
                    else:
                        return "No spreadsheet data available."

        
        # Execute query - let the agent decide how to search based on the question
        logger.info(f"🔍 Executing pandas query: {question[:200]}...")
        # Enhance question to prevent NaN results and merging, and ensure actual data is shown
        enhanced_question = (
            f"{question}\n\n"
            "CRITICAL INSTRUCTIONS - YOU MUST FOLLOW THESE:\n"
            "1. Work ONLY with the current DataFrame - do NOT merge, join, or concatenate with other tables\n"
            "2. You MUST execute pandas code to retrieve and DISPLAY the actual data values\n"
            "3. NEVER say 'not shown in the observation' or 'can be found in the dataframe' - SHOW THE ACTUAL VALUES\n"
            "4. For each field requested, display the actual value from the DataFrame\n"
            "5. Use df.loc or df[df['column'] == value] to retrieve specific rows and SHOW all column values\n"
            "6. Filter out rows with all NaN values before returning results\n"
            "7. If a query would result in mostly NaN values, return 'No matching data found' instead\n"
            "8. Provide a clear answer with ACTUAL DATA VALUES, formatted clearly\n"
            "9. Example format: 'Worker_ID: 12, Name: John Doe, Trade: Electrician, Daily_Wage: 150.00, ...'\n"
            "10. DO NOT use placeholders or say data exists without showing it - SHOW THE ACTUAL VALUES"
        )
        # Pandas agent expects {"input": ...} format, not {"messages": ...}
        try:
            result = agent.invoke({"input": enhanced_question})
            # Handle different response formats
            if isinstance(result, dict):
                output = result.get("output", "")
                if not output and "messages" in result:
                    messages = result["messages"]
                    if messages:
                        last_msg = messages[-1]
                        output = getattr(last_msg, "content", str(last_msg))
                if not output:
                    output = str(result)
            else:
                output = str(result)
            
            # Clean output to remove NaN-heavy results
            output = _clean_pandas_output(output)
            logger.info(f"✅ Query completed. Output length: {len(output)} chars")
            return output
        except Exception as e:
            logger.warning(f"⚠️  Query execution failed: {e}, trying fallback")
            try:
                # Try with simpler question
                result = agent.invoke({"input": question})
                output = result.get("output", "No output produced.") if isinstance(result, dict) else str(result)
                # Clean output to remove NaN-heavy results
                output = _clean_pandas_output(output)
                logger.info(f"✅ Query completed (fallback). Output length: {len(output)} chars")
                return output
            except Exception as e2:
                logger.error(f"❌ Query execution failed: {e2}")
                return f"Error executing query: {str(e2)}"
        logger.warning("⚠️  No output produced")
        return "No output produced."

    return _run



def _multi_table_analysis_runner(llm, registry: DataRegistry, uid: Optional[int] = None):
    """Tool for analyzing across multiple tables with joins and aggregations."""
    def _run(analysis_request: str) -> str:
        """
        Perform complex multi-table analysis including joins, filters, aggregations.
        Format: tables=<table1,table2>::operation=<description>
        Or natural language describing the multi-table operation.
        """
        tables = registry.list_all_tables(user_id=uid).get("spreadsheet", [])
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
                df = registry.get("spreadsheet", name, user_id=uid)
                if df is not None:
                    dfs[name] = df
        else:
            # Use all tables
            for table_info in tables:
                df = registry.get("spreadsheet", table_info["name"], user_id=uid)
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
        
        agent = _build_pandas_agent(llm, df, table_name=None)

        
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


class PaymentQueryInput(BaseModel):
    """Input schema for payment-related tools."""
    query: str = Field(default="", description="Optional query string. Can be empty string or JSON with filters like payment_type, entity_type, status.")


class NotificationQueryInput(BaseModel):
    """Input schema for notification-related tools."""
    query: str = Field(default="", description="Optional query string. Can be empty string or filter parameters.")

def _list_tables_runner(registry: DataRegistry, uid: Optional[int] = None):
    """List all available spreadsheet tables with their structures."""
    def _run(query: str = "") -> str:
        # Handle different input types (string or dict from agent)
        if isinstance(query, dict):
            # Extract the actual query string from dict format
            query_str = query.get('__arg1', query.get('query', ''))
        else:
            query_str = str(query) if query else ""
        
        logger.info(f"📋 Listing all available tables...")
        
        # Check what's in the registry
        all_categories = registry.categories(user_id=uid)
        logger.info(f"📊 Data registry categories: {all_categories}")
        
        tables_info = registry.list_all_tables(user_id=uid)
        logger.info(f"📊 Tables info: {tables_info}")
        
        if not tables_info:
            logger.warning("⚠️  No tables found in registry")
            summary = registry.summary(user_id=uid)
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
    return _run


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


def build_tools(llm, manager: VectorStoreManager, data_registry: Optional[DataRegistry] = None, user_id: Optional[int] = None) -> List[Tool]:
    """Build all available tools for the agent."""
    # Use provided registry or get user-specific one
    if data_registry is None:
        if user_id is not None:
            data_registry = get_data_registry(user_id)
        else:
            data_registry = DataRegistry()  # Fallback
    
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
            func=_generic_spreadsheet_runner(llm, data_registry, user_id),
            description=(
                "MANDATORY FOR CSV/EXCEL QUERIES: Use to query ANY uploaded spreadsheet table (CSV or Excel) using natural language. "
                "ALWAYS call List_Available_Tables FIRST to see what tables and columns exist. "
                "CRITICAL MULTI-TABLE SEARCH: This tool AUTOMATICALLY searches ALL relevant tables when you ask a question without specifying a table name. "
                "It will identify which tables are relevant based on column names and table names, then search ALL of them and combine results. "
                "This ensures comprehensive answers when data spans multiple CSV/Excel files. "
                "This tool automatically understands table structures, finds relevant columns, and can perform filtering (>, <, >=, <=, =, !=, contains, in/not in), "
                "grouping, aggregations (sum, avg, count, min, max), and basic analysis. "
                "You can specify a specific table with 'table=<name>::question=<query>' if you want to target one table, "
                "but by default it searches ALL relevant tables automatically and combines results. "
                "For complex queries spanning multiple tables that need joins or complex relationships, use Multi_Table_Analysis_Tool. "
                "This is the PRIMARY tool for structured data queries. "
                "USE THIS PROACTIVELY for questions about timelines, schedules, durations, costs, budgets, quantities, resources, etc. "
                "If a question involves numbers, dates, or calculations, search spreadsheets automatically - the tool will search ALL relevant tables. "
                "ALWAYS use this tool when CSV/Excel data exists - don't skip spreadsheet searches. "
                "Use together with Multi_Table_Analysis_Tool for cross-table queries, and with ERP tools and document retrievers for comprehensive answers."
            ),
        ),
        Tool(
            name="Multi_Table_Analysis_Tool",
            func=_multi_table_analysis_runner(llm, data_registry, user_id),
            description=(
                "MANDATORY FOR MULTI-TABLE QUERIES: Use for complex operations across MULTIPLE spreadsheet tables. "
                "CRITICAL: When information spans multiple CSV/Excel files, you MUST use this tool to combine data. "
                "Supports joining tables, cross-table filtering, aggregations across tables, and combining data from multiple sources. "
                "Format: 'tables=<table1,table2,table3>::operation=<description>' or use natural language describing the multi-table operation. "
                "The tool will automatically infer relationships and join keys when possible. "
                "Examples: "
                "'tables=workers,materials::operation=Find which workers are assigned to which materials' "
                "'tables=payments,invoices,projects::operation=Calculate total revenue per project' "
                "'tables=schedule,tasks::operation=Find tasks that are behind schedule' "
                "ALWAYS use this when you need to combine information from multiple CSV/Excel files. "
                "Don't just search one table - if multiple tables have relevant data, use this tool to analyze them together."
            ),
        ),
        Tool(
            name="List_Available_Tables",
            func=_list_tables_runner(data_registry, user_id),
            description=(
                "MANDATORY FIRST STEP: Use this to see what CSV/Excel tables are available, their column names, row counts, and structure information. "
                "ALWAYS call this FIRST before querying spreadsheets to understand what data is available. "
                "This shows you what columns exist so you can formulate better queries. "
                "You can call this tool with an empty string or any query - it will list all tables regardless. "
                "After seeing available tables, use Generic_Spreadsheet_Query_Tool to query the data."
            ),
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
        
        # Notification tools
        Tool(
            name="Send_Notification",
            func=lambda request: _send_notification_runner(request),
            description=(
                "Send a notification email to a recipient. Use this when you need to send payment reminders, payment requests, or custom notifications. "
                "Input format: JSON string with 'recipient_id' (int), 'notification_type' ('payment_reminder', 'payment_request', or 'custom'), "
                "'context' (optional dict with payment details, amounts, due dates, etc.), 'template' (optional custom template), "
                "and 'payment_link' (optional URL). Example: '{\"recipient_id\": 1, \"notification_type\": \"payment_reminder\", \"context\": {\"amount\": 5000, \"due_date\": \"2024-01-15\"}}'"
            ),
        ),
        StructuredTool.from_function(
            func=_list_recipients_runner(user_id) if user_id else lambda q: "User ID required",
            name="List_Notification_Recipients",
            description=(
                "List all notification recipients (vendors, workers, clients). "
                "Use this to find recipient IDs when you need to send notifications. "
                "Optional query parameter to filter by type: 'vendor', 'worker', or 'client'."
            ),
            args_schema=NotificationQueryInput,
        ),
        StructuredTool.from_function(
            func=_list_schedules_runner(user_id) if user_id else lambda q: "User ID required",
            name="List_Notification_Schedules",
            description=(
                "List all notification schedules. Use this to see what automated notifications are configured. "
                "Shows schedules with their recipients, types, intervals, and status."
            ),
            args_schema=NotificationQueryInput,
        ),
        StructuredTool.from_function(
            func=_get_notification_history_runner(user_id) if user_id else lambda q: "User ID required",
            name="Get_Notification_History",
            description=(
                "Get notification history/logs. Use this to check what notifications have been sent recently. "
                "Optional query can specify recipient_id as a number to filter by recipient."
            ),
            args_schema=NotificationQueryInput,
        ),
        
        # Payment Tools
        StructuredTool.from_function(
            func=_list_payments_runner(user_id) if user_id else lambda q: "User ID required",
            name="List_Payments",
            description=(
                "MANDATORY FOR PAYMENT QUESTIONS: List all payments in the ERP system. Shows payment type (receive/send), amounts, due dates, status, and related entities. "
                "ALWAYS call this when questions involve payments, invoices, or financial transactions. "
                "Also search CSV/Excel tables and documents for comprehensive payment information. "
                "Optional query can filter by payment_type ('receive' or 'send'), entity_type ('client', 'vendor', 'worker'), or status ('pending', 'paid', 'overdue'). "
                "Example: '{\"payment_type\": \"receive\", \"status\": \"pending\"}' "
                "Use this tool together with Generic_Spreadsheet_Query_Tool and document retrievers for complete answers."
            ),
            args_schema=PaymentQueryInput,
        ),
        StructuredTool.from_function(
            func=_get_payments_due_soon_runner(user_id) if user_id else lambda q: "User ID required",
            name="Get_Payments_Due_Soon",
            description=(
                "Get payments that are due soon. Shows payments due within specified days (default 7). "
                "Useful for identifying which payments need reminders sent. "
                "Optional query can specify days as a number (e.g., '14' for 14 days)."
            ),
            args_schema=PaymentQueryInput,
        ),
        StructuredTool.from_function(
            func=_get_overdue_payments_runner(user_id) if user_id else lambda q: "User ID required",
            name="Get_Overdue_Payments",
            description=(
                "Get all overdue payments. Shows payments that are past their due date and still pending. "
                "Useful for identifying urgent payment reminders needed."
            ),
            args_schema=PaymentQueryInput,
        ),
        Tool(

            name="Create_Payment_Reminder_Schedules",
            func=lambda query="": _create_payment_reminder_schedules_runner(query),
            description=(
                "Create automatic reminder schedules for a payment. Creates multiple schedules to send reminders before the due date. "
                "Input format: JSON string with 'payment_id' (int) and optional 'days_before' (list of days, default [7, 3, 1]). "
                "Example: '{\"payment_id\": 1, \"days_before\": [7, 3, 1]}'"
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


# Notification tool runners
def _send_notification_runner(request_str: str) -> str:
    """Send a notification."""
    try:
        import json
        from .notifications_service import notification_service
        
        if isinstance(request_str, dict):
            request = request_str
        else:
            request = json.loads(request_str)
        
        recipient_id = request.get('recipient_id')
        notification_type = request.get('notification_type', 'custom')
        context = request.get('context', {})
        template = request.get('template')
        payment_link = request.get('payment_link')
        
        if not recipient_id:
            return "Error: recipient_id is required"
        
        result = notification_service.send_direct_notification(
            recipient_id=recipient_id,
            notification_type=notification_type,
            context=context,
            template=template,
            payment_link=payment_link
        )
        
        if result.get('success'):
            return f"✅ Notification sent successfully to {result.get('recipient')}. Subject: {result.get('subject')}"
        else:
            return f"❌ Failed to send notification: {result.get('error', 'Unknown error')}"
    except Exception as e:
        logger.error(f"Error in Send_Notification tool: {e}")
        return f"Error sending notification: {str(e)}"


def _list_recipients_runner(user_id: int):
    """List notification recipients."""
    def _run(query: str = "") -> str:
        try:
            from .notifications_db import list_recipients
            
            # Handle None or empty query
            if not query:
                query = ""
            
            if isinstance(query, dict):
                recipient_type = query.get('type') or query.get('__arg1', '')
            else:
                recipient_type = str(query).strip() if query else None
            
            if recipient_type and recipient_type.lower() in ['vendor', 'worker', 'client']:
                recipients = list_recipients(user_id=user_id, recipient_type=recipient_type.lower())
            else:
                recipients = list_recipients(user_id=user_id)
            
            if not recipients:
                return "No recipients found. Add recipients in the Notifications section."
            
            result_lines = []
            for rec in recipients:
                result_lines.append(f"\nID: {rec['id']} - {rec['name']} ({rec['type']})")
                result_lines.append(f"  Email: {rec['email']}")
                if rec.get('company'):
                    result_lines.append(f"  Company: {rec['company']}")
                if rec.get('phone'):
                    result_lines.append(f"  Phone: {rec['phone']}")
            
            return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in List_Notification_Recipients tool: {e}")
            return f"Error listing recipients: {str(e)}"
    return _run


def _list_schedules_runner(user_id: int):
    """List notification schedules."""
    def _run(query: str = "") -> str:
        try:
            from .notifications_db import list_schedules, get_recipient
            
            # Handle None or empty query (not used but required by Tool signature)
            query = query or ""
            
            schedules = list_schedules(user_id=user_id)
            
            if not schedules:
                return "No notification schedules found. Create schedules in the Notifications section."
            
            result_lines = []
            for sched in schedules:
                recipient = get_recipient(sched['recipient_id'], user_id=user_id)
                recipient_name = recipient['name'] if recipient else f"ID {sched['recipient_id']}"
                status = "✅ Enabled" if sched.get('enabled') else "❌ Disabled"
                result_lines.append(f"\nSchedule ID: {sched['id']} - {sched['name']} ({status})")
                result_lines.append(f"  Recipient: {recipient_name} ({recipient['type'] if recipient else 'unknown'})")
                result_lines.append(f"  Type: {sched['notification_type']}")
                result_lines.append(f"  Interval: Every {sched.get('interval_days', 7)} days")
                if sched.get('next_send_at'):
                    result_lines.append(f"  Next send: {sched['next_send_at']}")
            
            return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in List_Notification_Schedules tool: {e}")
            return f"Error listing schedules: {str(e)}"
    return _run


def _get_notification_history_runner(user_id: int):
    """Get notification history."""
    def _run(query: str = "") -> str:
        try:
            from .notifications_db import get_notification_history, get_recipient
            
            # Handle None or empty query
            if not query:
                query = ""
            
            recipient_id = None
            if isinstance(query, dict):
                recipient_id = query.get('recipient_id') or query.get('__arg1')
            elif query:
                try:
                    recipient_id = int(query)
                except:
                    pass
            
            history = get_notification_history(user_id=user_id, limit=20, recipient_id=recipient_id)
            
            if not history:
                return "No notification history found."
            
            result_lines = []
            for entry in history[:10]:  # Show last 10
                recipient = get_recipient(entry['recipient_id'], user_id=user_id)
                recipient_name = recipient['name'] if recipient else f"ID {entry['recipient_id']}"
                status_icon = "✅" if entry['status'] == 'sent' else "❌"
                result_lines.append(f"\n{status_icon} {entry['sent_at']} - {recipient_name}")
                result_lines.append(f"  Subject: {entry['subject']}")
                result_lines.append(f"  Type: {entry['notification_type']}")
                if entry.get('error_message'):
                    result_lines.append(f"  Error: {entry['error_message']}")
            
            return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in Get_Notification_History tool: {e}")
            return f"Error getting notification history: {str(e)}"
    return _run


# Payment tool runners
def _list_payments_runner(user_id: int):
    """List payments."""
    def _run(query: str = "") -> str:
        try:
            import json
            from .notifications_db import list_payments
            
            # Handle None or empty query
            if not query:
                query = ""
            
            payment_type = None
            entity_type = None
            status = None
            
            if isinstance(query, dict):
                payment_type = query.get('payment_type')
                entity_type = query.get('entity_type')
                status = query.get('status')
            elif query:
                try:
                    params = json.loads(query)
                    payment_type = params.get('payment_type')
                    entity_type = params.get('entity_type')
                    status = params.get('status')
                except:
                    pass
            
            payments = list_payments(
                user_id=user_id,
                payment_type=payment_type,
                entity_type=entity_type,
                status=status,
                limit=50
            )
            
            if not payments:
                return "No payments found matching criteria."
            
            result_lines = [f"\n💰 Payments ({len(payments)} total):"]
            for p in payments[:20]:  # Show first 20
                entity_type = p['entity_type']
                entity_id = p['entity_id']
                
                # Get entity name
                entity_name = f"{entity_type} {entity_id}"
                
                payment_dir = "📥 Receive" if p['payment_type'] == 'receive' else "📤 Send"
                result_lines.append(f"\n  {payment_dir} - ID: {p['id']}")
                result_lines.append(f"    Amount: ${p.get('amount', 0):,.2f}")
                result_lines.append(f"    To/From: {entity_name} ({entity_type})")
                result_lines.append(f"    Due Date: {p.get('due_date', 'N/A')}")
                result_lines.append(f"    Status: {p.get('status', 'N/A')}")
                if p.get('project_name'):
                    result_lines.append(f"    Project: {p['project_name']}")
                if p.get('invoice_number'):
                    result_lines.append(f"    Invoice: {p['invoice_number']}")
            
            return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in List_Payments tool: {e}")
            return f"Error listing payments: {str(e)}"
    return _run


def _get_payments_due_soon_runner(user_id: int):
    """Get payments due soon."""
    def _run(query: str = "") -> str:
        try:
            from .notifications_db import get_payments_due_soon
            
            # Handle None or empty query
            if not query:
                query = ""
            
            days = 7
            if isinstance(query, dict):
                days = int(query.get('days', query.get('__arg1', 7)))
            elif query:
                try:
                    days = int(query)
                except:
                    pass
            
            payments = get_payments_due_soon(user_id=user_id, days=days)
        
            if not payments:
                return f"No payments due within {days} days."
            
            result_lines = [f"\n⏰ Payments Due Soon (within {days} days):"]
            for p in payments:
                entity_type = p['entity_type']
                entity_id = p['entity_id']
                
                # Get entity name
                entity_name = f"{entity_type} {entity_id}"
                payment_dir = "📥 Receive from" if p['payment_type'] == 'receive' else "📤 Pay to"
                result_lines.append(f"\n  {payment_dir} {entity_name}")
                result_lines.append(f"    Amount: ${p.get('amount', 0):,.2f}")
                result_lines.append(f"    Due Date: {p.get('due_date', 'N/A')}")
                result_lines.append(f"    Invoice: {p.get('invoice_number', 'N/A')}")
            
                return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in Get_Payments_Due_Soon tool: {e}")
            return f"Error getting payments due soon: {str(e)}"
    return _run


def _get_overdue_payments_runner(user_id: int):
    """Get overdue payments."""
    def _run(query: str = "") -> str:
        try:
            from .notifications_db import get_overdue_payments
            
            # Handle None or empty query (not used but required by Tool signature)
            query = query or ""
            
            payments = get_overdue_payments(user_id=user_id)
            
            if not payments:
                return "No overdue payments found."
            
            result_lines = [f"\n🚨 Overdue Payments ({len(payments)} total):"]
            for p in payments:
                entity_type = p['entity_type']
                entity_id = p['entity_id']
                
                # Get entity name
                entity_name = f"{entity_type} {entity_id}"
                payment_dir = "📥 Receive from" if p['payment_type'] == 'receive' else "📤 Pay to"
                result_lines.append(f"\n  {payment_dir} {entity_name}")
                result_lines.append(f"    Amount: ${p.get('amount', 0):,.2f}")
                result_lines.append(f"    Due Date: {p.get('due_date', 'N/A')} (OVERDUE)")
                result_lines.append(f"    Invoice: {p.get('invoice_number', 'N/A')}")
            
            return "\n".join(result_lines)
        except Exception as e:
            logger.error(f"Error in Get_Overdue_Payments tool: {e}")
            return f"Error getting overdue payments: {str(e)}"
    return _run


def _create_payment_reminder_schedules_runner(query: str = "") -> str:
    """Create payment reminder schedules."""
    try:
        import json
        from .notifications_service import notification_service
        
        if isinstance(query, dict):
            payment_id = query.get('payment_id') or query.get('__arg1')
            days_before = query.get('days_before', [7, 3, 1])
        else:
            try:
                params = json.loads(query)
                payment_id = params.get('payment_id')
                days_before = params.get('days_before', [7, 3, 1])
            except:
                return "Error: Invalid input format. Expected JSON with 'payment_id' and optional 'days_before'."
        
        if not payment_id:
            return "Error: payment_id is required"
        
        schedule_ids = notification_service.create_payment_based_schedules(
            payment_id=int(payment_id),
            days_before=days_before if isinstance(days_before, list) else [7, 3, 1]
        )
        
        if schedule_ids:
            return f"✅ Created {len(schedule_ids)} reminder schedule(s) for payment {payment_id}: {schedule_ids}"
        else:
            return f"❌ Failed to create schedules for payment {payment_id}"
    except Exception as e:
        logger.error(f"Error in Create_Payment_Reminder_Schedules tool: {e}")
        return f"Error creating payment reminder schedules: {str(e)}"
