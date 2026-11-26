import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.config import config
from app.database import DBSession
from app.libs.masterbrain import chat_qa_language
from app.models.chat import (
    Chat,
    ChatContext,
    ChatModel,
    ChatType,
    ChatUserMessage,
)
from app.models.project import Project
from app.models.protocol import Protocol
from app.routers.depends import CurrentUser, get_current_user
from app.routers.permission import check_user_permission
from app.services.aira_memory import (
    MEMORY_HANDLED,
    MEMORY_REQUEST,
    MemoryUpdate,
    load_for_inference,
    observe_style,
    parse_command,
    preference_prompt,
    read_memory,
    requested_style,
    update_memory,
)
from app.services.model_usage import create_usage_context
from app.services.recorder_turns import (
    RecorderTarget,
    plan_recorder_turn,
    recorder_scope,
)

from .context_inject import (
    build_current_editor_protocol_context_message,
    build_current_recorder_record_context_message,
    inject_airalogy_discussions,
    inject_airalogy_protocols,
    inject_airalogy_records,
    inject_recommended_airalogy_protocols,
)
from .file_processor import process_files, recorder_attachment_texts
from .utils import (
    build_chat_stream_error_data,
    check_model_usage,
    generate_tool_call_messages,
)

logger = logging.getLogger("app")

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


class QAChatMessageParams(BaseModel):
    chat_id: uuid.UUID | None = None
    protocol_id: uuid.UUID | None = None
    context: ChatContext
    message: ChatUserMessage
    model: ChatModel
    hub_search: bool = False
    recorder_target: RecorderTarget | None = None
    memory_disabled: bool = False
    memory_request_id: uuid.UUID | None = None


