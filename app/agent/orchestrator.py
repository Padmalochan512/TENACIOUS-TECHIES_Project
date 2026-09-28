import json
import time
from typing import Any, Dict, List, Optional

from app.config import settings
from app.agent.schemas import ChatResponse, ToolCallRecord, SourceRecord
from app.agent.guardrails import check_input_guardrails, filter_agent_output
from app.agent.memory import session_memory
from app.agent.tools import tool_executor, AVAILABLE_TOOLS_SPEC
from app.agent.prompts import SYSTEM_INSTRUCTION
from app.llm import get_llm_client
from app.llm.base import LLMClient
from app.observability.logging import logger
from app.observability.tracing import trace_manager

class AgentOrchestrator:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._custom_llm_client = llm_client

    def get_client(self) -> LLMClient:
        return self._custom_llm_client or get_llm_client()

    def process_chat(
        self,
        message: str,
        customer_id: str = "CUST-001",
        session_id: Optional[str] = None
    ) -> ChatResponse:
        start_time = time.time()
        session_id = session_memory.get_or_create_session(session_id, customer_id)
        
        # Start trace
        trace = trace_manager.start_trace(
            session_id=session_id,
            customer_id=customer_id,
            input_message=message
        )
        trace_id = trace.trace_id

        # 1. Input Guardrails
        is_safe, refusal = check_input_guardrails(message)
        if not is_safe:
            trace_manager.record_event(trace_id, "guardrail_refusal", {"reason": "prompt_injection_pattern"})
            trace_manager.finish_trace(trace_id, reply=refusal, success=True)
            session_memory.save_message(session_id, "user", message)
            session_memory.save_message(session_id, "assistant", refusal)
            return ChatResponse(
                session_id=session_id,
                customer_id=customer_id,
                reply=refusal,
                sources=[],
                tool_calls=[],
                trace_id=trace_id
            )

        # 2. Session Memory - Save user message & load context
        session_memory.save_message(session_id, "user", message)
        conversation_history = session_memory.get_recent_messages(session_id)

        # Format messages for LLM
        llm_messages = []
        for msg in conversation_history:
            llm_messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        tool_calls_executed: List[ToolCallRecord] = []
        sources_collected: List[SourceRecord] = []
        last_tool_data: Optional[Dict[str, Any]] = None
        
        client = self.get_client()
        final_reply = ""
        loop_count = 0
        max_loops = settings.max_tool_calls

        # 3. Agent Execution Loop
        while loop_count < max_loops:
            # Check timeout
            elapsed = time.time() - start_time
            if elapsed > settings.agent_timeout_seconds:
                logger.warning(f"Agent execution timeout exceeded ({elapsed:.2f}s > {settings.agent_timeout_seconds}s)")
                final_reply = "I apologize, but processing your request timed out. Please try again or reach out to support."
                break

            loop_count += 1
            trace_manager.record_event(trace_id, f"agent_loop_step_{loop_count}", {"messages_count": len(llm_messages)})

            try:
                response = client.chat(
                    messages=llm_messages,
                    tools=AVAILABLE_TOOLS_SPEC,
                    system_instruction=SYSTEM_INSTRUCTION
                )
            except Exception as e:
                logger.error(f"LLM chat generation error on step {loop_count}: {e}", exc_info=True)
                final_reply = "I am currently experiencing technical difficulties communicating with our assistant service. Please try again shortly."
                break

            # If LLM decides to call tools
            if response.tool_calls:
                # Helper to execute a single tool call safely
                def _run_tool(tcall_item):
                    fn_item = tcall_item.get("function", {})
                    t_name = fn_item.get("name")
                    raw_a = fn_item.get("arguments", "{}")
                    if isinstance(raw_a, str):
                        try:
                            p_args = json.loads(raw_a)
                        except Exception:
                            p_args = {}
                    else:
                        p_args = raw_a or {}
                    t_res = tool_executor.execute_tool(
                        tool_name=t_name,
                        arguments=p_args,
                        customer_id=customer_id
                    )
                    return t_name, p_args, t_res

                # Execute concurrently if multiple tool calls, else sequentially
                if len(response.tool_calls) > 1:
                    from concurrent.futures import ThreadPoolExecutor
                    with ThreadPoolExecutor(max_workers=min(len(response.tool_calls), 4)) as pool:
                        executed_results = list(pool.map(_run_tool, response.tool_calls))
                else:
                    executed_results = [_run_tool(response.tool_calls[0])]

                for tool_name, parsed_args, tool_result in executed_results:
                    last_tool_data = tool_result

                    # Collect sources if KB search
                    if tool_name == "search_knowledge_base" and "results" in tool_result:
                        for chunk in tool_result["results"]:
                            sources_collected.append(SourceRecord(
                                source_file=chunk.get("source_file", ""),
                                section=chunk.get("section", ""),
                                last_updated=chunk.get("last_updated"),
                                score=chunk.get("score")
                            ))

                    tool_record = ToolCallRecord(
                        tool_name=tool_name,
                        args=parsed_args,
                        result=tool_result,
                        error=tool_result.get("error") if isinstance(tool_result, dict) else None
                    )
                    tool_calls_executed.append(tool_record)

                    # Feed tool output back into message stream
                    llm_messages.append({
                        "role": "tool",
                        "name": tool_name,
                        "content": json.dumps(tool_result)
                    })

                # Continue next iteration of loop to let LLM summarize/answer
                continue

            else:
                # LLM produced a final text answer
                final_reply = response.text or ""
                break

        # If hit loop limit
        if loop_count >= max_loops and not final_reply:
            logger.warning(f"Agent reached MAX_TOOL_CALLS limit ({max_loops}) for session {session_id}")
            final_reply = "I've reached the maximum number of tool operations for this single request. Please clarify your request if you need additional help."

        # 4. Output Guardrails
        safe_reply = filter_agent_output(final_reply, current_customer_id=customer_id)

        # 5. Persist Assistant Reply in Memory
        session_memory.save_message(
            session_id=session_id,
            role="assistant",
            content=safe_reply,
            tool_calls=[tc.model_dump() for tc in tool_calls_executed] if tool_calls_executed else None
        )

        # 6. Finish Trace & Return
        trace_manager.finish_trace(
            trace_id=trace_id,
            reply=safe_reply,
            tool_calls=[tc.model_dump() for tc in tool_calls_executed],
            sources=[src.model_dump() for src in sources_collected],
            success=True,
            token_estimate=len(safe_reply.split()) * 2 + 100
        )

        return ChatResponse(
            session_id=session_id,
            customer_id=customer_id,
            reply=safe_reply,
            sources=sources_collected,
            tool_calls=tool_calls_executed,
            tool_data=last_tool_data,
            trace_id=trace_id
        )

agent_orchestrator = AgentOrchestrator()
