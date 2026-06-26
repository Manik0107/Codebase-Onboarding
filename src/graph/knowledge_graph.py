import networkx as nx
import chromadb
from chromadb.utils import embedding_functions
import os
from typing import List, Dict, Any

class KnowledgeGraph:
    """
    Manages the graph connecting Code structures to originating PRs and Commits (NetworkX for MVP).
    Uses ChromaDB for vector-based semantic search of code and decisions.
    """
    def __init__(self, db_path: str = "./chroma_db"):
        self.graph = nx.DiGraph()
        
        # Initialize Vector DB
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        
        # Setup OpenAI Embeddings if available to avoid ONNX/sentence-transformers issues on Windows
        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            self.ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=openai_key,
                model_name="text-embedding-3-small"
            )
        else:
            self.ef = None # Will fallback to default ONNX model
            
        # Collections for different types of embeddings
        self.code_collection = self.chroma_client.get_or_create_collection(
            name="code_snippets", 
            embedding_function=self.ef if self.ef else None
        )
        self.decision_collection = self.chroma_client.get_or_create_collection(
            name="pr_decisions", 
            embedding_function=self.ef if self.ef else None
        )
        
    def add_commit(self, sha: str, author: str, message: str):
        self.graph.add_node(sha, type="Commit", author=author, message=message)
        self.graph.add_node(author, type="Author")
        self.graph.add_edge(author, sha, relation="AUTHORED")
        
    def add_pr(self, number: int, title: str, body: str, author: str):
        pr_id = f"PR#{number}"
        self.graph.add_node(pr_id, type="PullRequest", title=title, body=body)
        self.graph.add_node(author, type="Author")
        self.graph.add_edge(author, pr_id, relation="OPENED")
        
    def link_commit_to_pr(self, sha: str, pr_number: int):
        self.graph.add_edge(f"PR#{pr_number}", sha, relation="CONTAINS_COMMIT")
        
    def add_code_snippet(self, file_path: str, name: str, snippet_type: str, content: str, docstring: str, commit_sha: str = None):
        """Adds a code structure to graph and its embedding to Chroma."""
        node_id = f"{file_path}::{name}"
        self.graph.add_node(node_id, type=snippet_type, name=name, file_path=file_path)
        
        if commit_sha:
            self.graph.add_edge(commit_sha, node_id, relation="MODIFIED")
            
        # Add to vector DB
        metadata = {"file_path": file_path, "name": name, "type": snippet_type}
        if commit_sha:
            metadata["commit_sha"] = commit_sha
            
        # Use content + docstring for richer search
        text_to_embed = f"{snippet_type} {name}\nDocstring: {docstring}\nContent: {content}"
        
        self.code_collection.add(
            documents=[text_to_embed],
            metadatas=[metadata],
            ids=[node_id]
        )
        
    def add_decision(self, pr_number: int, decision: str, reasoning: str, impact: str):
        """Adds architectural decisions to Vector DB."""
        pr_id = f"PR#{pr_number}"
        text_to_embed = f"Decision: {decision}\nReasoning: {reasoning}\nImpact: {impact}"
        self.decision_collection.add(
            documents=[text_to_embed],
            metadatas=[{"pr_number": pr_number, "impact": impact}],
            ids=[pr_id]
        )
        
    def search_code(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Semantic search for code snippets."""
        results = self.code_collection.query(
            query_texts=[query],
            n_results=limit
        )
        # Format results
        formatted = []
        if results['documents'] and len(results['documents'][0]) > 0:
            for i in range(len(results['documents'][0])):
                formatted.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i]
                })
        return formatted
        
    def search_decisions(self, query: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Semantic search for architectural decisions."""
        results = self.decision_collection.query(
            query_texts=[query],
            n_results=limit
        )
        formatted = []
        if results['documents'] and len(results['documents'][0]) > 0:
            for i in range(len(results['documents'][0])):
                formatted.append({
                    "id": results['ids'][0][i],
                    "document": results['documents'][0][i],
                    "metadata": results['metadatas'][0][i]
                })
        return formatted
        
    def get_pr_for_code(self, code_id: str) -> List[str]:
        """Graph traversal: Find which PR introduced or modified this code."""
        if code_id not in self.graph:
            return []
            
        # Code <- MODIFIED - Commit <- CONTAINS_COMMIT - PR
        prs = []
        for pred in self.graph.predecessors(code_id):
            edge_data = self.graph.get_edge_data(pred, code_id)
            if edge_data.get('relation') == 'MODIFIED':
                # This predecessor is a Commit. Find its PRs
                for pr_pred in self.graph.predecessors(pred):
                    pr_edge = self.graph.get_edge_data(pr_pred, pred)
                    if pr_edge.get('relation') == 'CONTAINS_COMMIT':
                        prs.append(pr_pred)
        return prs
