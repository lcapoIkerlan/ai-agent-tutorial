"""A2A server: exposes the retrieval agent over JSON-RPC (A2A v1.0 and v0.3) with optional bearer auth."""

import asyncio
import hmac

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
    Part,
    Task,
    TaskState,
    TaskStatus,
)
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.agent import LLMError, answer_question
from app.config import Settings
from app.indexer import Index


class DocsAgentExecutor(AgentExecutor):
    def __init__(self, index: Index, model: str):
        self.index = index
        self.model = model

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        if context.current_task is None:  # the SDK requires a Task event before any status update
            status = TaskStatus(state=TaskState.TASK_STATE_SUBMITTED)
            await event_queue.enqueue_event(
                Task(id=context.task_id, context_id=context.context_id, status=status)
            )
        try:
            answer = await asyncio.to_thread(
                answer_question, context.get_user_input(), self.index, self.model
            )
        except LLMError as exc:
            reason = f"The LLM provider returned an error: {exc}"
            await updater.failed(updater.new_agent_message([Part(text=reason)]))
            return
        text = answer.text
        if answer.sources:
            text += "\n\nSources: " + ", ".join(answer.sources)
        await updater.add_artifact(parts=[Part(text=text)], name="answer", last_chunk=True)
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        pass


def build_app(settings: Settings, index: Index) -> Starlette:
    url = settings.public_url + "/"
    card = AgentCard(
        name=settings.agent_name,
        description=settings.agent_description,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=False, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[
            AgentSkill(
                id="answer_questions",
                name="Answer questions",
                description=settings.agent_description,
                tags=["documentation", "qa"],
            )
        ],
        supported_interfaces=[
            AgentInterface(protocol_binding="JSONRPC", protocol_version=v, url=url)
            for v in ("1.0", "0.3")
        ],
    )
    handler = DefaultRequestHandler(
        agent_executor=DocsAgentExecutor(index, settings.llm_model),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    app = Starlette(
        routes=create_agent_card_routes(card)
        + create_jsonrpc_routes(handler, rpc_url="/", enable_v0_3_compat=True)
    )

    key = settings.agent_api_key
    if key:

        async def bearer_auth(request: Request, call_next):
            if request.method == "POST":
                scheme, _, token = request.headers.get("authorization", "").partition(" ")
                if scheme.lower() != "bearer" or not hmac.compare_digest(
                    token.encode(), key.encode()
                ):
                    return PlainTextResponse("Unauthorized", status_code=401)
            return await call_next(request)

        app.add_middleware(BaseHTTPMiddleware, dispatch=bearer_auth)

    return app
