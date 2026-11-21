import io
import os
import unittest
from fastapi.testclient import TestClient

from backend.app.main import app


class TestDatasetsAPI(unittest.TestCase):
    """
    Tests dataset REST endpoints under fixture mode and validation conditions.
    Rule 5: With USE_FIXTURES=1, dataset endpoints return HTTP 503 with a clear message.
    """

    @classmethod
    def setUpClass(cls):
        os.environ["USE_FIXTURES"] = "1"

    def setUp(self):
        self.client = TestClient(app)

    def test_fixture_mode_returns_503(self):
        # GET /api/datasets
        res = self.client.get("/api/datasets")
        self.assertEqual(res.status_code, 503)
        self.assertIn("live postgresql database", res.json()["detail"].lower())

        # POST /api/datasets
        file_content = io.BytesIO(b"id,name\n1,Alpha\n")
        res = self.client.post(
            "/api/datasets",
            files={"files": ("test.csv", file_content, "text/csv")},
            data={"dataset_name": "Test"}
        )
        self.assertEqual(res.status_code, 503)

        # GET /api/datasets/{id}
        res = self.client.get("/api/datasets/dummy-id")
        self.assertEqual(res.status_code, 503)

        # PATCH /api/datasets/{id}/columns
        res = self.client.patch("/api/datasets/dummy-id/columns", json={"share_samples": True})
        self.assertEqual(res.status_code, 503)

        # GET /api/datasets/{id}/preview
        res = self.client.get("/api/datasets/dummy-id/preview?table=orders")
        self.assertEqual(res.status_code, 503)

        # DELETE /api/datasets/{id}
        res = self.client.delete("/api/datasets/dummy-id")
        self.assertEqual(res.status_code, 503)


if __name__ == "__main__":
    unittest.main()
