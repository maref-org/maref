import os
import re
import json
import argparse
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

try:
    from github import Github, GithubException
    from github.Issue import Issue
except ImportError:
    raise ImportError(
        "PyGitHub is required. Install with: pip install pygithub"
    )


TODO_PATTERNS = [
    r"#\s*(TODO|FIXME|HACK|XXX)\s*[:-]?\s*(.+)",
    r"//\s*(TODO|FIXME|HACK|XXX)\s*[:-]?\s*(.+)",
    r"<!--\s*(TODO|FIXME|HACK|XXX)\s*[:-]?\s*(.+?)\s*-->",
]

SKIP_DIRS = {"__pycache__", ".git", "node_modules", "dist", "build", ".eggs"}


class CodeScanner:
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path

    def scan_todos(self) -> List[Dict]:
        todos = []
        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for file in files:
                if file.endswith((".py", ".ts", ".tsx", ".md")):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, self.repo_path)
                    todos.extend(self._scan_file(rel_path))
        return todos

    def _scan_file(self, rel_path: str) -> List[Dict]:
        todos = []
        try:
            with open(os.path.join(self.repo_path, rel_path), "r", encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError):
            return todos

        for idx, line in enumerate(lines, 1):
            for pattern in TODO_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    todos.append({
                        "file": rel_path,
                        "line": idx,
                        "type": match.group(1).upper(),
                        "text": match.group(2).strip(),
                    })
        return todos


class GoodFirstIssueGenerator:
    DIFFICULTY_MAP = {
        "FIXME": "1 - Easy (1-2 hours)",
        "TODO": "2 - Medium (3-4 hours)",
        "HACK": "3 - Intermediate (1 day)",
        "XXX": "2 - Medium (3-4 hours)",
    }

    MODULE_MAP = {
        "loop": "maref.loop",
        "governance": "maref.governance",
        "security": "maref.security",
        "evolution": "maref.evolution",
        "sidecar": "sidecar",
        "desktop": "maref.desktop",
        "lite": "maref_lite",
        "research": "research",
    }

    def __init__(self, gh: Github, repo_name: str):
        self.gh = gh
        self.repo = gh.get_repo(repo_name)

    def generate_issue(self, todo: Dict) -> Optional[Issue]:
        module = "maref"
        for key, value in self.MODULE_MAP.items():
            if key in todo["file"].lower():
                module = value
                break

        title = f"[Good First Issue] {todo['text'][:50]}..." if len(todo["text"]) > 50 else f"[Good First Issue] {todo['text']}"

        body = f"""## Description
{todo['text']}

## Steps to Complete
1. Locate the code at the specified file and line
2. Understand the context of the TODO/FIXME
3. Implement the fix or complete the task
4. Write or update tests
5. Verify the change works correctly

## Code Anchor
- {todo['file']}:{todo['line']}

## Hints
- Check existing tests for patterns
- See CONTRIBUTING.md for coding standards
"""

        labels = ["good-first-issue", "triage"]

        try:
            issue = self.repo.create_issue(
                title=title,
                body=body,
                labels=labels,
            )
            return issue
        except GithubException as e:
            print(f"Failed to create issue: {e}")
            return None


