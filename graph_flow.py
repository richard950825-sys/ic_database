from langgraph.graph import StateGraph, END
from typing import List, Dict, Any, TypedDict
import logging
from concurrent.futures import ThreadPoolExecutor

# Logic components imported for type hinting or usage if needed
from agents.router import QueryRouter
from agents.analyzer import DomainAnalyzer
from agents.auditor import ResponseAuditor
from core.vector_store import VectorStore
from core.graph_store import GraphStore
from core.config import settings

logger = logging.getLogger("graph_flow")

# Define State
class AgentState(TypedDict):
    query: str
    route: Dict[str, Any]
    retrieved_contexts: List[Dict[str, Any]]
    analysis_result: Dict[str, Any]
    generated_answer: str
    audit_result: Dict[str, Any]
    audit_passed: bool
    revision_count: int
    components: Dict[str, Any]

# Nodes

def router_node(state: AgentState) -> AgentState:
    """
    路由节点：将用户查询路由到不同的处理流程
    """
    router = state["components"]["router"]
    query = state["query"]
    logger.info(f"[路由节点] 开始处理用户查询：'{query}'")
    
    logger.info(f"[路由节点] 调用路由器进行查询分类")
    route_result = router.route_query(query)
    logger.info(f"[路由节点] 查询路由结果：{route_result}")
    
    return {"route": route_result, "revision_count": 0}

def retrieval_node(state: AgentState) -> AgentState:
    """
    检索节点：根据路由结果执行相应的检索策略
    """
    router = state["components"]["router"]
    vector_store = state["components"]["vector_store"]
    graph_store = state["components"]["graph_store"]
    executor = state["components"].get("executor")
    
    query = state["query"]
    route_type = state["route"]["route_type"]
    keywords = state["route"].get("keywords", [])
    
    logger.info(f"[检索节点] 开始检索 - 查询: '{query}', 路由类型: '{route_type}', 关键词: {keywords}")
    
    retrieval_strategy = router.get_retrieval_strategy(route_type)
    
    # Retrieval definitions
    def run_exact_match():
        if "exact_match" in retrieval_strategy["methods"]:
            return vector_store.exact_match_search(query, limit=settings.EXACT_MATCH_LIMIT)
        return []

    def run_vector_search():
        if "vector_search" in retrieval_strategy["methods"]:
            limit = settings.VECTOR_SEARCH_LIMIT
            if hasattr(vector_store, 'search_similar'):
                return vector_store.search_similar(query, limit=limit)
            return vector_store.search(query, limit=limit)
        return []

    def run_graph_search():
        if "graph_search" in retrieval_strategy["methods"]:
            graph_results = []
            search_terms = keywords if keywords else [w for w in query.split() if len(w) > 1][:3]
            if not search_terms: return []
            
            seen = set()
            all_relations = []
            for term in search_terms:
                rels = graph_store.search_relations(term)
                for r in rels:
                    k = f"{r['source']}|{r['relation']}|{r['target']}"
                    if k not in seen:
                        seen.add(k)
                        all_relations.append(r)
            
            if all_relations:
                txt = "图谱关系：\n" + "\n".join([f"- {r['source']} {r['relation']} {r['target']}" for r in all_relations[:settings.GRAPH_SEARCH_LIMIT]])
                graph_results.append({
                    "score": 1.0, 
                    "metadata": {"file_name": "knowledge_graph", "content": txt, "page": 0, "type": "graph"},
                    "id": "graph_1"
                })
            return graph_results
        return []

    def run_table_search():
        if "table_extraction" in retrieval_strategy["methods"]:
            return vector_store.search_tables(query, limit=3)
        return []

    def run_image_search():
        if "image_retrieval" in retrieval_strategy["methods"]:
            return vector_store.search_images(query, limit=2)
        return []

    retrieved_contexts = []
    
    # Use injected executor or local fallback (safe fallback if executor missing for tests)
    local_executor = None
    if executor is None:
        logger.warning("No executor provided in components, creating local ThreadPoolExecutor")
        local_executor = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS)
        run_executor = local_executor
    else:
        run_executor = executor

    try:
        futures = []
        if executor:
            # If using shared executor, we submit tasks
            futures.append(executor.submit(run_exact_match))
            futures.append(executor.submit(run_vector_search))
            futures.append(executor.submit(run_graph_search))
            futures.append(executor.submit(run_table_search))
            futures.append(executor.submit(run_image_search))
        else:
             # Logic duplicate mostly to handle Context Manager if creating new
             futures.append(run_executor.submit(run_exact_match))
             futures.append(run_executor.submit(run_vector_search))
             futures.append(run_executor.submit(run_graph_search))
             futures.append(run_executor.submit(run_table_search))
             futures.append(run_executor.submit(run_image_search))

        for f in futures:
            try:
                retrieved_contexts.extend(f.result())
            except Exception as e:
                logger.error(f"Search task failed: {e}")
                
    finally:
        if local_executor:
            local_executor.shutdown()

    # Deduplication
    seen_contents = set()
    unique_contexts = []
    for ctx in retrieved_contexts:
        # Use content+file+page hash key
        content = ctx['metadata'].get('content', '')
        file_name = ctx['metadata'].get('file_name', '')
        page = ctx['metadata'].get('page', '')
        content_key = f"{content}_{file_name}_{page}"
        content_hash = hash(content_key)
        
        if content_hash not in seen_contents:
            seen_contents.add(content_hash)
            unique_contexts.append(ctx)
    
    logger.info(f"[检索节点] 检索完成，找到 {len(unique_contexts)} 个上下文")
    return {"retrieved_contexts": unique_contexts}

