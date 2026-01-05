from langgraph.graph import StateGraph, END
from typing import List, Dict, Any, TypedDict
from agents.router import QueryRouter
from agents.analyzer import DomainAnalyzer
from agents.auditor import ResponseAuditor
from core.vector_store import VectorStore
from core.graph_store import GraphStore
import logging

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("graph_flow")

# 定义状态类型
class AgentState(TypedDict):
    query: str
    route: Dict[str, Any]
    retrieved_contexts: List[Dict[str, Any]]
    analysis_result: Dict[str, Any]
    generated_answer: str
    audit_result: Dict[str, Any]
    audit_passed: bool
    revision_count: int

# 初始化各个模块
router = QueryRouter()
domain_analyzer = DomainAnalyzer()
auditor = ResponseAuditor()
vector_store = VectorStore()
graph_store = GraphStore()

# 定义节点函数

def router_node(state: AgentState) -> AgentState:
    """
    路由节点：将用户查询路由到不同的处理流程
    """
    # 获取用户查询
    query = state["query"]
    logger.info(f"[路由节点] 开始处理用户查询：'{query}'")
    
    # 路由查询
    logger.info(f"[路由节点] 调用路由器进行查询分类")
    route_result = router.route_query(query)
    logger.info(f"[路由节点] 查询路由结果：{route_result}")
    
    # 更新状态
    state["route"] = route_result
    state["revision_count"] = 0  # 重置修订计数
    
    logger.info(f"[路由节点] 路由完成，进入检索节点")
    return state

def retrieval_node(state: AgentState) -> AgentState:
    """
    检索节点：根据路由结果执行相应的检索策略
    """
    # 获取查询和路由信息
    query = state["query"]
    route_type = state["route"]["route_type"]
    logger.info(f"[检索节点] 开始检索 - 查询: '{query}', 路由类型: '{route_type}'")
    
    # 获取检索策略
    retrieval_strategy = router.get_retrieval_strategy(route_type)
    logger.info(f"[检索节点] 检索策略: {retrieval_strategy}")
    
    # 执行检索
    retrieved_contexts = []
    
    # 根据检索策略执行不同的检索方法
    if "exact_match" in retrieval_strategy["methods"]:
        # 精确匹配检索
        logger.info(f"[检索节点] 执行精确匹配检索")
        exact_match_results = vector_store.exact_match_search(
            query, 
            limit=retrieval_strategy["exact_match_params"]["limit"]
        )
        logger.info(f"[检索节点] 精确匹配检索到 {len(exact_match_results)} 个结果")
        retrieved_contexts.extend(exact_match_results)
    
    if "vector_search" in retrieval_strategy["methods"]:
        # 向量搜索
        logger.info(f"[检索节点] 执行向量搜索")
        vector_results = vector_store.search_similar(
            query, 
            limit=retrieval_strategy["vector_search_params"]["limit"]
        )
        logger.info(f"[检索节点] 向量搜索到 {len(vector_results)} 个结果")
        retrieved_contexts.extend(vector_results)
    
    if "graph_search" in retrieval_strategy["methods"]:
        # 图谱搜索
        logger.info(f"[检索节点] 执行图谱搜索")
        graph_depth = retrieval_strategy["graph_search_params"]["depth"]
        logger.info(f"[检索节点] 图谱搜索深度: {graph_depth}")
        
        # 2. 在图数据库中搜索相关实体和关系
        all_entities = graph_store.get_all_entities()
        all_relations = graph_store.get_all_relations()
        logger.info(f"[检索节点] 从图数据库获取到 {len(all_entities)} 个实体，{len(all_relations)} 个关系")
        logger.debug(f"[检索节点] 实体列表: {all_entities}")
        logger.debug(f"[检索节点] 关系列表: {all_relations}")
        
        # 3. 将搜索结果转换为适合生成回答的上下文格式
        # 构建上下文文本
        context_text = f"""
        图数据库中存储的实体和关系信息：
        
        实体列表：
        {', '.join(all_entities)}
        
        关系列表：
        """
        
        # 添加所有关系
        for relation in all_relations:
            context_text += f"- {relation['source']} {relation['relation']} {relation['target']}\n"
        
        # 4. 将结果添加到 retrieved_contexts
        if all_entities or all_relations:
            retrieved_context = {
                "score": 1.0,  # 固定分数
                "metadata": {
                    "file_name": "graph_database",
                    "type": "graph_data",
                    "page": 1,
                    "tier": "RED",  # 关系数据通常比较重要，标记为 RED
                    "coordinates": {
                        "x1": 0,
                        "y1": 0,
                        "x2": 0,
                        "y2": 0
                    },
                    "content": context_text
                },
                "id": "graph_data_1"
            }
            retrieved_contexts.append(retrieved_context)
            logger.info(f"[检索节点] 已将图谱数据添加到检索上下文")
    
    # 去重，避免同一上下文被多次返回
    logger.info(f"[检索节点] 检索到 {len(retrieved_contexts)} 个原始结果，开始去重")
    seen_contents = set()
    unique_contexts = []
    for ctx in retrieved_contexts:
        content_hash = hash(ctx["metadata"]["content"])
        if content_hash not in seen_contents:
            seen_contents.add(content_hash)
            unique_contexts.append(ctx)
    
    logger.info(f"[检索节点] 去重后保留 {len(unique_contexts)} 个上下文")
    for i, ctx in enumerate(unique_contexts):
        logger.info(f"[检索节点] 上下文 {i+1} - 来源: {ctx['metadata']['file_name']}, 类型: {ctx['metadata']['type']}, 分数: {ctx.get('score', 'N/A')}")
        logger.debug(f"[检索节点] 上下文 {i+1} 内容前100字符: {ctx['metadata']['content'][:100]}...")
    
    # 更新状态
    state["retrieved_contexts"] = unique_contexts
    
    logger.info(f"[检索节点] 检索完成，进入分析节点")
    return state

