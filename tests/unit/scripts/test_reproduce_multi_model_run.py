from argparse import Namespace

from scripts.reproduce_multi_model_run import server_base_url


def test_server_base_url_uses_explicit_host_and_port():
    args = Namespace(host="127.0.0.1", port=8001)

    assert server_base_url(args) == "http://127.0.0.1:8001"
