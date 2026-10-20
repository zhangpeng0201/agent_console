import sys

from fastapi import FastAPI, Response
from pydantic import BaseModel
from handle import run_agent, STORE, HISTORY_LIMIT
from time import perf_counter as pc
from tools import clean_session_id, get_count, X, U
import traceback
from pathlib import Path
from fastapi.responses import FileResponse

app = FastAPI()

# 前端页面所在目录：用 __file__ 定位，不依赖启动时的工作目录
STATIC_DIR = Path(__file__).resolve().parent / 'static'


@app.get('/')
def index():
    return FileResponse(STATIC_DIR / 'index.html')


class ChatResponse(BaseModel):
    session_id: str | None
    elapsed_ms: int
    ok: bool
    reply: str
    steps: list
    error: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    text: str
    user_id: str | None = None

class ListCountResponse(BaseModel):
    user_id: str | None
    session_id: str | None
    memo_count: int
    todo_count: int
    turns: int


class HistoryMessage(BaseModel):
    role: str      # 'user' / 'assistant'
    text: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[HistoryMessage]
    truncated: bool   # 是否被 HISTORY_LIMIT 裁过（历史不完整）


@app.post('/chat')
def chat(req: ChatRequest, response: Response) -> ChatResponse:
    if req.user_id is not None:
        if clean_session_id(req.user_id) == 'default' or clean_session_id(req.user_id) != req.user_id:
            response.status_code = 400
            return ChatResponse(
                session_id=None,
                elapsed_ms=0,
                ok=False,
                reply='用户标识不合法，请刷新页面重试。',
                steps=[],
                error='invalid_user_id'
            )
    if clean_session_id(req.session_id) == 'default' or clean_session_id(req.session_id) != req.session_id:
        response.status_code = 400
        return ChatResponse(
            session_id=None,
            elapsed_ms=0,
            ok=False,
            reply='会话标识不合法，请刷新页面重试。',
            steps=[],
            error='invalid_session_id'
        )
    if not req.text.strip():
        response.status_code = 400
        return ChatResponse(
            session_id=req.session_id,
            elapsed_ms=0,
            ok=False,
            reply='发送内容不能为空。',
            steps=[],
            error='invalid_text'
        )
    try:
        start = pc()
        run = run_agent(req.text, req.session_id, req.user_id)
        end = pc()
    except Exception as e:
        print(f'[警告]：{str(e)}', file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        response.status_code = 500
        return ChatResponse(
            session_id=req.session_id,
            elapsed_ms=round((pc() - start) * 1000),
            ok=False,
            reply='服务内部出错，请稍后再试',
            steps=[],
            error='internal_error'
        )
    if not run.ok:
        response.status_code = 503
        return ChatResponse(
            session_id=req.session_id,
            elapsed_ms=round((end - start) * 1000),
            ok=False,
            reply=run.reply,
            steps=run.steps,
            error=run.error
        )
    response.status_code = 200
    return ChatResponse(
        session_id=req.session_id,
        elapsed_ms=round((end - start) * 1000),
        ok=run.ok,
        reply=run.reply,
        steps=run.steps,
        error=run.error
    )


@app.get('/state')
def state(user_id: str | None = None, session_id: str | None = None) -> ListCountResponse:
    cleaned_user_id = clean_session_id(user_id)
    cleaned_session_id = clean_session_id(session_id)
    U.set(cleaned_user_id)
    X.set(cleaned_session_id)
    if cleaned_user_id == 'default' or cleaned_user_id != user_id:
        return ListCountResponse(
            user_id='default',
            session_id='default',
            memo_count=0,
            todo_count=0,
            turns=0
        )
    if cleaned_session_id == 'default' or cleaned_session_id != session_id:
        return ListCountResponse(
            user_id=cleaned_user_id,
            session_id='default',
            memo_count=get_count('memo'),
            todo_count=get_count('todo'),
            turns=0
        )
    return ListCountResponse(
        user_id=cleaned_user_id,
        session_id=cleaned_session_id,
        memo_count=get_count('memo'),
        todo_count=get_count('todo'),
        turns=(len(STORE.get(session_id)['chat_history']) // 2 if STORE.get(session_id) else 0)
    )


@app.get('/history')
def history(session_id: str | None = None) -> HistoryResponse:
    """把某个会话的对话原文按顺序还给前端，用于刷新后恢复。

    只读 STORE 里的 chat_history（人和机器人的原文），**不读 history**
    —— history 里是给模型看的 decision JSON，直接渲染会让页面出现
    {"type": "command", ...} 这种东西。

    注意：chat_history 只有原文，没有 steps，所以恢复出来的消息
    没有决策卡。想连决策卡一起恢复，得在写入时另存 steps。
    """
    cleaned = clean_session_id(session_id)
    cell = STORE.get(cleaned)
    if not cell:
        return HistoryResponse(session_id=cleaned, messages=[], truncated=False)

    raw = cell['chat_history']
    messages = [
        HistoryMessage(role=m['role'], text=m['content'])
        for m in raw if m.get('role') in ('user', 'assistant')
    ]
    return HistoryResponse(
        session_id=cleaned,
        messages=messages,
        truncated=len(raw) >= HISTORY_LIMIT,
    )