def analysis_node(state: AgentState) -> AgentState:
    """
    分析节点：分析检索到的上下文
    """
    # 获取查询和检索到的上下文
    query = state["query"]
    retrieved_contexts = state["retrieved_contexts"]
    logger.info(f"[分析节点] 开始分析上下文 - 查询: '{query}', 上下文数量: {len(retrieved_contexts)}")
    
    # 分析上下文
    logger.info(f"[分析节点] 调用领域分析器进行上下文分析")
    analysis_result = domain_analyzer.analyze_context(query, retrieved_contexts)
    logger.info(f"[分析节点] 上下文分析完成")
    logger.debug(f"[分析节点] 分析结果: {analysis_result}")
    
    # 更新状态
    state["analysis_result"] = analysis_result
    
    logger.info(f"[分析节点] 分析完成，进入生成节点")
    return state

def generation_node(state: AgentState) -> AgentState:
    """
    生成节点：生成回答
    """
    # 获取查询、检索到的上下文和分析结果
    query = state["query"]
    retrieved_contexts = state["retrieved_contexts"]
    analysis_result = state["analysis_result"]
    logger.info(f"[生成节点] 开始生成回答 - 查询: '{query}', 上下文数量: {len(retrieved_contexts)}")
    
    # 生成回答
    logger.info(f"[生成节点] 调用领域分析器生成回答")
    generated_answer = domain_analyzer.generate_answer(query, retrieved_contexts, analysis_result)
    logger.info(f"[生成节点] 回答生成完成，原始回答长度: {len(generated_answer)} 字符")
    logger.debug(f"[生成节点] 原始回答: {generated_answer}")
    
    # 格式化回答，添加引用
    logger.info(f"[生成节点] 格式化回答，添加引用信息")
    formatted_answer = domain_analyzer.format_answer_with_references(generated_answer, retrieved_contexts)
    logger.info(f"[生成节点] 格式化完成，最终回答长度: {len(formatted_answer)} 字符")
    logger.debug(f"[生成节点] 最终回答: {formatted_answer}")
    
    # 更新状态
    state["generated_answer"] = formatted_answer
    
    logger.info(f"[生成节点] 生成完成，进入审计节点")
    return state

def audit_node(state: AgentState) -> AgentState:
    """
    审计节点：审计生成的回答
    """
    # 获取检索到的上下文和生成的回答
    retrieved_contexts = state["retrieved_contexts"]
    generated_answer = state["generated_answer"]
    logger.info(f"[审计节点] 开始审计回答 - 上下文数量: {len(retrieved_contexts)}")
    logger.debug(f"[审计节点] 待审计回答: {generated_answer}")
    
    # 审计回答
    logger.info(f"[审计节点] 调用回答审计器进行审计")
    audit_result = auditor.audit_response(retrieved_contexts, generated_answer)
    logger.info(f"[审计节点] 审计完成，审计结果: {'通过' if audit_result['audit_passed'] else '不通过'}")
    logger.debug(f"[审计节点] 审计详细结果: {audit_result}")
    
    # 更新状态
    state["audit_result"] = audit_result
    state["audit_passed"] = audit_result["audit_passed"]
    state["revision_count"] += 1  # 增加修订计数
    
    logger.info(f"[审计节点] 审计完成，修订计数: {state['revision_count']}")
    return state

