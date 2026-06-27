import streamlit as st
import os
import pandas as pd
from dotenv import load_dotenv
import streamlit.components.v1 as components
from pyvis.network import Network

# Load environment variables
load_dotenv()

# We'll import our ingestion client and extraction modules
from src.ingestion.github_client import GitHubIngestionClient
from src.extraction.code_analyzer import PythonCodeAnalyzer
from src.extraction.decision_extractor import DecisionExtractor
from src.extraction.history_analyzer import HistoryAnalyzer
from src.graph.knowledge_graph import KnowledgeGraph
from src.agents.langgraph_orchestrator import OnboardingOrchestrator

st.set_page_config(page_title="AI Onboarding Buddy", layout="wide", initial_sidebar_state="expanded")

st.title("🚀 AI Onboarding Buddy")
st.markdown("Welcome to the MVP. Let's explore the repository structure, extract AI insights, and talk to our LangGraph orchestrator.")

# Sidebar for configuration
with st.sidebar:
    st.header("Configuration")
    github_token = st.text_input("GitHub Token (Optional)", type="password", value=os.environ.get("GITHUB_TOKEN", ""))
    openrouter_key_1 = st.text_input("OpenRouter API Key 1 (For Extraction)", type="password", value=os.environ.get("OPENROUTER_API_KEY_1", ""))
    openrouter_key_2 = st.text_input("OpenRouter API Key 2 (For Agents)", type="password", value=os.environ.get("OPENROUTER_API_KEY_2", ""))
    repo_name = st.text_input("Repository", value="tiangolo/fastapi")
    
    st.divider()
    st.subheader("Ingestion Settings")
    fetch_all = st.checkbox("Fetch ALL historical data (Not recommended without token)")
    item_limit = None if fetch_all else st.number_input("Limit items to fetch", min_value=1, max_value=500, value=5)

# Initialize Session State
if "kg" not in st.session_state:
    st.session_state.kg = KnowledgeGraph()
if "data_fetched" not in st.session_state:
    st.session_state.data_fetched = False
    st.session_state.commits = []
    st.session_state.prs = []
    st.session_state.structure = []
    st.session_state.quick_results = {}

# Main content area
st.header("Modules 1-5: The Complete Pipeline")

if st.button("Fetch, Extract & Build Graph", type="primary"):
    if repo_name:
        with st.spinner(f"Processing {repo_name} & Building Knowledge Graph (This may take a minute)..."):
            try:
                client = GitHubIngestionClient(token=github_token)
                code_analyzer = PythonCodeAnalyzer()
                decision_extractor = DecisionExtractor(api_key=openrouter_key_1)
                
                # Fetch Data
                structure = client.fetch_repo_structure(repo_name)
                commits = client.fetch_commits(repo_name, limit=item_limit)
                prs = client.fetch_prs(repo_name, limit=item_limit)
                
                # Save to session state for dashboard
                st.session_state.structure = structure
                st.session_state.commits = commits
                st.session_state.prs = prs
                
                # Build Graph
                for commit in commits[:10]: # Limit for MVP speed
                    st.session_state.kg.add_commit(commit['sha'], commit['author'], commit['message'])
                    
                for pr in prs[:5]: # Limit for MVP speed
                    st.session_state.kg.add_pr(pr['number'], pr['title'], pr['body'] or "", pr['user'])
                    if openrouter_key_1:
                        extraction = decision_extractor.extract(pr['title'], pr['body'])
                        if "error" not in extraction:
                            st.session_state.kg.add_decision(
                                pr['number'], 
                                extraction.get("decision", ""), 
                                extraction.get("reasoning", ""), 
                                extraction.get("impact", "")
                            )
                            
                # Pre-call all 4 agent paths
                if openrouter_key_2:
                    st.info("Pre-calculating Agent Executive Summaries...")
                    orchestrator = OnboardingOrchestrator(st.session_state.kg, openrouter_api_key=openrouter_key_2)
                    st.session_state.quick_results["Code Explanation"] = orchestrator.ask("Explain the core code components of this repository.")
                    st.session_state.quick_results["Architecture Map"] = orchestrator.ask("How do the components connect? Give me an architecture map.")
                    st.session_state.quick_results["Decision Timeline"] = orchestrator.ask("What is the timeline of architectural decisions made in PRs?")
                    st.session_state.quick_results["Learning Path"] = orchestrator.ask("Create a Day 1 to Day N learning path for a new engineer.")
                
                st.session_state.data_fetched = True
                st.success("Successfully fetched data, built Graph, and pre-calculated Executive Summaries!")
            except Exception as e:
                st.error(f"Error fetching data: {str(e)}")
    else:
        st.warning("Please enter a repository name.")

