"""
Load Testing with Locust — Simulates concurrent user traffic.

Run locally:
  locust -f tests/load/locustfile.py --host=http://localhost:8000

Run headless (CI):
  locust -f tests/load/locustfile.py --host=http://localhost:8000 \
    --headless -u 50 -r 5 -t 60s --csv=load_results

Target: 100 concurrent users, <500ms p95 response time
"""

import random
import string

from locust import HttpUser, between, task


def random_user_id():
    return f"loadtest.{''.join(random.choices(string.ascii_lowercase, k=6))}"


class ChatbotUser(HttpUser):
    """Simulates a typical chatbot user journey."""

    wait_time = between(1, 3)  # 1-3 seconds between requests
    session_id = None
    user_id = None

    def on_start(self):
        """Create session on user spawn."""
        self.user_id = random_user_id()
        self._create_session()

    def _create_session(self):
        """Create new session and select scope."""
        resp = self.client.post("/chat", json={
            "question": "hello",
            "customer_key": "demo",
            "user_id": self.user_id,
            "facility_ids": [63],
        })
        if resp.status_code == 200:
            data = resp.json()
            self.session_id = data.get("session_id")

            # Select random scope
            scope = random.choice(["inmate_data", "document_qa", "daily_activity"])
            self.client.post("/scope/select", json={
                "session_id": self.session_id,
                "scope": scope,
            })

    @task(10)
    def chat_inmate_data(self):
        """Common: Query inmate data."""
        if not self.session_id:
            return

        questions = [
            "how many notes today?",
            "show fire watch notes",
            "notes for last week",
            "top 5 officers by notes",
            "red highlighted entries",
            "show recent inmates",
        ]
        self.client.post("/chat", json={
            "question": random.choice(questions),
            "customer_key": "demo",
            "user_id": self.user_id,
            "session_id": self.session_id,
        })

    @task(3)
    def chat_document_qa(self):
        """Less common: Document search."""
        if not self.session_id:
            return

        questions = [
            "what is fire drill procedure?",
            "visitor check-in policy",
            "medical emergency steps",
        ]
        # Switch to doc scope
        self.client.post("/scope/select", json={
            "session_id": self.session_id,
            "scope": "document_qa",
        })
        self.client.post("/chat", json={
            "question": random.choice(questions),
            "customer_key": "demo",
            "user_id": self.user_id,
            "session_id": self.session_id,
        })

    @task(2)
    def refresh_daily_activity(self):
        """Occasional: Refresh daily activity."""
        if not self.session_id:
            return

        self.client.post("/scope/select", json={
            "session_id": self.session_id,
            "scope": "daily_activity",
        })

    @task(1)
    def check_health(self):
        """Rare: Health check."""
        self.client.get("/health")

    @task(1)
    def get_scope_options(self):
        """Rare: Fetch scope options."""
        self.client.get(f"/scope/options?session_id={self.session_id}")


class HealthCheckUser(HttpUser):
    """Lightweight user for health monitoring."""

    wait_time = between(5, 10)

    @task
    def health_check(self):
        self.client.get("/health")

    @task
    def pipeline_health(self):
        scope = random.choice(["inmate_data", "document_qa", "daily_activity"])
        self.client.get(f"/pipelines/health/{scope}")
