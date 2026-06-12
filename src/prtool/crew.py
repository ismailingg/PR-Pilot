from crewai import Agent, Crew, Process, Task
from prtool.tools.semgrep_tool import SemgrepScanTool
from prtool.tools.merge_sim_tool import MergeSimTool
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding
from crewai import LLM
import os

# ---------------------------------------------------------------------------
# Tier detection
# LLM_TIER controls context limits and which model handles security scanning.
#
# "free"  — Groq + OpenRouter free keys. Diff truncated to 8k chars.
#           Security scanner uses OpenRouter to avoid Groq's 12k TPM limit.
# "paid"  — Any paid key (Anthropic / OpenAI / Gemini). No truncation.
#           All agents use the configured paid model.
# "local" — Ollama running locally. No truncation, no external API calls.
# ---------------------------------------------------------------------------
LLM_TIER = os.environ.get("LLM_TIER", "free").lower()


def _make_llm(model: str, api_key: str, base_url: str) -> LLM:
    return LLM(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0.2,
    )


def _make_fallback_llm() -> LLM:
    """
    Returns a fallback LLM when the primary hits rate limits.
    Free tier: Groq primary → OpenRouter fallback.
    Paid tier: configured model, no fallback needed.
    """
    if LLM_TIER == "local":
        return _make_llm(
            model=os.environ.get("OLLAMA_MODEL", "ollama/llama3.1"),
            api_key="ollama",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
    # Free tier fallback: OpenRouter gpt-4o-mini
    return _make_llm(
        model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
        api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        base_url="https://openrouter.ai/api/v1",
    )


@CrewBase
class PrToolCrew():

    # ------------------------------------------------------------------
    # LLM setup based on tier
    # ------------------------------------------------------------------

    if LLM_TIER == "local":
        _primary = _make_llm(
            model=os.environ.get("OLLAMA_MODEL", "ollama/llama3.1"),
            api_key="ollama",
            base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        )
        _secondary = _primary   # same model for all agents locally

    elif LLM_TIER == "paid":
        _primary = _make_llm(
            model=os.environ.get("PAID_MODEL", "anthropic/claude-3-5-haiku-20241022"),
            api_key=os.environ.get("PAID_API_KEY", ""),
            base_url=os.environ.get("PAID_BASE_URL", "https://api.anthropic.com/v1"),
        )
        _secondary = _primary

    else:
        # free tier — Groq primary, OpenRouter secondary/fallback
        _primary = _make_llm(
            model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.environ.get("GROQ_API_KEY", ""),
            base_url="https://api.groq.com/openai/v1",
        )
        _secondary = _make_llm(
            model=os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            base_url="https://openrouter.ai/api/v1",
        )

    agents_config = 'config/agents.yaml'
    tasks_config  = 'config/tasks.yaml'

    # ------------------------------------------------------------------
    # Agents — 6 total
    # intent_extractor + security_scanner always use _secondary (OpenRouter)
    # to avoid Groq TPM limits on the free tier.
    # ------------------------------------------------------------------

    @agent
    def intent_extractor(self) -> Agent:
        return Agent(
            config=self.agents_config['intent_extractor'],
            llm=self._secondary,   # lightweight task, use secondary
            verbose=True,
        )

    @agent
    def diff_reviewer(self) -> Agent:
        return Agent(
            config=self.agents_config['diff_reviewer'],
            llm=self._secondary,   # OpenRouter follows complex instructions more reliably
            verbose=True,
        )

    @agent
    def security_scanner(self) -> Agent:
        return Agent(
            config=self.agents_config['security_scanner'],
            llm=self._primary,   # always on secondary — avoids 413 on Groq free tier
            tools=[SemgrepScanTool()],
            max_iter=2,
            max_retry_limit=1,
            verbose=True,
        )

    @agent
    def merge_sim_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['merge_sim_engineer'],
            llm=self._primary,
            tools=[MergeSimTool()],
            max_iter=2,
            max_retry_limit=1,
            verbose=True,
        )

    @agent
    def verifier(self) -> Agent:
        return Agent(
            config=self.agents_config['verifier'],
            llm=self._primary,
            verbose=True,
        )

    @agent
    def decider(self) -> Agent:
        return Agent(
            config=self.agents_config['decider'],
            llm=self._primary,
            verbose=True,
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task
    def extraction_task(self) -> Task:
        return Task(
            config=self.tasks_config['extraction_task'],
            agent=self.intent_extractor(),
            verbose=True,
        )

    @task
    def review_task(self) -> Task:
        return Task(
            config=self.tasks_config['review_task'],
            agent=self.diff_reviewer(),
            context=[self.extraction_task()],
            verbose=True,
        )

    @task
    def security_scan_task(self) -> Task:
        return Task(
            config=self.tasks_config['security_scan_task'],
            agent=self.security_scanner(),
            verbose=True,
        )

    @task
    def merge_sim_task(self) -> Task:
        return Task(
            config=self.tasks_config['merge_sim_task'],
            agent=self.merge_sim_engineer(),
            verbose=True,
        )

    @task
    def verification_task(self) -> Task:
        return Task(
            config=self.tasks_config['verification_task'],
            agent=self.verifier(),
            context=[
                self.extraction_task(),
                self.review_task(),
                self.security_scan_task(),
                self.merge_sim_task(),
            ],
            output_pydantic=CodeReviewReport,
        )

    @task
    def decision_task(self) -> Task:
        return Task(
            config=self.tasks_config['decision_task'],
            agent=self.decider(),
            context=[
                self.verification_task(),
                self.security_scan_task(),
                self.merge_sim_task(),
            ],
            output_pydantic=ReviewVerdict,
        )

    # ------------------------------------------------------------------
    # Crew
    # ------------------------------------------------------------------

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=[
                self.extraction_task(),
                self.review_task(),
                self.security_scan_task(),
                self.merge_sim_task(),
                self.verification_task(),
                self.decision_task(),
            ],
            process=Process.sequential,
            llm=self._primary,
            verbose=True,
        )