def analysis_node(state: AgentState) -> AgentState:
    domain_analyzer = state["components"]["domain_analyzer"]
    query = state["query"]
    retrieved_contexts = state["retrieved_contexts"]
    
    logger.info(f"[分析节点] 开始分析上下文")
    analysis_result = domain_analyzer.analyze_context(query, retrieved_contexts)
    logger.debug(f"[分析节点] 分析结果: {analysis_result}")
    
    return {"analysis_result": analysis_result}

def generation_node(state: AgentState) -> AgentState:
    domain_analyzer = state["components"]["domain_analyzer"]
    query = state["query"]
    retrieved_contexts = state["retrieved_contexts"]
    analysis_result = state["analysis_result"]
    
    logger.info(f"[生成节点] 开始生成回答")
    generated_answer = domain_analyzer.generate_answer(query, retrieved_contexts, analysis_result)
    
    formatted_answer = domain_analyzer.format_answer_with_references(generated_answer, retrieved_contexts)
    logger.info(f"[生成节点] 生成完成, 长度: {len(formatted_answer)}")
    
    return {"generated_answer": formatted_answer}

def audit_node(state: AgentState) -> AgentState:
    auditor = state["components"]["auditor"]
    retrieved_contexts = state["retrieved_contexts"]
    generated_answer = state["generated_answer"]
    
    logger.info(f"[审计节点] 开始审计")
    audit_result = auditor.audit_response(retrieved_contexts, generated_answer)
    logger.info(f"[审计节点] 审计结果: {'通过' if audit_result['audit_passed'] else '不通过'}")
    
    return {
        "audit_result": audit_result, 
        "audit_passed": audit_result['audit_passed'],
        "revision_count": state["revision_count"] + 1
    }

def correction_node(state: AgentState) -> AgentState:
    auditor = state["components"]["auditor"]
    domain_analyzer = state["components"]["domain_analyzer"]
    audit_result = state["audit_result"]
    
    logger.info(f"[修正节点] 开始修正")
    correction_prompt = auditor.generate_correction_prompt(audit_result)
    
    corrected_answer = domain_analyzer.generate_answer(
        correction_prompt, 
        audit_result["original_contexts"], 
        {"key_information": [], "context_summary": "", "context_relations": [], "information_gaps": "无"}
    )
    
    formatted_corrected_answer = domain_analyzer.format_answer_with_references(
        corrected_answer, 
        audit_result["original_contexts"]
    )
    
    return {"generated_answer": formatted_corrected_answer}

def should_revise(state: AgentState) -> bool:
    need_revision = not state["audit_passed"] and state["revision_count"] < 3
    logger.info(f"[条件判断] 是否需要修订: {need_revision}")
    return need_revision

# Build Graph
# Notice: Dependencies are injected at runtime, so graph definition is static
def build_workflow():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("router", router_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("analyze", analysis_node)
    workflow.add_node("generate", generation_node)
    workflow.add_node("audit", audit_node)
    workflow.add_node("correct", correction_node)
    
    workflow.add_edge("router", "retrieve")
    workflow.add_edge("retrieve", "analyze")
    workflow.add_edge("analyze", "generate")
    workflow.add_edge("generate", "audit")
    
    workflow.add_conditional_edges(
        "audit",
        should_revise,
        {True: "correct", False: END}
    )
    workflow.add_edge("correct", "audit")
    
    workflow.set_entry_point("router")
    return workflow.compile()

# Run Workflow
def run_workflow(query: str, components: Dict[str, Any] = None) -> Dict[str, Any]:
    if components is None:
        raise ValueError("Components must be provided to run_workflow")

    app = build_workflow()
    
    initial_state = {
        "query": query,
        "route": {},
        "retrieved_contexts": [],
        "analysis_result": {},
        "generated_answer": "",
        "audit_result": {},
        "audit_passed": False,
        "revision_count": 0,
        "components": components
    }
    
    result = app.invoke(initial_state)
    
    return {
        "query": result["query"],
        "generated_answer": result["generated_answer"],
        "audit_passed": result["audit_passed"],
        "revision_count": result["revision_count"],
        "retrieved_contexts": result["retrieved_contexts"]
    }
