import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

class DecisionExtractor:
    """
    Uses an LLM (via LangChain and OpenRouter) to read Pull Request discussions 
    and extract the 'why' behind decisions.
    """
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if self.api_key:
            self.llm = ChatOpenAI(
                openai_api_base="https://openrouter.ai/api/v1",
                openai_api_key=self.api_key,
                model_name="meta-llama/llama-3.1-8b-instruct",
                temperature=0,
                max_tokens=300 # Limit maximum tokens to prevent OpenRouter upfront cost rejection
            )
        else:
            self.llm = None

    def extract(self, pr_title: str, pr_body: str):
        if not self.llm:
            return {"error": "API Key is required for Decision Extraction."}
            
        prompt = f"""
        Analyze the following Pull Request and extract the key architectural or engineering decision made.
        Return ONLY a JSON object with the following keys:
        - "decision": A short 1-sentence summary of what was decided or implemented.
        - "reasoning": Why it was implemented this way (the 'why').
        - "impact": What system or component this affects.

        PR Title: {pr_title}
        PR Body: {pr_body or "No description provided."}
        """
        
        try:
            response = self.llm.invoke([SystemMessage(content=prompt)])
            # Langchain OpenRouter responses might contain markdown formatting like ```json ... ```
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
        except Exception as e:
            return {"error": f"Failed to extract or parse JSON: {str(e)}"}
