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
            
            "DECISION-MAKING PROCESS:\n"
            "For every user query, you must autonomously decide the best approach:\n"
            "1. ANALYZE the query to determine what type of information is needed:\n"
            "   - Structured data queries (numbers, calculations, aggregations, filtering) → Use spreadsheet tools\n"
            "   - Unstructured content (regulations, clauses, descriptions, text search) → Use document retrieval tools\n"
            "   - Combined queries (e.g., 'What does the contract say about X and how much do we have?') → Use BOTH\n\n"
            
            "2. STEP-BY-STEP REASONING:\n"
            "   - First, understand what the user is asking\n"
            "   - Determine if you need structured data, unstructured documents, or both\n"
            "   - If structured: Check available tables using 'List Available Tables' tool\n"
            "   - If unstructured: Use appropriate document retriever (PDF, DOCX, PPTX, Image)\n"
            "   - If combined: Gather information from both sources, then synthesize\n\n"
            
            "3. SPREADSHEET OPERATIONS (when needed):\n"
            "   - Use 'Generic Spreadsheet Query Tool' for single-table queries\n"
            "   - Use 'Multi-Table Analysis Tool' for joins, cross-table analysis, aggregations\n"
            "   - Support all operations: filtering (>, <, >=, <=, =, !=, contains, in/not in), "
            "grouping, aggregations (sum, avg, count, min, max), joins\n"
            "   - Never assume column names - always check table structure first if unsure\n"
            "   - Reason through multiple steps for complex queries\n\n"
            
            "4. DOCUMENT OPERATIONS (when needed):\n"
            "   - Use specific retrievers (PDF, DOCX, PPTX, Image) when you know the source type\n"
            "   - Use 'General Document Retriever' when unsure\n"
            "   - Always cite filenames and page/row numbers\n\n"
            
            "5. SYNTHESIS:\n"
            "   - When combining structured and unstructured data, use 'Answer Synthesizer' tool\n"
            "   - Provide comprehensive answers with proper citations\n"
            "   - Explain your reasoning when combining multiple data sources\n\n"
            
            "IMPORTANT:\n"
            "- Be autonomous: decide the best approach without asking the user\n"
            "- Think step-by-step: break down complex queries into logical steps\n"
            "- Be file-agnostic: never rely on specific file names or structures\n"
            "- Always cite your sources (table names, row indices, document filenames)\n"
            "- If a query requires data that doesn't exist, clearly state what's missing\n"
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
        
        # Log conversation context
        logger.info(f"📚 Conversation History: {len(conversation)} messages")
        if len(conversation) > 1:
            logger.info(f"   Previous messages in context: {len(conversation) - 1}")
        
        # Add user message
        conversation.append(HumanMessage(content=message))
        
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
