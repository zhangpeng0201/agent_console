import sys

import openai
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

DEEPSEEK_CLIENT = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url=os.getenv('DEEPSEEK_BASE_URL')

)

GLM_CLIENT = OpenAI(
    api_key=os.getenv('GLM_API_KEY'),
    base_url=os.getenv('GLM_BASE_URL')
)

PROVIDERS = [
    {
        'client': DEEPSEEK_CLIENT,
        'private': {'model': os.getenv('DEEPSEEK_MODEL'), 'extra_body': {"thinking": {"type": "disabled"}}}
    },
    {
        'client': GLM_CLIENT,
        'private': {'model': os.getenv('GLM_MODEL')}
    }
]


class ModelUnavailableError(Exception):
    pass

def ask(messages, **overrides) -> str:
    for index, provider in enumerate(PROVIDERS):
        try:
            params = {
                'messages': messages,
                'max_tokens': 800,
                'temperature': 0,
                'timeout': 5
            }
            params.update(provider['private'], )
            params.update(overrides)
            res = provider['client'].chat.completions.create(**params)
            result = res.choices[0].message.content
            if not result or not result.strip():
                raise ValueError('模型返回了空content')
            return result
        except (openai.APIStatusError, openai.APIConnectionError, ValueError, openai.APIError) as e:
            print(f'[警告]：{str(e)}', file=sys.stderr)
            if index + 1 < len(PROVIDERS):
                print('模型切换中', file=sys.stderr)
                continue
            print(f'[警告]：所有模型均未访问成功', file=sys.stderr)
            raise ModelUnavailableError('所有模型均未访问成功') from e



