from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


# TODO: 솔직히 무슨 소리인지 모르겠어서, 주석 유지함. 추후 딥다이브 소재로 사용 가능할듯
# AsyncSqliteSaver.from_conn_string()은 async context manager를 반환한다 (동기 SqliteSaver와 다름).w
# ChatGraphRunner가 graph.ainvoke()로 그래프를 비동기 실행하기 때문에, checkpointer도 비동기 버전이어야 한다.
# 그래서 호출부(main.py)는 `async with` 혹은 AsyncExitStack.enter_async_context()로 열어야 한다.
def make_checkpointer(path: str = "draftsmith_checkpoint.db"):
    return AsyncSqliteSaver.from_conn_string(path)
