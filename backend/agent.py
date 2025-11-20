"""LangChain v1 agent wiring with autonomous decision-making capabilities."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_core.messages import ToolMessage

# Load .env file before creating any OpenAI clients
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

from .tools import build_tools, data_registry
from .vectorstore import vector_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AgentAnalysisCallback(BaseCallbackHandler):
    """Callback handler to log detailed agent analysis and tool usage."""
    
    def __init__(self):
        super().__init__()
        self.step_count = 0
        self.tool_calls = []
        
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> None:
        """Called when LLM starts running."""
        try:
            self.step_count += 1
            logger.info("=" * 80)
            logger.info(f"🤖 AGENT STEP {self.step_count} - LLM THINKING")
            logger.info("=" * 80)
            if prompts and len(prompts) > 0:
                prompt_text = str(prompts[0]) if prompts[0] else ""
                logger.info(f"📝 Prompt: {prompt_text[:200]}..." if len(prompt_text) > 200 else f"📝 Prompt: {prompt_text}")
        except Exception as e:
            logger.debug(f"Error in on_llm_start: {e}")
            self.step_count += 1
            logger.info("=" * 80)
            logger.info(f"🤖 AGENT STEP {self.step_count} - LLM THINKING")
            logger.info("=" * 80)
    
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Called when LLM ends running."""
        try:
            if response and hasattr(response, 'generations') and response.generations:
                for gen_list in response.generations:
                    if gen_list:
                        for gen in gen_list:
                            if hasattr(gen, 'text'):
                                text = str(gen.text) if gen.text else ""
                                logger.info(f"💭 LLM Response: {text[:300]}..." if len(text) > 300 else f"💭 LLM Response: {text}")
                            elif hasattr(gen, 'message'):
                                try:
                                    content = str(gen.message.content) if hasattr(gen.message, 'content') else str(gen.message)
                                    logger.info(f"💭 LLM Response: {content[:300]}..." if len(content) > 300 else f"💭 LLM Response: {content}")
                                except Exception:
                                    logger.info(f"💭 LLM Response: [Message object]")
        except Exception as e:
            logger.debug(f"Error in on_llm_end: {e}")
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> None:
        """Called when a tool starts running."""
        try:
            if serialized is None:
                tool_name = "Unknown Tool"
            elif isinstance(serialized, dict):
                tool_name = serialized.get("name", "Unknown Tool")
            else:
                tool_name = str(serialized) if serialized else "Unknown Tool"
            
            logger.info("-" * 80)
            logger.info(f"🔧 TOOL CALL: {tool_name}")
            logger.info(f"📥 Input: {input_str[:500]}..." if len(input_str) > 500 else f"📥 Input: {input_str}")
            self.tool_calls.append({
                "tool": tool_name,
                "input": input_str,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            logger.debug(f"Error in on_tool_start: {e}")
            logger.info("-" * 80)
            logger.info(f"🔧 TOOL CALL: Unknown Tool")
            logger.info(f"📥 Input: {str(input_str)[:500]}...")
    
    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        """Called when a tool ends running."""
        try:
            # Handle different output types
            if isinstance(output, ToolMessage):
                output_str = str(output.content) if hasattr(output, 'content') else str(output)
            elif hasattr(output, 'content'):
                output_str = str(output.content)
            elif isinstance(output, str):
                output_str = output
            else:
                output_str = str(output) if output is not None else ""
            
            # Log output (safely handle length)
            output_len = len(output_str) if output_str else 0
            if output_len > 500:
                logger.info(f"📤 Output: {output_str[:500]}...")
            else:
                logger.info(f"📤 Output: {output_str}")
            
            if self.tool_calls:
                self.tool_calls[-1]["output"] = output_str
            logger.info("-" * 80)
        except Exception as e:
            logger.debug(f"Error in on_tool_end: {e}")
            try:
                # Fallback: just convert to string
                output_str = str(output) if output is not None else ""
                logger.info(f"📤 Output: {output_str[:500]}...")
                if self.tool_calls:
                    self.tool_calls[-1]["output"] = output_str
            except:
                pass
            logger.info("-" * 80)
    
    def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        """Called when a tool encounters an error."""
        logger.error(f"❌ TOOL ERROR: {str(error)}")
        logger.error("-" * 80)
    
    def on_chain_start(self, serialized: Any, inputs: Any, **kwargs: Any) -> None:
        """Called when a chain starts running."""
        try:
            # Try to extract chain name from kwargs first (more reliable)
            chain_name = kwargs.get("name") or kwargs.get("chain_name")
            
            # Handle None or missing serialized
            if chain_name is None:
                if serialized is None:
                    chain_name = "Agent Chain"
                # Handle dict type
                elif isinstance(serialized, dict):
                    chain_name = serialized.get("name") or serialized.get("id")
                    if chain_name is None:
                        # Try to get from nested structure
                        chain_name = serialized.get("lc_id") or serialized.get("type")
                    if chain_name is None:
                        chain_name = "Agent Chain"
                    elif isinstance(chain_name, list) and len(chain_name) > 0:
                        chain_name = chain_name[-1]
                    elif not isinstance(chain_name, str):
                        chain_name = str(chain_name)
                # Handle other types
                else:
                    try:
                        chain_name = str(serialized) if serialized else "Agent Chain"
                    except:
                        chain_name = "Agent Chain"
            
            # Clean up chain name
            if chain_name and isinstance(chain_name, str):
                # Remove common prefixes/suffixes
                chain_name = chain_name.replace("langchain.", "").replace("chains.", "")
                if len(chain_name) > 50:
                    chain_name = chain_name[:47] + "..."
            
            logger.info(f"🔗 CHAIN START: {chain_name}")
        except Exception:
            # Silently handle errors - don't log debug to avoid spam
            logger.info(f"🔗 CHAIN START: Agent Chain")
    
    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        """Called when a chain ends running."""
        try:
            logger.info(f"✅ CHAIN COMPLETE")
        except Exception as e:
            logger.debug(f"Error in on_chain_end: {e}")
    
    def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        """Called when a chain encounters an error."""
        try:
            logger.error(f"❌ CHAIN ERROR: {str(error)}")
        except Exception as e:
            logger.debug(f"Error in on_chain_error: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the agent's analysis."""
        return {
            "total_steps": self.step_count,
            "tool_calls": self.tool_calls,
        }


class AgentOrchestrator:
    """
    Configures and runs the LangChain v1 agent with session-aware memory and autonomous decision-making.
    
    The agent autonomously decides whether to:
    - Search structured data (CSV/Excel tables)
    - Search unstructured documents (PDF, DOCX, PPTX, images)
    - Combine both sources
    - Perform multi-step reasoning across multiple tables
    
    Based on: https://docs.langchain.com/oss/python/langchain/agents
    """

    def __init__(self) -> None:
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.0)
        self.tools = build_tools(self.llm, vector_manager)
        
        # Log available tools
        logger.info("=" * 80)
        logger.info("🛠️  AVAILABLE TOOLS")
        logger.info("=" * 80)
        for i, tool in enumerate(self.tools, 1):
            logger.info(f"{i}. {tool.name}")
            logger.info(f"   Description: {tool.description[:100]}...")
        logger.info("=" * 80)
        
        # LangChain v1: create_agent(model, tools=tools)
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
        )
        
        # Store conversation history per session
        self._conversations: Dict[str, List] = {}
        
        # Enhanced system message with autonomous decision-making guidance
        self.system_message = (
            "You are ConstructionBot, an intelligent construction compliance and planning analyst "
            "with autonomous decision-making capabilities.\n\n"
            
            "CRITICAL: COMPREHENSIVE MULTI-SOURCE SEARCH - SEARCH ALL DATA SOURCES BEFORE RESPONDING\n"
            "MANDATORY RULE: For ANY question, you MUST search ALL relevant data sources BEFORE responding:\n"
            "1. CSV/Excel spreadsheets (structured data)\n"
            "2. ERP system data (workers, clients, vendors, payments)\n"
            "3. Documents (PDFs, DOCX, PPTX, images)\n"
            "Your immediate knowledge does NOT include project-specific information - you MUST search for it.\n\n"
            
            "MANDATORY SEARCH SEQUENCE FOR EVERY QUESTION - FOLLOW THIS EXACT ORDER:\n"
            "STEP 1: ALWAYS check CSV/Excel data FIRST (MANDATORY - DO NOT SKIP THIS STEP)\n"
            "   → ALWAYS call List_Available_Tables FIRST - this is REQUIRED for every question\n"
            "   → Review the table structures to understand available columns\n"
            "   → If tables exist, you MUST call Generic_Spreadsheet_Query_Tool with the question\n"
            "   → The tool will automatically find relevant columns and filter data\n"
            "   → For complex queries, use Multi_Table_Analysis_Tool\n"
            "   → CRITICAL: Even if you search ERP data, you MUST still search CSV/Excel\n"
            "   → CSV/Excel files may contain information not in ERP system\n"
            "   → For questions about people (workers, clients, vendors), search CSV/Excel for names\n\n"
            "STEP 2: Search ERP system data (ALWAYS check if relevant)\n"
            "   → For questions about workers → Call List_Workers\n"
            "   → For questions about clients → Call List_Clients\n"
            "   → For questions about vendors → Call List_Vendors\n"
            "   → For questions about payments → Call List_Payments\n"
            "   → For payment due dates → Call Get_Payments_Due_Soon or Get_Overdue_Payments\n"
            "   → Use filters in queries when appropriate (e.g., status, payment_type)\n"
            "   → CRITICAL: Searching ERP does NOT replace CSV/Excel search - do BOTH\n\n"
            "STEP 3: Search documents\n"
            "   → Call General_Document_Retriever with the question\n"
            "   → Call PDF_Document_Retriever with related search terms\n"
            "   → Call DOCX_Document_Retriever if needed\n"
            "   → Try multiple search term variations\n\n"
            "STEP 4: Synthesize and respond\n"
            "   → Combine information from ALL sources searched\n"
            "   → Use Answer_Synthesizer if combining structured and unstructured data\n"
            "   → Cite all sources (table names, column names, ERP entities, document filenames)\n\n"
            "CRITICAL RULE: You MUST call List_Available_Tables and Generic_Spreadsheet_Query_Tool for EVERY question, "
            "even if you also search ERP data. CSV/Excel files may contain information not in ERP system. "
            "For questions about people (names like 'Subash', 'John', etc.), you MUST search CSV/Excel files.\n\n"
            
            "NEVER say phrases like:\n"
            "- 'I was unable to find...'\n"
            "- 'I cannot find specific information...'\n"
            "- 'It seems that the necessary data is not currently uploaded...'\n"
            "UNLESS you have:\n"
            "1. Called List_Available_Tables to check CSV/Excel data\n"
            "2. Searched spreadsheets with Generic_Spreadsheet_Query_Tool\n"
            "3. Searched relevant ERP data (List_Workers, List_Clients, List_Vendors, List_Payments)\n"
            "4. Searched documents with General_Document_Retriever and PDF_Document_Retriever\n"
            "5. Tried multiple search term variations\n\n"
            
            "SEARCH TRIGGERS - Automatically search ALL relevant sources:\n"
            "- Project timelines, durations, completion dates, schedules → Search CSV/Excel AND ERP payments AND documents\n"
            "- Costs, budgets, financials → Search CSV/Excel AND ERP payments AND documents\n"
            "- Workers, employees, staff → Search CSV/Excel AND List_Workers AND documents\n"
            "- Clients, customers → Search CSV/Excel AND List_Clients AND documents\n"
            "- Vendors, suppliers → Search CSV/Excel AND List_Vendors AND documents\n"
            "- Payments, invoices, due dates → Search CSV/Excel AND List_Payments AND Get_Payments_Due_Soon AND documents\n"
            "- Quantities, materials, resources → Search CSV/Excel AND documents\n"
            "- Compliance, regulations, requirements → Search documents AND CSV/Excel\n"
            "- Contract terms, specifications, details → Search documents AND CSV/Excel\n"
            "- Any 'how long', 'how much', 'what is', 'when', 'where', 'who' questions → SEARCH ALL SOURCES\n\n"
            
            "CSV/EXCEL SEARCH STRATEGY:\n"
            "1. ALWAYS start with List_Available_Tables to see:\n"
            "   → What tables exist\n"
            "   → What columns are in each table\n"
            "   → Column data types and sample values\n"
            "   → This helps you understand what data is available\n\n"
            "2. When querying spreadsheets:\n"
            "   → Use Generic_Spreadsheet_Query_Tool with natural language questions\n"
            "   → The tool will automatically find relevant columns and filter\n"
            "   → For example: 'Show all payments over $5000' will find amount columns and filter\n"
            "   → For example: 'List workers with hourly rate above $25' will find rate columns\n"
            "   → The tool handles column name inference automatically\n\n"
            "3. For complex multi-table queries:\n"
            "   → Use Multi_Table_Analysis_Tool\n"
            "   → Specify tables and operations clearly\n\n"
            
            "ERP SEARCH STRATEGY:\n"
            "1. For ANY question involving people or entities:\n"
            "   → Check List_Workers, List_Clients, List_Vendors,Generic_Spreadsheet_Query_Tool\n"
            "   → Use query filters when appropriate (e.g., 'active' status)\n\n"
            "2. For ANY question involving payments or financials:\n"
            "   → Check List_Payments (use filters: payment_type, status, entity_type)\n"
            "   → Check Get_Payments_Due_Soon for upcoming payments\n"
            "   → Check Get_Overdue_Payments for overdue items\n\n"
            "3. Combine ERP data with spreadsheet data:\n"
            "   → ERP might have payment records\n"
            "   → Spreadsheets might have detailed transaction data\n"
            "   → Search BOTH and combine results\n\n"
            
            "DOCUMENT SEARCH STRATEGY:\n"
            "1. For ambiguous questions:\n"
            "   → Search BOTH General_Document_Retriever AND specific retrievers\n"
            "   → Try multiple search terms (e.g., 'project timeline', 'completion date', 'duration', 'schedule')\n"
            "   → Don't give up after one search - try different queries\n\n"
            "2. If first search doesn't find relevant info:\n"
            "   → Try broader search terms\n"
            "   → Search different document types (PDF, DOCX, PPTX)\n"
            "   → Only say 'cannot find' after exhaustive searching\n\n"
            
            "ABSOLUTE PROHIBITION:\n"
            "NEVER respond with phrases like:\n"
            "- 'I was unable to find...'\n"
            "- 'I cannot find specific information...'\n"
            "- 'It seems that the necessary data is not currently uploaded...'\n"
            "- 'If you have any specific documents...'\n"
            "UNLESS you have:\n"
            "1. Searched General_Document_Retriever with multiple query variations\n"
            "2. Searched PDF_Document_Retriever\n"
            "3. Checked List_Available_Tables and searched spreadsheets\n"
            "4. Tried different search terms related to the question\n\n"
            
            "DECISION-MAKING PROCESS:\n"
            "For every user query, you must autonomously decide the best approach:\n"
            "1. ANALYZE the query to determine what type of information is needed:\n"
            "   - Structured data queries (numbers, calculations, aggregations, filtering, timelines, schedules) → Use spreadsheet tools\n"
            "   - Unstructured content (regulations, clauses, descriptions, text search, contract terms, project details) → Use document retrieval tools\n"
            "   - Ambiguous queries (e.g., 'how long will it take?', 'what's the budget?') → Search BOTH documents AND spreadsheets\n"
            "   - Combined queries (e.g., 'What does the contract say about X and how much do we have?') → Use BOTH\n\n"
            
            "2. STEP-BY-STEP REASONING - BE PROACTIVE (MANDATORY PROCESS):\n"
            "   - First, understand what the user is asking\n"
            "   - ASSUME you don't have project-specific information - you MUST search ALL sources\n"
            "   - For EVERY question, execute this COMPREHENSIVE search sequence:\n"
            "     STEP 1: Call List_Available_Tables to see what CSV/Excel data exists and what columns are available\n"
            "     STEP 2: If CSV/Excel tables exist, call Generic_Spreadsheet_Query_Tool with the question\n"
            "            (The tool will automatically find relevant columns and filter data)\n"
            "     STEP 3: Check if question involves workers/clients/vendors/payments → Call relevant ERP tools:\n"
            "            - List_Workers (with filters if needed)\n"
            "            - List_Clients (with filters if needed)\n"
            "            - List_Vendors (with filters if needed)\n"
            "            - List_Payments (with filters: payment_type, status, entity_type)\n"
            "            - Get_Payments_Due_Soon or Get_Overdue_Payments if relevant\n"
            "     STEP 4: Call General_Document_Retriever with the question or key terms\n"
            "     STEP 5: Call PDF_Document_Retriever with related search terms\n"
            "     STEP 6: If still no results, try broader search terms and different tools\n"
            "     STEP 7: Synthesize information from ALL sources and provide comprehensive answer\n"
            "   - Questions about timelines, schedules, durations → ALWAYS search CSV/Excel AND ERP payments AND documents\n"
            "   - Questions about costs, budgets, quantities → ALWAYS search CSV/Excel AND ERP payments AND documents\n"
            "   - Questions about workers/employees → ALWAYS search CSV/Excel AND List_Workers AND documents\n"
            "   - Questions about clients → ALWAYS search CSV/Excel AND List_Clients AND documents\n"
            "   - Questions about vendors → ALWAYS search CSV/Excel AND List_Vendors AND documents\n"
            "   - Questions about payments → ALWAYS search CSV/Excel AND List_Payments AND documents\n"
            "   - Questions about compliance, regulations, requirements → ALWAYS search documents AND CSV/Excel\n"
            "   - Questions about project details, specifications → ALWAYS search documents AND CSV/Excel\n"
            "   - NEVER say 'I need to analyze...' or 'I cannot find...' without having called:\n"
            "     * List_Available_Tables\n"
            "     * Generic_Spreadsheet_Query_Tool (if tables exist)\n"
            "     * Relevant ERP tools (List_Workers, List_Clients, List_Vendors, List_Payments)\n"
            "     * General_Document_Retriever\n"
            "     * PDF_Document_Retriever\n\n"
            
            "3. SPREADSHEET OPERATIONS (MANDATORY - check CSV/Excel for every question):\n"
            "   - ALWAYS call List_Available_Tables FIRST to see:\n"
            "     * What tables exist\n"
            "     * What columns are available in each table\n"
            "     * Column data types and sample values\n"
            "   - Use 'Generic_Spreadsheet_Query_Tool' for queries - it automatically:\n"
            "     * Finds relevant columns based on your question\n"
            "     * Filters data using appropriate operators (>, <, >=, <=, =, !=, contains, in/not in)\n"
            "     * Handles column name inference - you don't need to know exact column names\n"
            "   - For person/name questions:\n"
            "     * When asked about a person, identify which column contains names (e.g., 'Name', 'Worker_Name', 'Client_Name')\n"
            "     * Use pandas filtering to search that column: df[df['ColumnName'].str.contains('name', case=False, na=False)]\n"
            "     * The agent will automatically determine the correct column based on the table structure\n"
            "   - Use 'Multi_Table_Analysis_Tool' for joins, cross-table analysis, aggregations\n"
            "   - Support all operations: filtering, grouping, aggregations (sum, avg, count, min, max), joins\n"
            "   - The tools automatically find relevant columns - you just ask natural language questions\n"
            "   - For example: 'Show payments over $5000' → tool finds amount column and filters\n"
            "   - For example: 'List workers earning more than $25/hour' → tool finds rate column and filters\n"
            "   - For example: 'Who is Subash?' → tool searches Name column for 'Subash'\n"
            "   - Reason through multiple steps for complex queries\n"
            "   - For timeline/schedule questions, search for date columns, duration columns, milestone columns\n\n"
            
            "4. DOCUMENT OPERATIONS (when needed):\n"
            "   - Use specific retrievers (PDF_Document_Retriever, DOCX_Document_Retriever, PPTX_Document_Retriever) when you know the source type\n"
            "   - Use 'General_Document_Retriever' when unsure or when searching broadly\n"
            "   - For questions about contracts, timelines, project details → Search PDFs and DOCX files\n"
            "   - Always cite filenames and page/row numbers\n"
            "   - If initial search doesn't find relevant info, try different search terms or broader searches\n\n"
            
            "5. SYNTHESIS:\n"
            "   - When combining structured and unstructured data, use 'Answer_Synthesizer' tool\n"
            "   - Provide comprehensive answers with proper citations\n"
            "   - Explain your reasoning when combining multiple data sources\n\n"
            
            "EXAMPLES OF COMPREHENSIVE MULTI-SOURCE SEARCH:\n"
            "- User: 'How long will it take to complete the project?'\n"
            "  → STEP 1: Call List_Available_Tables to check CSV/Excel tables and columns\n"
            "  → STEP 2: If tables exist, call Generic_Spreadsheet_Query_Tool with 'project timeline completion date duration'\n"
            "  → STEP 3: Call List_Payments to check payment schedules (might indicate timeline)\n"
            "  → STEP 4: Call General_Document_Retriever with 'project completion timeline duration'\n"
            "  → STEP 5: Call PDF_Document_Retriever with 'project timeline completion date'\n"
            "  → STEP 6: Synthesize findings from ALL sources and provide answer\n"
            "  → NEVER say 'I cannot find' without doing all these steps\n\n"
            "- User: 'What's the budget?'\n"
            "  → STEP 1: Call List_Available_Tables to see available columns\n"
            "  → STEP 2: Call Generic_Spreadsheet_Query_Tool with 'budget cost total amount'\n"
            "  → STEP 3: Call List_Payments to check payment amounts\n"
            "  → STEP 4: Call General_Document_Retriever with 'budget cost financial'\n"
            "  → STEP 5: Synthesize and provide answer from ALL sources\n\n"
            "- User: 'Who are the workers on this project?'\n"
            "  → STEP 1: Call List_Available_Tables to check for worker tables\n"
            "  → STEP 2: If CSV/Excel tables exist, call Generic_Spreadsheet_Query_Tool with 'workers employees staff'\n"
            "  → STEP 3: Call List_Workers to get all workers from ERP\n"
            "  → STEP 4: Call General_Document_Retriever with 'workers employees project team'\n"
            "  → STEP 5: Combine results from CSV/Excel, ERP, and documents\n\n"
            "- User: 'What payments are due soon?'\n"
            "  → STEP 1: Call List_Available_Tables to check for payment tables\n"
            "  → STEP 2: If CSV/Excel tables exist, call Generic_Spreadsheet_Query_Tool with 'payments due dates upcoming'\n"
            "  → STEP 3: Call Get_Payments_Due_Soon to get ERP payment data\n"
            "  → STEP 4: Call List_Payments with filters for 'pending' status\n"
            "  → STEP 5: Synthesize payment information from ALL sources\n\n"
            "- User: 'What are the safety requirements?'\n"
            "  → STEP 1: Call List_Available_Tables to check for compliance tables\n"
            "  → STEP 2: If tables exist, call Generic_Spreadsheet_Query_Tool with 'safety requirements compliance'\n"
            "  → STEP 3: Call PDF_Document_Retriever with 'safety requirements regulations'\n"
            "  → STEP 4: Call General_Document_Retriever with 'safety compliance'\n"
            "  → STEP 5: Provide answer from ALL sources\n\n"
            
            "IMPORTANT:\n"
            "- Be autonomous: decide the best approach without asking the user\n"
            "- Be PROACTIVE: if you don't know, SEARCH - don't just state that you need information\n"
            "- Think step-by-step: break down complex queries into logical steps\n"
            "- Be file-agnostic: never rely on specific file names or structures\n"
            "- Always cite your sources (table names, row indices, document filenames)\n"
            "- If a query requires data that doesn't exist after searching, clearly state what's missing\n"
            "- When in doubt, search multiple sources - it's better to search too much than too little\n"
            "- Answer the questions no need to elaborate more.\n"
        )

    def _get_conversation(self, session_id: str) -> List:
        """Get or create conversation history for a session."""
        if session_id not in self._conversations:
            # Initialize with system message
            self._conversations[session_id] = [
                SystemMessage(content=self.system_message)
            ]
        return self._conversations[session_id]

    def run(self, message: str, session_id: str) -> str:
        """
        Run the agent with a message and return the response.
        
        The agent will autonomously decide which tools to use based on the query.
        LangChain v1 agents are invoked with: agent.invoke({"messages": [...]})
        """
        # Create callback handler for detailed logging
        callback_handler = AgentAnalysisCallback()
        
        logger.info("=" * 80)
        logger.info("🚀 NEW AGENT REQUEST")
        logger.info("=" * 80)
        logger.info(f"📨 User Message: {message}")
        logger.info(f"🆔 Session ID: {session_id}")
        logger.info(f"⏰ Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 80)
        
        conversation = self._get_conversation(session_id)
        
        # Enhance user message with explicit multi-source search instructions
        enhanced_message = (
            f"{message}\n\n"
            "IMPORTANT: Before responding, you MUST search ALL available data sources:\n"
            "1. Call List_Available_Tables to check CSV/Excel data\n"
            "2. If CSV/Excel tables exist, call Generic_Spreadsheet_Query_Tool with the question\n"
            "3. Call relevant ERP tools (List_Workers, List_Clients, List_Vendors, List_Payments)\n"
            "4. Call General_Document_Retriever to search documents\n"
            "5. Only respond after searching ALL sources. Do not skip CSV/Excel searches."
        )
        
        # Log conversation context
        logger.info(f"📚 Conversation History: {len(conversation)} messages")
        if len(conversation) > 1:
            logger.info(f"   Previous messages in context: {len(conversation) - 1}")
        
        # Add enhanced user message with explicit search instructions
        conversation.append(HumanMessage(content=enhanced_message))
        
        # Log available data
        tables_info = data_registry.list_all_tables()
        if tables_info:
            logger.info("📊 Available Data Tables:")
            for category, tables in tables_info.items():
                logger.info(f"   {category}: {len(tables)} table(s)")
                for table in tables[:3]:  # Show first 3
                    logger.info(f"      - {table['name']} ({table['rows']} rows, {table['columns']} cols)")
        else:
            logger.info("📊 No data tables available")
        
        logger.info("=" * 80)
        logger.info("🧠 STARTING AGENT ANALYSIS...")
        logger.info("=" * 80)
        
        try:
            # Invoke agent with current conversation and callbacks
            # LangChain v1 format: {"messages": [...]}
            result = self.agent.invoke(
                {"messages": conversation},
                config={"callbacks": [callback_handler]}
            )
            
            # Extract the last message (agent's response)
            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                if hasattr(last_message, "content"):
                    output = last_message.content
                else:
                    output = str(last_message)
            else:
                output = "No response generated."
                        
            # Log summary
            summary = callback_handler.get_summary()
            logger.info("=" * 80)
            logger.info("✅ AGENT ANALYSIS COMPLETE")
            logger.info("=" * 80)
            logger.info(f"📊 Total Steps: {summary['total_steps']}")
            logger.info(f"🔧 Tool Calls: {len(summary['tool_calls'])}")
            for i, tool_call in enumerate(summary['tool_calls'], 1):
                logger.info(f"   {i}. {tool_call['tool']}")
            logger.info("=" * 80)
            
        except Exception as e:
            logger.error("=" * 80)
            logger.error("❌ AGENT ERROR")
            logger.error("=" * 80)
            logger.error(f"Error: {str(e)}")
            logger.error(f"Error Type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            logger.error("=" * 80)
            raise
        
        # Update conversation history with agent's response
        conversation.append(AIMessage(content=output))
        
        # Keep conversation history manageable (last 20 messages)
        if len(conversation) > 20:
            # Keep system message and last 19 messages
            conversation = [conversation[0]] + conversation[-19:]
            self._conversations[session_id] = conversation
        
        return output


agent_orchestrator = AgentOrchestrator()