if st.session_state.data_fetched:
    st.divider()
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📂 Structure", 
        "📜 Commits Analysis", 
        "🔄 PRs & Decisions",
        "🧠 Visual Knowledge Graph",
        "📊 Executive Summary (Pre-Called)",
        "🤖 Chat with Agents"
    ])
    
    with tab1:
        st.subheader("Repository File Structure")
        if st.session_state.structure:
            df = pd.DataFrame(st.session_state.structure)
            st.dataframe(df, width='stretch')
        else:
            st.info("No structure found or root is empty.")
    
    with tab2:
        st.subheader("Commit History & Code Changes")
        commits = st.session_state.commits
        if not commits:
            st.info("No commits found.")
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("### Select a Commit")
                commit_options = {c['sha']: f"{c['sha'][:7]} - {c['message'].split(chr(10))[0]}" for c in commits}
                selected_sha = st.selectbox("Commits", options=list(commit_options.keys()), format_func=lambda x: commit_options[x])
            with col2:
                selected_commit = next((c for c in commits if c['sha'] == selected_sha), None)
                if selected_commit:
                    st.markdown(f"### {selected_commit['message']}")
                    st.caption(f"Author: **{selected_commit['author']}** | Date: {selected_commit['date']}")
                    total_additions = sum(f.get('additions', 0) for f in selected_commit['files_changed'])
                    total_deletions = sum(f.get('deletions', 0) for f in selected_commit['files_changed'])
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Files Changed", len(selected_commit['files_changed']))
                    m2.metric("Additions", f"+{total_additions}")
                    m3.metric("Deletions", f"-{total_deletions}")
                    st.divider()
                    st.markdown("#### File Changes")
                    for f in selected_commit['files_changed']:
                        status_color = "green" if f['status'] == "added" else "red" if f['status'] == "removed" else "blue"
                        with st.expander(f"📄 {f['filename']} ({f['status']}) | +{f['additions']} -{f['deletions']}"):
                            if f.get('patch'):
                                st.code(f['patch'], language='diff')
                            else:
                                st.info("No patch available (binary file or too large).")

    with tab3:
        st.subheader("Pull Requests & Discussions")
        prs = st.session_state.prs
        if not prs:
            st.info("No PRs found.")
        else:
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("### Select a PR")
                pr_options = {pr['number']: f"PR #{pr['number']}: {pr['title']}" for pr in prs}
                selected_pr_num = st.selectbox("Pull Requests", options=list(pr_options.keys()), format_func=lambda x: pr_options[x])
            with col2:
                selected_pr = next((p for p in prs if p['number'] == selected_pr_num), None)
                if selected_pr:
                    st.markdown(f"### {selected_pr['title']} (#{selected_pr['number']})")
                    state_color = "green" if selected_pr['state'] == "open" else "purple" if selected_pr['merged'] else "red"
                    st.markdown(f"**Author:** {selected_pr['user']} | **State:** :{state_color}[{selected_pr['state'].upper()}]")
                    st.markdown("#### Description")
                    st.info(selected_pr['body'] if selected_pr['body'] else "*No description provided.*")
                    st.divider()
                    st.markdown("#### PR File Changes")
                    for f in selected_pr['files_changed']:
                        with st.expander(f"📄 {f['filename']} ({f['status']}) | +{f['additions']} -{f['deletions']}"):
                            if f.get('patch'):
                                st.code(f['patch'], language='diff')
                            else:
                                st.info("No patch available.")
    
    with tab4:
        st.subheader("Visual Knowledge Graph")
        st.markdown("This graph maps the structural relationships between Developers, Commits, PRs, and Code Components.")
        
        if st.session_state.kg.graph.number_of_nodes() > 0:
            try:
                # Create a pyvis network from NetworkX
                net = Network(height='600px', width='100%', bgcolor='#0E1117', font_color='white')
                # Optional: customize nodes based on type
                for node, attrs in st.session_state.kg.graph.nodes(data=True):
                    node_type = attrs.get('type', 'Unknown')
                    color = '#ff4b4b' if node_type == 'Commit' else '#0068c9' if node_type == 'PullRequest' else '#29b09d'
                    net.add_node(node, label=str(node), title=f"Type: {node_type}", color=color)
                for source, target, attrs in st.session_state.kg.graph.edges(data=True):
                    net.add_edge(source, target, title=attrs.get('relation', ''))
                
                # Save and display
                net.save_graph('kg_viz.html')
                HtmlFile = open('kg_viz.html', 'r', encoding='utf-8')
                source_code = HtmlFile.read() 
                components.html(source_code, height=620)
            except Exception as e:
                st.error(f"Failed to render graph visually: {str(e)}")
        else:
            st.info("No nodes in the graph to visualize.")

    with tab5:
        st.subheader("Executive Summaries (Pre-Called via LangGraph)")
        st.info("During data ingestion, the Orchestrator automatically pre-calculated these views using the Code, Decision, Architecture, and Learning Agents.")
        
        if not st.session_state.quick_results:
            st.warning("Please provide OpenRouter API Key 2 and re-fetch to generate summaries.")
        else:
            c1, c2 = st.columns(2)
            c3, c4 = st.columns(2)
            
            with c1:
                with st.expander("📚 Code Explanation", expanded=True):
                    res = st.session_state.quick_results.get("Code Explanation", {})
                    st.write(res.get('final_answer', 'Not generated.'))
            with c2:
                with st.expander("🗺️ Architecture Map", expanded=True):
                    res = st.session_state.quick_results.get("Architecture Map", {})
                    st.write(res.get('final_answer', 'Not generated.'))
            with c3:
                with st.expander("⏱️ Decision Timeline", expanded=True):
                    res = st.session_state.quick_results.get("Decision Timeline", {})
                    st.write(res.get('final_answer', 'Not generated.'))
            with c4:
                with st.expander("🎓 Learning Path", expanded=True):
                    res = st.session_state.quick_results.get("Learning Path", {})
                    st.write(res.get('final_answer', 'Not generated.'))

    with tab6:
        st.subheader("Module 4 & 5: Ask the LangGraph Orchestrator")
        st.info("The LangGraph Supervisor analyzes your prompt, routes it to the specialized Agents, executes semantic search on the Knowledge Graph (GraphRAG), and Synthesizes a response.")
        
        user_q = st.text_input("Ask a custom question about the repository:")
        
        if st.button("Ask Agent", type="primary"):
            if not openrouter_key_2:
                st.warning("Please provide OpenRouter API Key 2 in the sidebar.")
            else:
                with st.spinner("Agent Orchestrator is executing..."):
                    orchestrator = OnboardingOrchestrator(st.session_state.kg, openrouter_api_key=openrouter_key_2)
                    result = orchestrator.ask(user_q)
                    
                    if "error" in result and result["error"]:
                        st.error(result["error"])
                    else:
                        st.markdown(f"**Agent Routed To:** `{result.get('next_agent', 'SYNTHESIZER')}`")
                        st.markdown("### Answer")
                        st.write(result.get('final_answer', 'No answer generated.'))
                        with st.expander("View RAG Context Retrieved from Graph"):
                            for ctx in result.get("current_context", []):
                                st.markdown(f"```text\n{ctx}\n```")
