import os,pytest
pytestmark=pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL required")
def test_hotfix3b1_database_environment_available():
 assert os.getenv("TEST_DATABASE_URL")
