import json
from typing import Callable

from app.evaluation.response_comparison_contracts import GeneratedResponse, ResponseComparisonCase
from app.evaluation.text_parsing import strip_code_fence

PromptInvoker = Callable[[str], str]


def build_baseline_prompt(case: ResponseComparisonCase) -> str:
    return f"""당신은 사용자의 글쓰기 대화를 이어가는 AI입니다.
아래 AI 질문과 사용자 답변을 보고 다음 응답을 작성하십시오.
외부 검색 자료는 없습니다. 근거가 부족하면 단정하지 말고 확인 질문으로 이어가도 됩니다.

[AI 질문]
{case.ai_question}

[사용자 답변]
{case.human_response}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"body":"다음 AI 응답","cited_source_keys":[],"cited_urls":[]}}"""


def build_grounded_prompt(case: ResponseComparisonCase) -> str:
    evidence_blocks = []
    for item in case.prepared_evidence:
        url = item.url or ""
        evidence_blocks.append(
            f"- source_key: {item.source_key}\n  url: {url}\n  title: {item.title}\n  text: {item.text}"
        )
    evidence_text = "\n".join(evidence_blocks) if evidence_blocks else "(준비된 근거 없음)"
    return f"""당신은 사용자의 글쓰기 대화를 이어가는 AI입니다.
아래 AI 질문과 사용자 답변, 준비된 근거를 보고 다음 응답을 작성하십시오.
근거·수치를 사용할 때는 cited_source_keys / cited_urls에 실제로 쓴 출처만 넣으십시오.
사용자가 직접 열어 확인할 수 있도록, 본문에 해당 페이지 주소를 그대로 넣으십시오.
근거가 부족하거나 부적절하면 단정하지 말고 확인 질문으로 이어가도 됩니다.

[AI 질문]
{case.ai_question}

[사용자 답변]
{case.human_response}

[준비된 근거]
{evidence_text}

출력은 아래 JSON 객체 하나만 출력하십시오. 코드펜스나 다른 설명을 붙이지 마십시오.
{{"body":"다음 AI 응답(사용한 페이지 주소 포함)","cited_source_keys":["사용한 source_key"],"cited_urls":["사용한 url"]}}"""


def parse_generation_response(raw_output: str) -> GeneratedResponse:
    data = json.loads(strip_code_fence(raw_output))
    if not isinstance(data, dict):
        raise ValueError("generation response must be a JSON object")
    body = data.get("body")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("body must be a non-empty string")
    cited_source_keys = data.get("cited_source_keys") or []
    cited_urls = data.get("cited_urls") or []
    if not isinstance(cited_source_keys, list) or not all(
        isinstance(item, str) for item in cited_source_keys
    ):
        raise ValueError("cited_source_keys must be a list of strings")
    if not isinstance(cited_urls, list) or not all(
        isinstance(item, str) for item in cited_urls
    ):
        raise ValueError("cited_urls must be a list of strings")
    return GeneratedResponse(
        body=body.strip(),
        cited_source_keys=tuple(cited_source_keys),
        cited_urls=tuple(cited_urls),
    )


def generate_response(*, prompt: str, invoke: PromptInvoker) -> GeneratedResponse:
    return parse_generation_response(invoke(prompt))
