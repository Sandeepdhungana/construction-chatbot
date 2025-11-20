"""Prompt templates for LangChain agent (optional - can be used with middleware)."""

# LangChain v1 import
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder


def react_prompt() -> ChatPromptTemplate:
    """
    Prompt template for the agent (optional in LangChain v1).
    
    Note: LangChain v1's create_agent() doesn't take a prompt parameter.
    System messages are handled via initial messages or middleware.
    This is kept for reference or future middleware usage.
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are ConstructionBot, a senior construction compliance analyst. "
                    "Carefully read governing PDFs (contracts, safety manuals) and cross-check "
                    "with structured CSV datasets (materials, workforce). "
                    "Always cite clauses or row indices, avoid assumptions, and explain when "
                    "data must be combined across both modalities."
                ),
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )


