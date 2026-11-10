"""可复现 CLI 和评测入口测试。"""

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from giim_agent.eval import checks
from giim_agent.runtime import ask


def test_cli_demo_and_refusal(tmp_path):
    command = [
        sys.executable,
        "-m",
        "giim_agent",
        "ask",
        "What happened at the AI laboratory?",
        "--demo",
        "--json",
        "--trace",
        "--trace-dir",
        str(tmp_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer["verified"] and answer["mode"] == "fake" and len(answer["claims"]) == 3
    command[4] = "Unknown unicorn stock price"
    result = subprocess.run(command, capture_output=True, text=True, timeout=15)
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "insufficient_evidence"


async def test_evaluation_case_checks(settings):
    data = yaml.safe_load((Path(__file__).parents[1] / "evals/questions.yaml").read_text())
    assert len(data["questions"]) >= 20
    assert len({row["category"] for row in data["questions"]}) == 8
    case = data["questions"][0]
    evidence = []
    answer = await ask(case["question"], settings=settings, trace_dir=None, evidence_sink=evidence)
    assert all(checks(case, answer, evidence).values())
    evidence[0]["url"] = "https://wrong.example.org"
    assert checks(case, answer, evidence)["citation_associations"] is False


def test_official_adk_cli_only_exposes_final_answer(tmp_path):
    env = dict(os.environ, GIIM_ADK_DEMO="1", GIIM_ADK_LIVE="0", GIIM_TRACE_DIR=str(tmp_path))
    app = Path(__file__).parents[1] / "adk_app/giim_analyst"
    result = subprocess.run(
        [
            "adk",
            "run",
            "--session_service_uri",
            "memory://",
            "--artifact_service_uri",
            "memory://",
            "--memory_service_uri",
            "memory://",
            "--log_level",
            "error",
            str(app),
            "AI laboratory",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert '"verified":true' in result.stdout
    assert '"author":"writer"' not in result.stdout


def test_adk_web_local_session_roundtrip(tmp_path):
    import socket
    import time
    import httpx

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    app_dir = Path(__file__).parents[1] / "adk_app"
    env = dict(os.environ, GIIM_ADK_DEMO="1", GIIM_ADK_LIVE="0", GIIM_TRACE_DIR=str(tmp_path))
    process = subprocess.Popen(
        [
            "adk",
            "web",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--session_service_uri",
            "memory://",
            "--artifact_service_uri",
            "memory://",
            "--memory_service_uri",
            "memory://",
            "--log_level",
            "error",
            str(app_dir),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=20, trust_env=False
        ) as client:
            for _ in range(100):
                try:
                    if client.get("/list-apps").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            assert "giim_analyst" in client.get("/list-apps").json()
            session = client.post("/apps/giim_analyst/users/test-user/sessions", json={})
            assert session.status_code == 200
            result = client.post(
                "/run",
                json={
                    "appName": "giim_analyst",
                    "userId": "test-user",
                    "sessionId": session.json()["id"],
                    "newMessage": {"role": "user", "parts": [{"text": "AI laboratory"}]},
                },
            )
            assert result.status_code == 200, result.text
            texts = [
                p["text"]
                for event in result.json()
                for p in (event.get("content") or {}).get("parts", [])
                if "text" in p
            ]
            final = json.loads(texts[-1])
            assert final["verified"] and len(final["claims"]) == 3
            assert all(event.get("author") != "writer" for event in result.json())
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
