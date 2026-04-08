"""Normalize LLM invoke results to plain text (str, AIMessage, content blocks)."""


def llm_result_to_text(result) -> str:
    if isinstance(result, str):
        return result
    content = getattr(result, "content", result)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
        return "".join(parts)
    return str(content)
