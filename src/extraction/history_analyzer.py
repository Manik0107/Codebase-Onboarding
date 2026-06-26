class HistoryAnalyzer:
    """
    Analyzes Git Commits to build a timeline of feature evolution.
    Extracts the author, message, and timestamp to map the 'when' and 'who' of the codebase.
    """
    def extract_timeline(self, commits):
        timeline = []
        for commit in commits:
            # We assume commit is a dict returned by our github client
            timeline.append({
                "sha": commit.get("sha"),
                "author": commit.get("author"),
                "message": commit.get("message"),
                "date": commit.get("date"),
                "files_changed_count": len(commit.get("files_changed", []))
            })
        # Sort by date
        return sorted(timeline, key=lambda x: x["date"] if x["date"] else "")
