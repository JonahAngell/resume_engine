import os,pytest
pytestmark=pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL required")
def test_phase3c_requires_disposable_postgresql(): assert os.environ["TEST_DATABASE_URL"]
