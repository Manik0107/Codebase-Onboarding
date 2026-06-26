import os
from github import Github
from github.Repository import Repository

class GitHubIngestionClient:
    def __init__(self, token: str = None):
        """Initialize the GitHub client. If no token provided, it connects anonymously (low rate limit)."""
        self.token = token or os.environ.get("GITHUB_TOKEN")
        # Handle empty string or the default template string from .env
        if self.token in ["your_github_personal_access_token_here", "", None]:
            self.client = Github()
        else:
            self.client = Github(self.token)

    def get_repo(self, repo_name: str) -> Repository:
        """Fetch a repository object."""
        return self.client.get_repo(repo_name)

    def fetch_repo_structure(self, repo_name: str, path: str = ""):
        """Fetch the current file structure of the repository at the given path."""
        repo = self.get_repo(repo_name)
        try:
            contents = repo.get_contents(path)
            # If it's a single file instead of a list, wrap it
            if not isinstance(contents, list):
                contents = [contents]
                
            result = []
            for content_file in contents:
                result.append({
                    "name": content_file.name,
                    "path": content_file.path,
                    "type": content_file.type,
                    "size": content_file.size
                })
            return result
        except Exception:
            return []

    def fetch_commits(self, repo_name: str, limit: int = None):
        """Fetch commits from the repository including code changes."""
        repo = self.get_repo(repo_name)
        commits_paginated = repo.get_commits()
        
        result = []
        for i, commit in enumerate(commits_paginated):
            if limit is not None and i >= limit:
                break
                
            files_changed = []
            # fetch files changed for this commit
            if commit.files:
                for f in commit.files:
                    files_changed.append({
                        "filename": f.filename,
                        "status": f.status,
                        "additions": f.additions,
                        "deletions": f.deletions,
                        "patch": f.patch if hasattr(f, 'patch') else ""
                    })
                    
            result.append({
                "sha": commit.sha,
                "author": commit.commit.author.name if commit.commit.author else "Unknown",
                "message": commit.commit.message,
                "date": commit.commit.author.date.isoformat() if commit.commit.author else None,
                "files_changed": files_changed
            })
        return result

    def fetch_prs(self, repo_name: str, limit: int = None, state: str = "closed"):
        """Fetch pull requests including code changes."""
        repo = self.get_repo(repo_name)
        prs_paginated = repo.get_pulls(state=state, sort="updated", direction="desc")
        
        result = []
        for i, pr in enumerate(prs_paginated):
            if limit is not None and i >= limit:
                break
                
            files_changed = []
            for f in pr.get_files():
                files_changed.append({
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "patch": f.patch if hasattr(f, 'patch') else ""
                })
                
            result.append({
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "user": pr.user.login,
                "body": pr.body,
                "merged": pr.is_merged(),
                "files_changed": files_changed
            })
        return result
