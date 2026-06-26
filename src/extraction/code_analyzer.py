import ast

class PythonCodeAnalyzer:
    """
    Analyzes Python source code to extract classes, functions, and docstrings.
    This replaces heavy AST parsers for the MVP to ensure fast, native execution.
    """
    def analyze(self, source_code: str):
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return {"error": f"Syntax Error: {str(e)}"}

        classes = []
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "docstring": ast.get_docstring(node),
                    "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                })
            elif isinstance(node, ast.FunctionDef):
                functions.append({
                    "name": node.name,
                    "docstring": ast.get_docstring(node),
                    "args": [arg.arg for arg in node.args.args]
                })
                
        return {
            "classes": classes,
            "functions": functions
        }
