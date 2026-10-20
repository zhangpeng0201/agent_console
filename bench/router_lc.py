import sys,os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from router_fc  import SYSTEM_PROMPT as PROMPT_JSON       # B1 的
from router_fc2 import SYSTEM_PROMPT as PROMPT_NEUTRAL    # B2 的
from tools import get_current_time
from schemas import RouterDecision
from tool_schema import TOOLS_SCHEMA

load_dotenv()

def _build_llm():
    llm = ChatOpenAI(
        model=os.getenv('DEEPSEEK_MODEL'),
        base_url=os.getenv('DEEPSEEK_BASE_URL'),
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        temperature=0,
        max_tokens=800,
        timeout=5,
        extra_body={'thinking':{'type':'disabled'}})

    return llm.bind_tools(TOOLS_SCHEMA, tool_choice='auto')

def _call(text: str, history: list| None, prompt):
    llm = _build_llm()
    CURRENT_DATE = get_current_time().reply.split('，')[0]
    messages = [{'role': 'system', 'content': prompt.replace('{CURRENT_DATE}', CURRENT_DATE)}] + (history or []) + [{'role': 'user', 'content': text}]
    res = llm.invoke(messages)
    return res


def route(text: str, history: list| None = None, prompt=PROMPT_JSON) -> RouterDecision:
    res = _call(text, history, prompt)
    if res.tool_calls:
        return RouterDecision(
            type='command',
            tool=res.tool_calls[0].get('name'),
            args=res.tool_calls[0].get('args'),
        )
    return RouterDecision(
        type='chat',
        tool=None,
        args={},
        text=res.content or None
    )


if __name__ == '__main__':
    res = route('记一下房间密码是123')
    print(res)