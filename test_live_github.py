import sys, os
sys.path.insert(0, os.path.abspath('AI_ESG_Platform/backend'))
from app.green.github_client import GitHubClient, GitHubClientError, get_oauth_authorize_url, exchange_oauth_code

def test_live_github():
    print("=== LIVE GITHUB VERIFICATION ===")
    
    # 1. Check OAuth configuration
    cid = os.getenv("GITHUB_CLIENT_ID")
    csec = os.getenv("GITHUB_CLIENT_SECRET")
    print(f"1. GITHUB_CLIENT_ID configured: {bool(cid)}")
    print(f"   GITHUB_CLIENT_SECRET configured: {bool(csec)}")
    url, state = get_oauth_authorize_url()
    print(f"   OAuth Authorize URL generation: SUCCESS")
    print(f"   Generated URL base: {url.split('?')[0]}")
    
    try:
        exchange_oauth_code("dummy_code_123")
    except GitHubClientError as e:
        print(f"   OAuth Exchange guard: Correctly rejected missing credentials -> {e}")

    # 2. Test live unauthenticated / public repository retrieval
    print("\n2. Testing live GitHub API connection (pallets/flask)...")
    token = os.getenv("GITHUB_TOKEN")
    print(f"   Live Personal Access Token (GITHUB_TOKEN) present: {bool(token)}")
    client = GitHubClient(token=token, demo=False)
    
    try:
        prs = client.list_pull_requests("pallets", "flask", state="open")
        print(f"   Retrieved {len(prs)} open PRs from pallets/flask")
        if prs:
            pr = prs[0]
            print(f"   Live PR #{pr['number']}: '{pr['title']}' by {pr.get('user', {}).get('login')}")
            files = client.get_pr_files("pallets", "flask", pr["number"])
            print(f"   Retrieved {len(files)} changed files from live PR #{pr['number']}")
            if files:
                f0 = files[0]
                print(f"   Sample file: {f0.get('filename')} (status: {f0.get('status')}, additions: {f0.get('additions')}, deletions: {f0.get('deletions')})")
                print(f"   Patch diff available: {bool(f0.get('patch'))}")
    except Exception as exc:
        print(f"   Live GitHub retrieval error/rate-limit: {exc}")

if __name__ == "__main__":
    test_live_github()

