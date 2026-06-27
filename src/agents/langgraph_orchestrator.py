import os
from typing import TypedDict, List, Dict, Any, Literal
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from src.graph.knowledge_graph import KnowledgeGraph

# Define State
class AgentState(TypedDict):
    user_question: str
    current_context: List[str]
    next_agent: str
    final_answer: str
    error: str

class OnboardingOrchestrator:
    def __init__(self, knowledge_graph: KnowledgeGraph, openrouter_api_key: str = None):
        self.kg = knowledge_graph
        self.api_key = openrouter_api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        
        # Initialize LLM using OpenRouter via LangChain ChatOpenAI
        if self.api_key:
            self.llm = ChatOpenAI(
                openai_api_base="https://openrouter.ai/api/v1",
                openai_api_key=self.api_key,
                model_name="meta-llama/llama-3.1-8b-instruct", # Defaulting to a solid model on OpenRouter
                temperature=0,
                max_tokens=800 # Limit maximum tokens to prevent OpenRouter upfront cost rejection
            )
        else:
            self.llm = None

        self.graph = self._build_graph()

    def _supervisor_node(self, state: AgentState):
        if not self.llm:
            return {"error": "API Key is missing for the Orchestrator."}
            
        question = state["user_question"]
        context_length = len(state.get("current_context", []))
        
        # If we already have some context, route to synthesizer to attempt an answer
        if context_length > 0:
            return {"next_agent": "SYNTHESIZER"}
            
        prompt = f"""
        You are a supervisor routing a user question to the correct expert agent.
        Question: "{question}"
        
        Options:
        - "CODE_AGENT": If the question is about how code works, file structure, classes, or functions.
        - "DECISION_AGENT": If the question is about why something was built, architectural decisions, or PRs.
        - "ARCHITECTURE_AGENT": If the question is about system architecture, how services connect, or request flows.
        - "LEARNING_AGENT": If the question is asking for a learning path, what to do on day 1, or how to get started.
        
        Respond with ONLY the string "CODE_AGENT", "DECISION_AGENT", "ARCHITECTURE_AGENT", or "LEARNING_AGENT".
        """
        response = self.llm.invoke([SystemMessage(content=prompt)])
        decision = response.content.strip()
        valid_agents = ["CODE_AGENT", "DECISION_AGENT", "ARCHITECTURE_AGENT", "LEARNING_AGENT"]
        if decision not in valid_agents:
            decision = "CODE_AGENT" # Fallback
            
        return {"next_agent": decision}

    def _code_agent_node(self, state: AgentState):
        question = state["user_question"]
        results = self.kg.search_code(question, limit=3)
        
        context_updates = []
        for res in results:
            context_updates.append(f"Code Snippet: {res['metadata'].get('name')} in {res['metadata'].get('file_path')}\n{res['document']}")
            
        current_context = state.get("current_context", [])
        return {"current_context": current_context + context_updates}

    def _decision_agent_node(self, state: AgentState):
        question = state["user_question"]
        results = self.kg.search_decisions(question, limit=3)
        
        context_updates = []
        for res in results:
            context_updates.append(f"PR Decision: PR#{res['metadata'].get('pr_number')}\n{res['document']}")
            
        current_context = state.get("current_context", [])
        return {"current_context": current_context + context_updates}

    def _architecture_agent_node(self, state: AgentState):
        question = state["user_question"]
        # In a full implementation, this traverses the Neo4j graph to find dependencies.
        # For MVP, we combine code snippets and decisions that relate to architecture.
        code_results = self.kg.search_code("architecture system flow " + question, limit=2)
        dec_results = self.kg.search_decisions("architecture system flow " + question, limit=2)
        
        context_updates = ["Agent Action: Tracing architecture dependencies across modules."]
        for res in code_results:
            context_updates.append(f"Code Arch: {res['document']}")
        for res in dec_results:
            context_updates.append(f"Decision Arch: {res['document']}")
            
        current_context = state.get("current_context", [])
        return {"current_context": current_context + context_updates}
        
    def _learning_agent_node(self, state: AgentState):
        # A static instructional context meant to prompt the Synthesizer into making a Day 1-N plan
        context_updates = [
            "Agent Action: Building a learning path.",
            "Directive for Synthesizer: Create a structured Day 1 to Day N onboarding plan based on the core components available in the codebase."
        ]
        
        current_context = state.get("current_context", [])
        return {"current_context": current_context + context_updates}

    def _synthesizer_node(self, state: AgentState):
        if not self.llm:
            return {"error": "API Key is missing for the Orchestrator."}
            
        question = state["user_question"]
        context_str = "\n\n---\n\n".join(state.get("current_context", []))
        
        prompt = f"""
        You are an AI Onboarding Buddy helping a new engineer understand a codebase.
        Use the provided context to answer the question clearly and concisely.
        If the context doesn't contain the answer, say that you don't have enough information.
        
        Context:
        {context_str}
        
        Question: {question}
        """
        response = self.llm.invoke([SystemMessage(content=prompt)])
        return {"final_answer": response.content}

    def _build_graph(self):
        workflow = StateGraph(AgentState)
        
        workflow.add_node("Supervisor", self._supervisor_node)
        workflow.add_node("CodeAgent", self._code_agent_node)
        workflow.add_node("DecisionAgent", self._decision_agent_node)
        workflow.add_node("ArchitectureAgent", self._architecture_agent_node)
        workflow.add_node("LearningAgent", self._learning_agent_node)
        workflow.add_node("Synthesizer", self._synthesizer_node)
        
        workflow.set_entry_point("Supervisor")
        
        # Conditional routing from Supervisor
        workflow.add_conditional_edges(
            "Supervisor",
            lambda x: x.get("next_agent", "SYNTHESIZER"),
            {
                "CODE_AGENT": "CodeAgent",
                "DECISION_AGENT": "DecisionAgent",
                "ARCHITECTURE_AGENT": "ArchitectureAgent",
                "LEARNING_AGENT": "LearningAgent",
                "SYNTHESIZER": "Synthesizer"
            }
        )
        
        # Agents always go to Synthesizer next for this MVP
        workflow.add_edge("CodeAgent", "Synthesizer")
        workflow.add_edge("DecisionAgent", "Synthesizer")
        workflow.add_edge("ArchitectureAgent", "Synthesizer")
        workflow.add_edge("LearningAgent", "Synthesizer")
        
        workflow.add_edge("Synthesizer", END)
        
        return workflow.compile()
        
    def ask(self, question: str) -> Dict[str, Any]:
        initial_state = {
            "user_question": question,
            "current_context": [],
            "next_agent": "",
            "final_answer": "",
            "error": ""
        }
        
        try:
            # invoke the graph
            result = self.graph.invoke(initial_state)
            return result
        except Exception as e:
            return {"error": str(e)}
