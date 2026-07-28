"""Embeddings y chat vía Foundation Models de Databricks."""
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole
from config import get_workspace_client, EMBED_ENDPOINT, CHAT_ENDPOINT


def embed(texts):
    if isinstance(texts, str):
        texts = [texts]
    w = get_workspace_client()
    resp = w.serving_endpoints.query(name=EMBED_ENDPOINT, input=texts)
    return [d["embedding"] if isinstance(d, dict) else d.embedding for d in resp.data]


def chat(system_prompt, user_prompt, max_tokens=400):
    w = get_workspace_client()
    resp = w.serving_endpoints.query(
        name=CHAT_ENDPOINT,
        messages=[
            ChatMessage(role=ChatMessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=ChatMessageRole.USER, content=user_prompt),
        ],
        max_tokens=max_tokens,
    )
    return resp.choices[0].message.content
