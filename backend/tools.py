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
            # Try to infer which table to use based on the query
            # Look for column names or keywords that might indicate which table
            question_lower = question.lower()
            inferred_table = None
            
            # Check each table's columns to see if they match the query
            for table_info in tables:
                table_name_check = table_info["name"].lower()
                # Use "column_names" which is a list, not "columns" which is an integer count
                column_names = table_info.get("column_names", [])
                columns = [col.lower() for col in column_names] if column_names else []
                
                # Check if query mentions table name or key columns
                if (table_name_check in question_lower or 
                    any(col in question_lower for col in columns if col and len(col) > 3)):
                    inferred_table = table_info["name"]
                    logger.info(f"🎯 Inferred table '{inferred_table}' based on query")
                    break
            
            if inferred_table:
                df = data_registry.get("spreadsheet", inferred_table)
                if df is not None and not df.empty:
                    logger.info(f"✅ Using inferred table '{inferred_table}' with {len(df)} rows, {len(df.columns)} columns")
                    agent = _build_pandas_agent(llm, df)
                else:
                    # Fallback: use first table if inference failed
                    if tables:
                        first_table = tables[0]["name"]
                        df = data_registry.get("spreadsheet", first_table)
                        logger.info(f"⚠️  Inference failed, using first available table '{first_table}'")
                        agent = _build_pandas_agent(llm, df)
                    else:
                        return "No spreadsheet data available."
            else:
                # No inference possible, use first table (don't combine all tables)
                if tables:
                    first_table = tables[0]["name"]
                    df = data_registry.get("spreadsheet", first_table)
                    logger.info(f"⚠️  No table inferred, using first available table '{first_table}'. "
                              f"For multi-table queries, use Multi_Table_Analysis_Tool or specify table name.")
                    agent = _build_pandas_agent(llm, df)
                else:
                    return "No spreadsheet data available."

        
        # Execute query - let the agent decide how to search based on the question
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
                "MANDATORY FOR CSV/EXCEL QUERIES: Use to query ANY uploaded spreadsheet table (CSV or Excel) using natural language. "
                "ALWAYS call List_Available_Tables FIRST to see what tables and columns exist. "
                "CRITICAL: If multiple CSV/Excel files exist, you MUST search MULTIPLE tables, not just one. "
                "This tool automatically understands table structures, finds relevant columns, and can perform filtering (>, <, >=, <=, =, !=, contains, in/not in), "
                "grouping, aggregations (sum, avg, count, min, max), and basic analysis. "
                "You can specify a table name with 'table=<name>::question=<query>' or just ask a question and the tool will infer the right table(s) and columns. "
                "IMPORTANT: When multiple tables exist, call this tool MULTIPLE times - once for each relevant table. "
                "For example, if you have 'workers.csv' and 'payments.csv', search BOTH when asked about worker payments. "
                "This is the PRIMARY tool for structured data queries. "
                "USE THIS PROACTIVELY for questions about timelines, schedules, durations, costs, budgets, quantities, resources, etc. "
                "If a question involves numbers, dates, or calculations, search spreadsheets automatically across ALL relevant tables. "
                "ALWAYS use this tool when CSV/Excel data exists - don't skip spreadsheet searches. "
                "After searching one table, check if other tables might have relevant information and search those too. "
                "Use together with Multi_Table_Analysis_Tool for cross-table queries, and with ERP tools and document retrievers for comprehensive answers."
            ),
        ),
        Tool(
            name="Multi_Table_Analysis_Tool",
            func=_multi_table_analysis_runner(llm),
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
        StructuredTool.from_function(
            func=_list_tables_runner,
            name="List_Available_Tables",
            description=(
                "MANDATORY FIRST STEP: Use this to see what CSV/Excel tables are available, their column names, row counts, and structure information. "
                "ALWAYS call this FIRST before querying spreadsheets to understand what data is available. "
                "This shows you what columns exist so you can formulate better queries. "
                "You can call this tool with an empty string or any query - it will list all tables regardless. "
                "After seeing available tables, use Generic_Spreadsheet_Query_Tool to query the data."
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
        Tool(
            name="List_Notification_Recipients",
            func=lambda query="": _list_recipients_runner(query),
            description=(
                "List all notification recipients (vendors, workers, clients). "
                "Use this to find recipient IDs when you need to send notifications. "
                "Optional query parameter to filter by type: 'vendor', 'worker', or 'client'."
            ),
        ),
        Tool(
            name="List_Notification_Schedules",
            func=lambda query="": _list_schedules_runner(query),
            description=(
                "List all notification schedules. Use this to see what automated notifications are configured. "
                "Shows schedules with their recipients, types, intervals, and status."
            ),
        ),
        Tool(

            name="Get_Notification_History",
            func=lambda query="": _get_notification_history_runner(query),
            description=(
                "Get notification history/logs. Use this to check what notifications have been sent recently. "
                "Optional query can specify recipient_id as a number to filter by recipient."
            ),
        ),
        
        # Payment Tools
        Tool(
            name="List_Payments",
            func=lambda query="": _list_payments_runner(query),
            description=(
                "MANDATORY FOR PAYMENT QUESTIONS: List all payments in the ERP system. Shows payment type (receive/send), amounts, due dates, status, and related entities. "
                "ALWAYS call this when questions involve payments, invoices, or financial transactions. "
                "Also search CSV/Excel tables and documents for comprehensive payment information. "
                "Optional query can filter by payment_type ('receive' or 'send'), entity_type ('client', 'vendor', 'worker'), or status ('pending', 'paid', 'overdue'). "
                "Example: '{\"payment_type\": \"receive\", \"status\": \"pending\"}' "
                "Use this tool together with Generic_Spreadsheet_Query_Tool and document retrievers for complete answers."
            ),
        ),
        Tool(

            name="Get_Payments_Due_Soon",
            func=lambda query="": _get_payments_due_soon_runner(query),
            description=(

                "Get payments that are due soon. Shows payments due within specified days (default 7). "
                "Useful for identifying which payments need reminders sent. "
                "Optional query can specify days as a number (e.g., '14' for 14 days)."
            ),
        ),
        Tool(

            name="Get_Overdue_Payments",
            func=lambda query="": _get_overdue_payments_runner(query),
            description=(

                "Get all overdue payments. Shows payments that are past their due date and still pending. "
                "Useful for identifying urgent payment reminders needed."
            ),
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


def _list_recipients_runner(query: str = "") -> str:
    """List notification recipients."""
    try:
        from .notifications_db import list_recipients
        
        if isinstance(query, dict):
            recipient_type = query.get('type') or query.get('__arg1', '')
        else:
            recipient_type = str(query).strip() if query else None
        
        if recipient_type and recipient_type.lower() in ['vendor', 'worker', 'client']:
            recipients = list_recipients(recipient_type=recipient_type.lower())
        else:
            recipients = list_recipients()
        
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


def _list_schedules_runner(query: str = "") -> str:
    """List notification schedules."""
    try:
        from .notifications_db import list_schedules, get_recipient
        
        schedules = list_schedules()
        
        if not schedules:
            return "No notification schedules found. Create schedules in the Notifications section."
        
        result_lines = []
        for sched in schedules:
            recipient = get_recipient(sched['recipient_id'])
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


def _get_notification_history_runner(query: str = "") -> str:
    """Get notification history."""
    try:
        from .notifications_db import get_notification_history, get_recipient
        
        recipient_id = None
        if isinstance(query, dict):
            recipient_id = query.get('recipient_id') or query.get('__arg1')
        elif query:
            try:
                recipient_id = int(query)
            except:
                pass
        
        history = get_notification_history(limit=20, recipient_id=recipient_id)
        
        if not history:
            return "No notification history found."
        
        result_lines = []
        for entry in history[:10]:  # Show last 10
            recipient = get_recipient(entry['recipient_id'])
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


# Payment tool runners
def _list_payments_runner(query: str = "") -> str:
    """List payments."""
    try:
        import json
        from .notifications_db import list_payments
        
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


def _get_payments_due_soon_runner(query: str = "") -> str:
    """Get payments due soon."""
    try:
        from .notifications_db import get_payments_due_soon
        
        days = 7
        if isinstance(query, dict):
            days = int(query.get('days', query.get('__arg1', 7)))
        elif query:
            try:
                days = int(query)
            except:
                pass
        
        payments = get_payments_due_soon(days=days)
        
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


def _get_overdue_payments_runner(query: str = "") -> str:
    """Get overdue payments."""
    try:
        from .notifications_db import get_overdue_payments
        
        payments = get_overdue_payments()
        
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