# protocol record qa chat
@router.post(
    "/qa/message",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {
                "text/event-stream": {
                    "description": "Stream of chat messages",
                },
            }
        }
    },
)
async def send_qa_chat_message(
    db_session: DBSession,
    current_user: CurrentUser,
    params: QAChatMessageParams,
) -> StreamingResponse:
    protocol: Protocol | None = None
    project: Project | None = None
    if params.protocol_id is not None:
        protocol = await Protocol.find(db_session, id=params.protocol_id)
        project = await Project.find(db_session, id=protocol.project_id)
        await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="read_protocol",
            protocol=protocol,
        )

    if params.chat_id is not None:
        chat = await Chat.find(db_session, id=params.chat_id, with_for_update=True)
        if chat.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Permission denied")
    else:
        chat = Chat(
            protocol_id=params.protocol_id,
            user_id=current_user.id,
            context={},
            messages=[],
            type=ChatType.QA,
            model=params.model.model_dump(),
            model_type=params.model.model_type.value,
            user_message_count=0,
        )
        db_session.add(chat)
        await db_session.flush()

    if project is None and chat.protocol_id is not None:
        chat_protocol = await Protocol.find(db_session, id=chat.protocol_id)
        project = await Project.find(db_session, id=chat_protocol.project_id)

    # Opting out is sticky for this conversation, including calls from old clients.
    memory_disabled = bool(
        params.memory_disabled or (chat.context or {}).get("memory_disabled")
    )
    chat.context = {**(chat.context or {}), "memory_disabled": memory_disabled}
    text = params.message.content
    previous = next((m for m in reversed(chat.messages) if m.get("role") == "user"), {})
    prior_text = previous.get("content") if not previous.get("files") else None
    last = chat.messages[-1] if chat.messages else {}
    answer = (
        last.get("content")
        if last.get("role") == "assistant" and not previous.get("files")
        else None
    )
    command = (
        parse_command(
            text,
            prior_text if isinstance(prior_text, str) else "",
            answer if isinstance(answer, str) else "",
        )
        if not params.message.files
        else None
    )
    # Observe direct style requests only in QA; attachments and Recorder fields are never signals.
    pair = (
        requested_style(text)
        if not (params.message.files or params.recorder_target or memory_disabled)
        else None
    )
    style_only = (
        not (params.message.files or params.recorder_target)
        and requested_style(text, include_once=True)
        and not any(c in text.strip().rstrip("。.!！") for c in "。！？!?\n")
    )
    if command is not None or style_only:
        chinese = any("\u4e00" <= char <= "\u9fff" for char in params.message.content)
        if style_only and command is None:
            reply = (
                "好的，这次会按你说的方式回答。"
                if chinese
                else "Understood. I’ll use that style for this conversation."
            )
            if pair and params.memory_request_id:
                state = await read_memory(db_session, current_user.id)
                if state["enabled"]:
                    await observe_style(
                        db_session,
                        current_user.id,
                        chat.id,
                        params.memory_request_id,
                        pair,
                        state["revision"],
                    )
        elif memory_disabled:
            reply = (
                "这次对话不读取或保存个人记忆，已有偏好保持不变。"
                if chinese
                else "This conversation does not read or save personal memory. Your preferences are unchanged."
            )
        elif command.get("clarify"):
            reply = (
                "想长期保留哪种回答方式？比如‘以后都分步骤回答’。"
                if chinese
                else "Which response style should I remember? For example, ‘Always use numbered steps’."
            )
        elif command.get("unsupported"):
            reply = (
                "暂未保存。当前支持回答语言、详细程度、表达格式和解释方式，例如：记住：用中文回答，简洁回答。科研事实和实验值请保存在文档或 Record 中。也可以打开‘个人记忆’管理。"
                if chinese
                else "Nothing saved. Supported preferences are language, detail, format and explanation style, for example: Remember: reply in English, be concise. Keep scientific facts and measurements in documents or Records. You can also open Personal memory."
            )
        elif params.memory_request_id is None:
            raise HTTPException(
                422, "Memory commands require a unique memory_request_id"
            )
        else:
            state = await read_memory(db_session, current_user.id)
            if not state["enabled"]:
                reply = (
                    "个人记忆已关闭，未保存。可在个人记忆设置中重新开启。"
                    if chinese
                    else "Personal memory is disabled. Nothing saved. You can enable it in memory settings."
                )
            else:
                result = await update_memory(
                    db_session,
                    current_user.id,
                    MemoryUpdate(
                        expected_revision=state["revision"],
                        request_id=params.memory_request_id,
                        **command,
                    ),
                    source="chat",
                    chat_id=chat.id,
                )
                if result.get("replayed"):
                    reply = (
                        "这条记忆指令已处理，未重复修改。"
                        if chinese
                        else "This memory command was already processed; no changes repeated."
                    )
                elif command.get("clear"):
                    reply = (
                        "已清除所有个人偏好。后续请求不再使用它们；已发送的回答和对话历史不会被删除。"
                        if chinese
                        else "All personal preferences cleared. Future requests will not use them; existing answers and chat history are not deleted."
                    )
                elif any(
                    value is None for value in command.get("changes", {}).values()
                ):
                    reply = (
                        "已忘记指定偏好。其他偏好保持不变。"
                        if chinese
                        else "The specified preference was forgotten. Other preferences are unchanged."
                    )
                else:
                    reply = (
                        "已记住你的表达偏好。"
                        if chinese
                        else "Your communication preferences are saved."
                    )
        # Do not retain commands as instructions in model history after forgetting.
        # The visible response may be descriptive; the stored history is neutral.
        chat.messages.extend(
            [
                {"role": "user", "content": text},
                {"role": "assistant", "content": reply},
            ]
            if style_only
            else [MEMORY_REQUEST.copy(), MEMORY_HANDLED.copy()]
        )
        await db_session.commit()

        async def memory_response():
            events = [
                {
                    "type": "meta",
                    "data": {
                        "chat_id": str(chat.id),
                        "memory_disabled": memory_disabled,
                        "memory_changed": True,
                    },
                },
                {
                    "type": "message",
                    "data": {
                        "index": len(chat.messages) - 1,
                        "message": {"role": "assistant", "content": reply},
                    },
                },
            ]
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            memory_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    await check_model_usage(db_session, current_user, params.model)
    if params.model.organization_model:
        chat.context = {**(chat.context or {}), "organization_model": params.model.organization_model}
    memory_state = await load_for_inference(current_user.id, disabled=memory_disabled)
    memory_meta = {
        "status": memory_state["status"],
        "keys": list(memory_state["preferences"])
        if memory_state["status"] == "used"
        else [],
        "revision": memory_state["revision"],
    }
    usage_context = create_usage_context(
        feature="chat.qa",
        user_id=current_user.id,
        lab_id=project.lab_id if project is not None else None,
        project_id=project.id if project is not None else None,
        chat_id=chat.id,
        attributes={"memory_disabled": memory_disabled},
    )

    if target := params.recorder_target:
        if not config.effective_ai_enabled:
            raise HTTPException(503, "Aira is unavailable")
        if (
            not protocol
            or not project
            or chat.protocol_id != protocol.id
            or chat.type != ChatType.QA
        ):
            raise HTTPException(409, "Conversation does not match the Recorder")
        # Recorder extraction must never see remembered values or inferred facts.
        # Its current SDK contract follows the latest message language directly.
        memory_meta = {**memory_meta, "status": "not_used", "keys": []}
        version = await recorder_scope(
            db_session, current_user, project, protocol, target
        )
        chat.model = params.model.model_dump()
        excerpts = await recorder_attachment_texts(
            db_session, params.message.files, current_user.id, usage_context
        )
        try:
            reply, focus, proposal = await plan_recorder_turn(
                chat,
                version,
                target,
                params.message.content,
                usage_context,
                attachment_texts=excerpts,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(502, "Invalid Recorder proposal") from exc
        # Recheck the user's authority after inference, before offering any mutation.
        if proposal["intent"] in ("simulate", "fill"):
            await recorder_scope(db_session, current_user, project, protocol, target)
        chat.context = {**(chat.context or {}), "recorder_focus": focus}
        chat.messages.extend(
            [params.message.model_dump(), {"role": "assistant", "content": reply}]
        )
        chat.user_message_count += 1
        await db_session.commit()

        async def recorder_response():
            events = [
                {
                    "type": "meta",
                    "data": {
                        "chat_id": str(chat.id),
                        "model": chat.model["name"],
                        "memory_disabled": memory_disabled,
                        "memory": memory_meta,
                    },
                },
                {
                    "type": "message",
                    "data": {
                        "index": len(chat.messages) - 1,
                        "message": {
                            "role": "assistant",
                            "content": reply,
                            "recorder_proposal": proposal,
                        },
                    },
                },
            ]
            for event in events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            recorder_response(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    # files
    if params.message.files is not None and len(params.message.files) > 0:
        file_tool_call_messages = await process_files(
            db_session,
            params.message.files,
            current_user.id,
            usage_context=usage_context,
        )
        chat.messages.extend(file_tool_call_messages)

    message = params.message.model_dump()
    context = params.context.model_dump(exclude_none=True)
    ephemeral_context = context.pop("ephemeral_context", {}) or {}
    editor_context_message = build_current_editor_protocol_context_message(
        ephemeral_context.get("current_editor_protocol"),
    )
    recorder_context_message = build_current_recorder_record_context_message(
        ephemeral_context.get("current_recorder_record"),
    )
    current_context_messages = [
        context_message
        for context_message in (editor_context_message, recorder_context_message)
        if context_message is not None
    ]
    current_context_message_index = len(chat.messages)
    current_context_message_count = len(current_context_messages)

    chat.model = params.model.model_dump()
    chat.model_type = params.model.model_type.value
    chat.messages.extend(current_context_messages)
    chat.messages.append(message)
    current_message_index = len(chat.messages)
    local_context = chat.context

    # inject airalogy protocols
    if context.get("inject_airalogy_protocols", {}).get("enabled", False):
        airalogy_protocol_ids = list(
            set(
                context.get("inject_airalogy_protocols", {}).get(
                    "airalogy_protocol_ids", []
                )
            ).difference(
                set(
                    local_context.get("inject_airalogy_protocols", {}).get(
                        "airalogy_protocol_ids", []
                    )
                )
            )
        )
        if len(airalogy_protocol_ids) > 0:
            protocols = await inject_airalogy_protocols(
                db_session,
                airalogy_protocol_ids,
            )
            inject_protocols_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_protocols",
                {"airalogy_protocol_ids": airalogy_protocol_ids},
                protocols,
            )
            chat.messages.extend(inject_protocols_tool_call_messages)

    # inject airalogy records
    if context.get("inject_airalogy_records", {}).get("enabled", False):
        airalogy_record_ids = list(
            set(
                context.get("inject_airalogy_records", {}).get(
                    "airalogy_record_ids", []
                )
            ).difference(
                set(
                    local_context.get("inject_airalogy_records", {}).get(
                        "airalogy_record_ids", []
                    )
                )
            )
        )
        if len(airalogy_record_ids) > 0:
            records = await inject_airalogy_records(
                db_session,
                airalogy_record_ids,
            )
            inject_records_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_records",
                {"airalogy_record_ids": airalogy_record_ids},
                records,
            )
            chat.messages.extend(inject_records_tool_call_messages)

    # inject airalogy discussions
    if (
        protocol
        and context.get("inject_airalogy_discussions", {}).get("enabled", False)
        and isinstance(message["content"], str)
    ):
        discussions = await inject_airalogy_discussions(
            db_session, protocol.id, message["content"], usage_context=usage_context
        )
        if len(discussions["airalogy_discussions"]) > 0:
            airalogy_discussion_ids = [
                d["airalogy_discussion_id"] for d in discussions["airalogy_discussions"]
            ]
            inject_discussions_tool_call_messages = generate_tool_call_messages(
                "inject_airalogy_discussions",
                {"airalogy_discussion_ids": airalogy_discussion_ids},
                discussions,
            )
            chat.messages.extend(inject_discussions_tool_call_messages)

            if "airalogy_discussion_ids" not in context["inject_airalogy_discussions"]:
                context["inject_airalogy_discussions"]["airalogy_discussion_ids"] = (
                    airalogy_discussion_ids
                )
            else:
                context["inject_airalogy_discussions"]["airalogy_discussion_ids"] = (
                    list(
                        set(
                            context["inject_airalogy_discussions"][
                                "airalogy_discussion_ids"
                            ]
                            + airalogy_discussion_ids
                        )
                    )
                )

    # inject recommended airalogy protocols
    if params.hub_search and isinstance(message["content"], str):
        recommended_protocols = await inject_recommended_airalogy_protocols(
            db_session,
            message.get("content", ""),
            usage_context=usage_context,
        )
        recommended_protocol_ids = [
            p["id"] for p in recommended_protocols.get("airalogy_protocols", [])
        ]
        inject_protocols_tool_call_messages = generate_tool_call_messages(
            "recommend_airalogy_protocols",
            {"airalogy_protocol_ids": recommended_protocol_ids},
            recommended_protocols,
        )
        chat.messages.extend(inject_protocols_tool_call_messages)

        context["inject_airalogy_protocols"] = context.get(
            "inject_airalogy_protocols", {"enabled": True, "airalogy_protocol_ids": []}
        )
        context["inject_airalogy_protocols"]["airalogy_protocol_ids"] = list(
            set(
                context["inject_airalogy_protocols"]["airalogy_protocol_ids"]
                + recommended_protocol_ids
            )
        )

    if params.model.organization_model:
        context["organization_model"] = params.model.organization_model
    chat.context = {**context, "memory_disabled": memory_disabled}

    # 创建一个新的流式响应，同时捕获内容
    async def capture_and_forward_stream():
        # 先讲 chat id 已 chunk 的方式发送
        meta_data = {
            "type": "meta",
            "data": {
                "chat_id": str(chat.id),
                "model": chat.model.get("name"),
                "memory_disabled": memory_disabled,
                "memory": memory_meta,
            },
        }
        yield f"data: {json.dumps(meta_data, ensure_ascii=False)}\n\n"

        # 发送 tool_call 的消息
        for i in range(current_message_index, len(chat.messages)):
            msg_data = {
                "type": "message",
                "data": {"index": i, "message": chat.messages[i]},
            }
            yield f"data: {json.dumps(msg_data, ensure_ascii=False)}\n\n"

        response_message_index = len(chat.messages)
        response_message = {
            "type": "message",
            "data": {
                "index": response_message_index,
                "message": {"role": "assistant", "content": ""},
            },
        }
        yield f"data: {json.dumps(response_message, ensure_ascii=False)}\n\n"

        # 获取原始的流式响应
        original_stream = chat_qa_language(
            chat=chat,
            usage_context=usage_context,
            personal_context=preference_prompt(memory_state),
        )

        full_response = ""
        try:
            async for chunk in original_stream:
                # 累积响应内容
                full_response += chunk
                # 将块转发给客户端
                chunk_message = {
                    "type": "message",
                    "data": {
                        "index": response_message_index,
                        "message": {"content": chunk},
                    },
                }
                yield f"data: {json.dumps(chunk_message, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.exception(
                "QA model stream failed for chat %s using model %s",
                chat.id,
                chat.model.get("name"),
            )
            error_event = {
                "type": "error",
                "data": build_chat_stream_error_data(
                    exc,
                    chat_id=chat.id,
                    model=chat.model.get("name"),
                ),
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        if current_context_message_count:
            del chat.messages[
                current_context_message_index : current_context_message_index
                + current_context_message_count
            ]

        chat.messages.append(
            {
                "role": "assistant",
                "content": full_response,
            }
        )
        if pair and params.memory_request_id and memory_state["enabled"]:
            try:
                async with db_session.begin_nested():
                    await observe_style(
                        db_session,
                        current_user.id,
                        chat.id,
                        params.memory_request_id,
                        pair,
                        memory_state["revision"],
                    )
            except SQLAlchemyError:
                logger.warning("Personal preference suggestion unavailable")
        chat.user_message_count += 1
        chat.updated_at = datetime.now()
        await db_session.commit()
        if pair:
            yield 'data: {"type":"meta","data":{"memory_changed":true}}\n\n'
        yield "data: [DONE]\n\n"

    # 返回新的流式响应
    return StreamingResponse(
        capture_and_forward_stream(),
        headers={"X-Accel-Buffering": "no"},
        media_type="text/event-stream",
    )
