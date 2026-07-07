import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=(
        os.getenv("QWEN_API_KEY", "").strip()
        or os.getenv("DASHSCOPE_API_KEY", "").strip()
        or os.getenv("LLM_API_KEY", "").strip()
        or os.getenv("MOONSHOT_API_KEY", "").strip()
    ),
    base_url=(
        os.getenv("QWEN_BASE_URL", "").strip()
        or os.getenv("DASHSCOPE_BASE_URL", "").strip()
        or os.getenv("LLM_BASE_URL", "").strip()
        or os.getenv("MOONSHOT_BASE_URL", "").strip()
    ),
)

resp = client.chat.completions.create(
    model=(
        os.getenv("QWEN_MODEL", "").strip()
        or os.getenv("DASHSCOPE_MODEL", "").strip()
        or os.getenv("LLM_MODEL", "").strip()
        or os.getenv("MOONSHOT_MODEL", "").strip()
    ),
    messages=[
        {"role": "user", "content": "请只回复：测试成功"}
    ],
    temperature=1,
)

print(resp.choices[0].message.content)
