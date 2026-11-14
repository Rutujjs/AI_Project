"""Complete live demonstration verification script for Area 5.
Starts the FastAPI backend on port 8001 and frontend server on port 3000,
executes real HTTP requests across the complete workflow, verifies responses,
and inspects the SQLite database for physical persistence.
"""

import http.server
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error

backend_dir = r"c:\Users\poter\Downloads\AI-CP-main\AI_ESG_Platform\backend"
frontend_dir = r"c:\Users\poter\Downloads\AI-CP-main\integrated-frontend"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ESG-TestClient/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, resp.read().decode("utf-8")


def http_post(url, data_dict):
    data = json.dumps(data_dict).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "ESG-TestClient/1.0"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, resp.read().decode("utf-8")


def main():
    print("=" * 65)
    print("  AREA 5: COMPLETE LIVE FRONTEND & BACKEND DEMONSTRATION")
    print("=" * 65)

    print("\n[STEP 1] Starting backend on http://127.0.0.1:8001 and frontend on http://127.0.0.1:3000...")
    
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001", "--log-level", "warning"],
        cwd=backend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    frontend_proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "3000", "--bind", "127.0.0.1"],
        cwd=frontend_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    try:
        health_ok = False
        for attempt in range(25):
            time.sleep(0.5)
            if backend_proc.poll() is not None:
                out, err = backend_proc.communicate()
                print("Backend stdout:", out.decode("utf-8", errors="ignore"))
                print("Backend stderr:", err.decode("utf-8", errors="ignore"))
                raise RuntimeError(f"Backend process exited prematurely with code {backend_proc.returncode}")
            try:
                status, body = http_get("http://127.0.0.1:8001/green/health")
                if status == 200 and "green_software" in body:
                    health_ok = True
                    break
            except Exception:
                pass

        assert health_ok, "Backend failed to start or did not respond healthy on port 8001"
        print("  --> Backend is healthy on port 8001 (GET /green/health -> 200 OK)")

        # 2. Test Frontend Server
        print("\n[STEP 2] Verifying frontend static asset delivery...")
        status, html_content = http_get("http://127.0.0.1:3000/green-code.html")
        assert status == 200
        assert "Green Code Intelligence" in html_content
        assert "js/green-code.js" in html_content
        assert "js/api.js" in html_content
        print("  --> Frontend served green-code.html successfully (Status 200, length:", len(html_content), "bytes)")

        status_js, js_content = http_get("http://127.0.0.1:3000/js/green-code.js")
        assert status_js == 200
        assert "Green Code Intelligence — Full Frontend Module" in js_content
        print("  --> Frontend served js/green-code.js successfully (Status 200, length:", len(js_content), "bytes)")

        # 3. Connect GitHub (Demo Mode)
        print("\n[STEP 3] Connecting GitHub account via POST /green/github/connect...")
        status, resp_text = http_post("http://127.0.0.1:8001/green/github/connect", {"demo": True})
        assert status == 200, f"Connect failed: {resp_text}"
        account = json.loads(resp_text)
        account_id = account["id"]
        print(f"  --> Connected account #{account_id}: '{account['username']}' (is_demo={account['is_demo']})")

        # 4. List Connected Accounts
        print("\n[STEP 4] Retrieving connected accounts via GET /green/github/accounts...")
        status, resp_text = http_get("http://127.0.0.1:8001/green/github/accounts")
        assert status == 200
        accounts = json.loads(resp_text)
        assert any(a["id"] == account_id for a in accounts)
        print(f"  --> Retrieved {len(accounts)} connected account(s)")

        # 5. List Repositories
        print(f"\n[STEP 5] Retrieving repositories for account #{account_id} via GET /green/github/accounts/{account_id}/repositories...")
        status, resp_text = http_get(f"http://127.0.0.1:8001/green/github/accounts/{account_id}/repositories")
        assert status == 200
        repos = json.loads(resp_text)
        assert len(repos) > 0, "No repositories returned"
        selected_repo = repos[0]
        repo_id = selected_repo["id"]
        print(f"  --> Retrieved {len(repos)} repo(s). Selected repo #{repo_id}: '{selected_repo['full_name']}'")

        # 6. List Pull Requests
        print(f"\n[STEP 6] Retrieving pull requests for repo #{repo_id} via GET /green/github/repositories/{repo_id}/pulls...")
        status, resp_text = http_get(f"http://127.0.0.1:8001/green/github/repositories/{repo_id}/pulls?state=open")
        assert status == 200
        prs = json.loads(resp_text)
        assert len(prs) > 0, "No pull requests returned"
        selected_pr = prs[0]
        pr_number = selected_pr["pr_number"]
        print(f"  --> Retrieved {len(prs)} PR(s). Selected PR #{pr_number}: '{selected_pr['title']}' by {selected_pr['author']}")

        # 7. Select PR Details & Changed Files
        print(f"\n[STEP 7] Inspecting PR details and changed files via GET /green/github/repositories/{repo_id}/pulls/{pr_number}...")
        status, resp_text = http_get(f"http://127.0.0.1:8001/green/github/repositories/{repo_id}/pulls/{pr_number}")
        assert status == 200
        pr_details = json.loads(resp_text)
        files = pr_details.get("files", [])
        print(f"  --> PR #{pr_number} contains {len(files)} changed file(s):")
        for f in files[:3]:
            print(f"      - {f['filename']} (+{f['additions']}/-{f['deletions']})")

        # 8. Run Analysis
        print(f"\n[STEP 8] Running Green Code Analysis via POST /green/analysis/analyze...")
        status, resp_text = http_post("http://127.0.0.1:8001/green/analysis/analyze", {
            "repository_id": repo_id,
            "pr_number": pr_number
        })
        assert status == 200, f"Analysis failed: {resp_text}"
        analysis = json.loads(resp_text)
        score_data = analysis["score"]
        findings = analysis["findings"]
        print(f"  --> Analysis Complete!")
        print(f"      Overall Green Code Score: {score_data['overall_score']} / 100")
        print(f"      Findings Count: {score_data['finding_count']} (High: {score_data['high_priority_count']}, Med: {score_data['medium_priority_count']}, Low: {score_data['low_priority_count']})")
        print(f"      Dimension Scores:")
        for dim, val in score_data.get("dimensions", {}).items():
            print(f"        * {dim.capitalize()}: {val}")
        print(f"      Detected Findings: {len(findings)}")
        for i, finding in enumerate(findings[:3], 1):
            print(f"        Finding #{i}: [{finding['severity'].upper()}] {finding['rule_id']} in {finding['file_path']}:{finding['line_start']}")
            print(f"          Problem: {(finding['problem'] or '')[:75]}...")
            print(f"          Resource Impact: {(finding['resource_impact'] or '')[:75]}...")
            print(f"          Recommendation: {(finding['recommendation'] or '')[:75]}...")
            if finding.get("before_code"):
                print(f"          Has Before/After Code Snippets: YES")

        pr_id = analysis["pull_request_id"]

        # 9. Verify Results Retrieval Endpoint
        print(f"\n[STEP 9] Verifying results retrieval via GET /green/analysis/results/{pr_id}...")
        status, resp_text = http_get(f"http://127.0.0.1:8001/green/analysis/results/{pr_id}")
        assert status == 200
        retrieved = json.loads(resp_text)
        assert retrieved["score"]["overall_score"] == score_data["overall_score"]
        assert len(retrieved["findings"]) == len(findings)
        print(f"  --> Result retrieval confirmed: Score {retrieved['score']['overall_score']}, {len(retrieved['findings'])} findings")

        # 10. Verify Scores History Endpoint
        print("\n[STEP 10] Verifying scores history via GET /green/analysis/scores...")
        status, resp_text = http_get("http://127.0.0.1:8001/green/analysis/scores")
        assert status == 200
        scores_list = json.loads(resp_text)
        assert len(scores_list) > 0
        print(f"  --> Scores history retrieved: {len(scores_list)} record(s) found")

        # 11. Verify Database Persistence in SQLite
        print("\n[STEP 11] Verifying Physical SQLite Database Persistence...")
        db_path = os.path.join(backend_dir, "green_db", "green_software.db")
        assert os.path.exists(db_path), f"Database file not found at {db_path}"

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM github_accounts WHERE id=?", (account_id,))
        count_accounts = cur.fetchone()[0]
        assert count_accounts >= 1, "github_accounts table does not contain account"

        cur.execute("SELECT COUNT(*) FROM repositories WHERE id=?", (repo_id,))
        count_repos = cur.fetchone()[0]
        assert count_repos >= 1, "repositories table does not contain repo"

        cur.execute("SELECT COUNT(*) FROM pull_requests WHERE id=?", (pr_id,))
        count_prs = cur.fetchone()[0]
        assert count_prs >= 1, "pull_requests table does not contain PR"

        cur.execute("SELECT COUNT(*) FROM code_findings WHERE pull_request_id=?", (pr_id,))
        count_findings = cur.fetchone()[0]
        assert count_findings == len(findings), "code_findings table record count mismatch"

        cur.execute("SELECT COUNT(*) FROM green_code_scores WHERE pull_request_id=?", (pr_id,))
        count_scores = cur.fetchone()[0]
        assert count_scores >= 1, "green_code_scores table does not contain score"

        cur.execute("SELECT rule_id, file_path, line_start, problem, before_code, after_code FROM code_findings WHERE pull_request_id=? LIMIT 1", (pr_id,))
        row = cur.fetchone()
        print(f"  --> SQLite row verified:")
        print(f"      Table 'github_accounts': >= 1 row")
        print(f"      Table 'repositories': >= 1 row")
        print(f"      Table 'pull_requests': >= 1 row")
        print(f"      Table 'code_findings': {count_findings} rows")
        print(f"      Table 'green_code_scores': >= 1 rows")
        print(f"      Sample persisted finding: rule='{row[0]}', file='{row[1]}', line={row[2]}")
        print(f"      Sample before_code length: {len(row[4] or '')} chars, after_code length: {len(row[5] or '')} chars")

        conn.close()

        print("\n" + "=" * 65)
        print("  ALL 11 LIVE DEMONSTRATION CHECKS PASSED SUCCESSFULLY!")
        print("=" * 65)

    finally:
        print("\n[CLEANUP] Stopping backend and frontend server processes...")
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=3)
        except Exception:
            backend_proc.kill()
        try:
            frontend_proc.terminate()
            frontend_proc.wait(timeout=3)
        except Exception:
            frontend_proc.kill()
        print("  --> Server processes terminated.")


if __name__ == "__main__":
    main()
