"""JSON reporter formatting results for CI/CD and programmatic usage."""

import json

from skill_atlas.models import ScanResult


class JsonReporter:
    """Renders structured JSON report."""

    def render(self, result: ScanResult, indent: int = 2) -> str:
        data = result.model_dump(
            exclude={
                "skills": {
                    "__all__": {
                        "raw_content",
                        "frontmatter",
                        "markdown_body",
                        "referenced_files",
                        "available_files",
                        "repo_files",
                        "base_dir",
                        "repo_root_dir",
                        "parse_error",
                    }
                }
            }
        )
        return json.dumps(data, indent=indent, ensure_ascii=False)
