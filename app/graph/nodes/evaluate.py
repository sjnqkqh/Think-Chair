import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.graph.llm_registry import get as get_language_model
from app.graph.prompts.concepts import CONCEPT_TEMPLATES
from app.graph.prompts.phases.evaluate import EVALUATE
from app.graph.state import GraphState
from app.graph.transcript import render_transcript
from app.services.document_evaluation_service import save_document_evaluation
from app.services.evaluation_response_parser import parse_evaluation_response

logger = logging.getLogger(__name__)

async def evaluate_polish_node(state: GraphState, config: RunnableConfig) -> dict:
    new_paper = state.get("new_paper")
    if not new_paper or new_paper.get("kind") != "polish":
        logger.info(
            "evaluate_polish: skip (kind=%s)", new_paper.get("kind") if new_paper else None
        )
        return {}

    version_id = new_paper.get("version_id")
    logger.info(
        "evaluate_polish: start manuscript_id=%s version_id=%s concept=%s",
        state["manuscript_id"],
        version_id,
        state["concept"],
    )
    try:
        checklist = CONCEPT_TEMPLATES[state["concept"]]["checkpoint"]
        language_model = get_language_model(
            config["configurable"].get("model", "default")
        )
        response = await language_model.ainvoke(
            [
                SystemMessage(content=EVALUATE.text),
                SystemMessage(content=f"[컨셉별 체크리스트]\n{checklist.text}"),
                HumanMessage(
                    content=(
                        f"[대화 내역]\n{render_transcript(state['messages'])}\n\n"
                        f"[평가 대상 문서]\n{new_paper['content']}"
                    )
                ),
            ]
        )
        raw_output = (response.content or "").strip()
        parsed = parse_evaluation_response(raw_output)
        logger.info(
            "evaluate_polish: version_id=%s score=%s verdict=%s",
            version_id,
            parsed["score"],
            parsed["verdict"],
        )

        db = config["configurable"].get("db_session")
        if db is not None:
            save_document_evaluation(
                db,
                state["manuscript_id"],
                version_id,
                raw_output,
                checklist.id,
                parsed,
            )
        else:
            db_factory = config["configurable"]["db_factory"]
            with db_factory() as database_session:
                save_document_evaluation(
                    database_session,
                    state["manuscript_id"],
                    version_id,
                    raw_output,
                    checklist.id,
                    parsed,
                )
        logger.info("evaluate_polish: saved evaluation version_id=%s", version_id)
    except Exception:
        logger.exception(
            "evaluate_polish: 평가 실패 version_id=%s", version_id
        )

    return {}
