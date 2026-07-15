import pytest

from app.services.storage.local import LocalFileStorage

pytestmark = pytest.mark.unit


def test_save_then_read_returns_same_content(tmp_path):
    # save()로 저장한 내용을 read()로 그대로 다시 읽을 수 있어야 한다.
    storage = LocalFileStorage(root=tmp_path)

    storage.save("drafts/a.md", b"hello draft")

    assert storage.read("drafts/a.md") == b"hello draft"


def test_save_creates_nested_directories(tmp_path):
    # key에 하위 디렉토리가 포함돼 있으면 필요한 폴더를 자동으로 만들어야 한다.
    storage = LocalFileStorage(root=tmp_path)

    storage.save("polishes/nested/b.md", b"content")

    assert (tmp_path / "polishes" / "nested" / "b.md").exists()


def test_delete_removes_file(tmp_path):
    # delete() 이후에는 같은 key로 read()가 실패해야 한다(파일이 실제로 지워짐).
    storage = LocalFileStorage(root=tmp_path)
    storage.save("drafts/c.md", b"to be deleted")

    storage.delete("drafts/c.md")

    with pytest.raises(FileNotFoundError):
        storage.read("drafts/c.md")


def test_delete_missing_key_does_not_raise(tmp_path):
    # 존재하지 않는 key를 delete()해도 예외 없이 조용히 넘어가야 한다.
    storage = LocalFileStorage(root=tmp_path)

    storage.delete("drafts/does-not-exist.md")