def correction_node(state: AgentState) -> AgentState:
    """
    修正节点：根据审计结果修正回答
    """
    # 获取审计结果
    audit_result = state["audit_result"]
    logger.info(f"[修正节点] 开始修正回答 - 审计结果: {'通过' if audit_result['audit_passed'] else '不通过'}")
    
    # 生成修正提示
    logger.info(f"[修正节点] 生成修正提示")
    correction_prompt = auditor.generate_correction_prompt(audit_result)
    logger.debug(f"[修正节点] 修正提示: {correction_prompt}")
    
    # 使用修正提示重新生成回答
    logger.info(f"[修正节点] 根据修正提示重新生成回答")
    corrected_answer = domain_analyzer.generate_answer(
        correction_prompt, 
        audit_result["original_contexts"], 
        {"key_information": [], "context_summary": "", "context_relations": [], "information_gaps": "无"}
    )
    logger.info(f"[修正节点] 修正回答生成完成，长度: {len(corrected_answer)} 字符")
    logger.debug(f"[修正节点] 修正后的回答: {corrected_answer}")
    
    # 格式化修正后的回答
    logger.info(f"[修正节点] 格式化修正后的回答")
    formatted_corrected_answer = domain_analyzer.format_answer_with_references(
        corrected_answer, 
        audit_result["original_contexts"]
    )
    logger.info(f"[修正节点] 修正完成，最终回答长度: {len(formatted_corrected_answer)} 字符")
    
    # 更新状态
    state["generated_answer"] = formatted_corrected_answer
    
    logger.info(f"[修正节点] 修正完成，返回审计节点")
    return state

# 定义条件函数
def should_revise(state: AgentState) -> bool:
    """
    判断是否需要重新生成回答
    
    Args:
        state: 当前状态
        
    Returns:
        是否需要重新生成
    """
    # 如果审计未通过且修订次数小于3次，则重新生成
    need_revision = not state["audit_passed"] and state["revision_count"] < 3
    logger.info(f"[条件判断] 是否需要修订: {need_revision} - 审计结果: {'通过' if state['audit_passed'] else '不通过'}, 修订次数: {state['revision_count']}/3")
    return need_revision

# 构建工作流
def build_workflow():
    """
    构建 LangGraph 工作流
    """
    logger.info("[工作流] 开始构建 LangGraph 工作流")
    
    # 创建状态图
    workflow = StateGraph(AgentState)
    logger.info("[工作流] 状态图创建完成")
    
    # 添加节点
    logger.info("[工作流] 添加节点: router, retrieve, analyze, generate, audit, correct")
    workflow.add_node("router", router_node)
    workflow.add_node("retrieve", retrieval_node)
    workflow.add_node("analyze", analysis_node)
    workflow.add_node("generate", generation_node)
    workflow.add_node("audit", audit_node)
    workflow.add_node("correct", correction_node)
    
    # 添加边
    logger.info("[工作流] 添加边: router -> retrieve -> analyze -> generate -> audit")
    workflow.add_edge("router", "retrieve")
    workflow.add_edge("retrieve", "analyze")
    workflow.add_edge("analyze", "generate")
    workflow.add_edge("generate", "audit")
    
    # 添加条件边
    logger.info("[工作流] 添加条件边: audit -> correct (if need revision) or END (if passed)")
    workflow.add_conditional_edges(
        "audit",
        should_revise,
        {
            True: "correct",  # 需要修订，进入修正节点
            False: END        # 审计通过，结束流程
        }
    )
    
    # 添加修正后的边
    logger.info("[工作流] 添加边: correct -> audit (修正后重新审计)")
    workflow.add_edge("correct", "audit")  # 修正后重新审计
    
    # 设置入口节点
    logger.info("[工作流] 设置入口节点为 router")
    workflow.set_entry_point("router")
    
    # 编译工作流
    logger.info("[工作流] 编译工作流")
    app = workflow.compile()
    
    logger.info("[工作流] 工作流构建完成")
    return app

# 运行工作流
def run_workflow(query: str) -> Dict[str, Any]:
    """
    运行工作流
    
    Args:
        query: 用户查询
        
    Returns:
        最终结果
    """
    logger.info(f"[工作流运行] ========== 开始运行工作流，处理查询: '{query}' ==========")
    
    # 构建工作流
    app = build_workflow()
    
    # 初始化状态
    logger.info("[工作流运行] 初始化工作流状态")
    initial_state = {
        "query": query,
        "route": {},
        "retrieved_contexts": [],
        "analysis_result": {},
        "generated_answer": "",
        "audit_result": {},
        "audit_passed": False,
        "revision_count": 0
    }
    logger.debug(f"[工作流运行] 初始状态: {initial_state}")
    
    # 运行工作流
    logger.info("[工作流运行] 启动工作流执行")
    result = app.invoke(initial_state)
    logger.info("[工作流运行] 工作流执行完成")
    logger.debug(f"[工作流运行] 工作流执行结果: {result}")
    
    # 格式化最终结果
    final_result = {
        "query": result["query"],
        "generated_answer": result["generated_answer"],
        "audit_passed": result["audit_passed"],
        "revision_count": result["revision_count"],
        "retrieved_contexts": result["retrieved_contexts"]
    }
    
    logger.info(f"[工作流运行] ========== 工作流运行完成 ==========")
    logger.info(f"[工作流运行] 最终结果 - 审计: {'通过' if final_result['audit_passed'] else '不通过'}, 修订次数: {final_result['revision_count']}")
    logger.debug(f"[工作流运行] 最终结果详细: {final_result}")
    
    return final_result
