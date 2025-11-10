import json
import subprocess
import sys
from pathlib import Path


class RepositoryAnalyzer:
    def __init__(
        self,
        repo_root: str | None = None,
        kotlin_repo_path: str | None = None,
        github_repo: str | None = None,
        ollama_url: str = "http://127.0.0.1:11434/api/generate",
        ollama_model: str = "llama3.1:8b-instruct-q4_K_M",
    ):
        self.repo_root = Path(repo_root or Path(__file__).parent).resolve()
        self.kotlin_repo_path = Path(kotlin_repo_path).resolve() if kotlin_repo_path else None
        self.github_repo = github_repo
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.data_dir = self.repo_root / "data"
        self.raw_dir = self.data_dir / "raw"
        self.derived_dir = self.data_dir / "derived"
        self.reports_dir = self.repo_root / "reports"
        self.tools_dir = self.repo_root / "tools"
        self.dashboard_json = self.derived_dir / "dashboard.json"

    def clone_repository(self):
        subprocess.run([sys.executable, str(self.repo_root / "fetch_github.py")], check=True)

    def run_static_analysis(self):
        if self.kotlin_repo_path is None:
            raise RuntimeError("kotlin_repo_path is not set")
        detekt_script = self.repo_root / "run_detekt.sh"
        ktlint_script = self.repo_root / "run_ktlint.sh"
        subprocess.run(["bash", str(detekt_script)], cwd=self.kotlin_repo_path, check=True)
        subprocess.run(["bash", str(ktlint_script)], cwd=self.kotlin_repo_path, check=True)

    def extract_features(self):
        subprocess.run([sys.executable, str(self.repo_root / "extract_features.py")], check=True)

    def fetch_pull_requests(self):
        if not self.github_repo:
            raise RuntimeError("github_repo is not set")
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        out_json = self.raw_dir / "prs.json"
        subprocess.run(
            [
                sys.executable,
                str(self.tools_dir / "fetch_prs.py"),
                "--repo",
                self.github_repo,
                "--out",
                str(out_json),
            ],
            check=True,
        )
        return out_json

    def enrich_with_llm(self, input_json: Path):
        self.derived_dir.mkdir(parents=True, exist_ok=True)
        out_json = self.dashboard_json
        subprocess.run(
            [
                sys.executable,
                str(self.tools_dir / "enrich_semantics.py"),
                "--in",
                str(input_json),
                "--out",
                str(out_json),
                "--ollama_url",
                self.ollama_url,
                "--model",
                self.ollama_model,
            ],
            check=True,
        )
        return out_json

    def compute_risk_index(self) -> dict:
        if not self.dashboard_json.exists():
            raise FileNotFoundError(f"{self.dashboard_json} not found")
        with self.dashboard_json.open("r", encoding="utf-8") as f:
            return json.load(f)

    def run_full_analysis(self, with_static: bool = False, with_llm: bool = True) -> dict:
        self.clone_repository()
        if with_static:
            self.run_static_analysis()
        self.extract_features()
        if with_llm and self.github_repo:
            prs_file = self.fetch_pull_requests()
            self.enrich_with_llm(prs_file)
        return self.compute_risk_index()


if __name__ == "__main__":
    analyzer = RepositoryAnalyzer(
        github_repo="square/kotlinpoet",
        kotlin_repo_path=None,
    )
    result = analyzer.run_full_analysis(with_static=False, with_llm=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