class DiscussionPublisher:
    GRAPHQL_API = "https://api.github.com/graphql"

    def __init__(self, token: str, repo_name: str):
        self.token = token
        self.repo_name = repo_name

    def _get_category_id(self) -> Optional[str]:
        query = """
        query($owner: String!, $name: String!) {
            repository(owner: $owner, name: $name) {
                discussionCategories(first: 10) {
                    nodes { id, name }
                }
            }
        }
        """
        owner, name = self.repo_name.split("/")
        variables = {"owner": owner, "name": name}

        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            self.GRAPHQL_API,
            json={"query": query, "variables": variables},
            headers=headers,
        )
        if response.status_code != 200:
            print(f"Failed to get category: {response.text}")
            return None

        data = response.json()
        categories = data.get("data", {}).get("repository", {}).get(
            "discussionCategories", {}
        ).get("nodes", [])

        for cat in categories:
            if cat.get("name") == "Announcements":
                return cat.get("id")
        if categories:
            return categories[0].get("id")
        return None

    def publish_weekly_report(self, todos: List[Dict], issues: List[Issue]) -> bool:
        category_id = self._get_category_id()
        if not category_id:
            print("Skipping discussion creation: no category found")
            return False

        today = datetime.now()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        title = f"📅 Weekly Report: {week_start.strftime('%Y-%m-%d')} - {week_end.strftime('%Y-%m-%d')}"

        todo_summary = "\n".join([
            f"- [{t['type']}] {t['file']}:{t['line']} - {t['text'][:40]}..."
            for t in todos[:10]
        ])

        issue_summary = "\n".join([
            f"- #{i.number}: {i.title}"
            for i in issues[:10]
        ])

        body = f"""## 🔍 Weekly Overview

Welcome to the MAREF weekly report! Here's what's been happening:

## 📋 New TODOs Discovered ({len(todos)})
{todo_summary if todos else "No new TODOs found this week."}

## 🚀 New Good First Issues ({len(issues)})
{issue_summary if issues else "No new issues created this week."}

## 💡 How to Contribute
1. Check out our [Good First Issues](https://github.com/{self.repo_name}/issues?q=is%3Aopen+is%3Aissue+label%3Agood-first-issue)
2. Read [CONTRIBUTING.md](CONTRIBUTING.md)
3. Join the discussion!

---
*This report was automatically generated by MAREF GitHub Agent*
"""

        mutation = """
        mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
            createDiscussion(input: {
                repositoryId: $repositoryId
                categoryId: $categoryId
                title: $title
                body: $body
            }) {
                discussion { id, url }
            }
        }
        """

        owner, name = self.repo_name.split("/")
        repo_query = """
        query($owner: String!, $name: String!) {
            repository(owner: $owner, name: $name) { id }
        }
        """
        repo_response = requests.post(
            self.GRAPHQL_API,
            json={"query": repo_query, "variables": {"owner": owner, "name": name}},
            headers={"Authorization": f"Bearer {self.token}"},
        )
        if repo_response.status_code != 200:
            print(f"Failed to get repo ID: {repo_response.text}")
            return False

        repo_id = repo_response.json().get("data", {}).get("repository", {}).get("id")
        if not repo_id:
            print("Failed to get repository ID")
            return False

        variables = {
            "repositoryId": repo_id,
            "categoryId": category_id,
            "title": title,
            "body": body,
        }

        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            self.GRAPHQL_API,
            json={"query": mutation, "variables": variables},
            headers=headers,
        )

        if response.status_code == 200:
            data = response.json()
            if "errors" in data:
                print(f"GraphQL errors: {data['errors']}")
                return False
            discussion_url = data.get("data", {}).get("createDiscussion", {}).get(
                "discussion", {}
            ).get("url")
            if discussion_url:
                print(f"Created discussion: {discussion_url}")
                return True
        else:
            print(f"Failed to create discussion: {response.text}")
        return False


class GitHubAgentScheduler:
    def __init__(self, token: str, repo_name: str, repo_path: str = "."):
        self.gh = Github(token)
        self.token = token
        self.repo_name = repo_name
        self.repo_path = repo_path
        self.scanner = CodeScanner(repo_path)
        self.issue_generator = GoodFirstIssueGenerator(self.gh, repo_name)
        self.discussion_publisher = DiscussionPublisher(token, repo_name)

    def run_full_pipeline(self) -> Dict:
        print("=== MAREF GitHub Agent Pipeline ===")

        print("\n[1/3] Scanning code for TODOs...")
        todos = self.scanner.scan_todos()
        print(f"Found {len(todos)} TODOs/FIXMEs/HACKs")

        print("\n[2/3] Generating good-first-issues...")
        issues = []
        for todo in todos[:5]:
            issue = self.issue_generator.generate_issue(todo)
            if issue:
                issues.append(issue)
                print(f"Created issue: #{issue.number}")

        print("\n[3/3] Publishing weekly discussion...")
        discussion_created = self.discussion_publisher.publish_weekly_report(todos, issues)

        return {
            "todos_found": len(todos),
            "issues_created": len(issues),
            "discussion_created": discussion_created,
        }

    def scan_only(self) -> List[Dict]:
        return self.scanner.scan_todos()


def main():
    parser = argparse.ArgumentParser(description="MAREF GitHub Agent Scheduler")
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN"),
        help="GitHub personal access token",
    )
    parser.add_argument(
        "--repo",
        default="maref-org/maref",
        help="GitHub repository name (owner/repo)",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Local repository path",
    )
    parser.add_argument(
        "--mode",
        choices=["scan", "full"],
        default="scan",
        help="Run mode: scan-only or full pipeline",
    )

    args = parser.parse_args()

    if not args.token:
        print("Error: GITHUB_TOKEN environment variable is required")
        parser.print_help()
        return

    agent = GitHubAgentScheduler(args.token, args.repo, args.path)

    if args.mode == "scan":
        todos = agent.scan_only()
        print(f"Found {len(todos)} TODOs/FIXMEs/HACKs:")
        for t in todos[:10]:
            print(f"  [{t['type']}] {t['file']}:{t['line']} - {t['text']}")
    else:
        result = agent.run_full_pipeline()
        print("\n=== Pipeline Complete ===")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()