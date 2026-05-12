from crewai import Agent, Crew, Process, Task
from prtool.tools.custom_tool import FormatReviewComment
from prtool.tools.semgrep_tool import SemgrepScanTool
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding, ProjectContext
from crewai import LLM
import os

@CrewBase
class PrToolCrew():
    # Use separate providers to stay within each provider's free-tier RPM limits.

    _groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    _openrouter_model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    llm_groq = LLM(
        model=_groq_model,
        api_key=os.environ.get("GROQ_API_KEY"),
        base_url="https://api.groq.com/openai/v1",
        temperature=0.2,
    )
    llm_openrouter = LLM(
        model=_openrouter_model,
        api_key=os.environ.get("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
        temperature=0.2,
    )

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @agent
    def scout(self) -> Agent:
        return Agent(
            config=self.agents_config['scout'],
            llm=self.llm_openrouter,
            max_iter=2,
            max_retry_limit=0,
            verbose=True,
        )

    @agent
    def intent_extractor(self) -> Agent:
        return Agent(
            config=self.agents_config['intent_extractor'],
            llm=self.llm_openrouter,
            verbose=True,
        )

    @agent
    def diff_reviewer(self) -> Agent:
        return Agent(
            config=self.agents_config['diff_reviewer'],
            llm=self.llm_groq,
            verbose=True,
        )

    @agent
    def security_scanner(self) -> Agent:
        return Agent(
            config=self.agents_config['security_scanner'],
            llm=self.llm_groq,
            tools=[SemgrepScanTool()],
            max_iter=2,          # run the tool once, interpret once
            max_retry_limit=1,
            verbose=True,
        )

    @agent
    def simulation_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['simulation_engineer'],
            llm=self.llm_groq,
            verbose=True,
        )

    @agent
    def verifier(self) -> Agent:
        return Agent(
            config=self.agents_config['verifier'],
            llm=self.llm_groq,
            verbose=True,
        )

    @agent
    def decider(self) -> Agent:
        return Agent(
            config=self.agents_config['decider'],
            llm=self.llm_groq,
            verbose=True,
        )

    # ------------------------------------------------------------------
    # Tasks
    # ------------------------------------------------------------------

    @task
    def scouting_task(self) -> Task:
        return Task(
            config=self.tasks_config['scouting_task'],
            agent=self.scout(),
            output_pydantic=ProjectContext,
        )

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
            context=[self.scouting_task(), self.extraction_task()],
            verbose=True,
        )

    @task
    def security_scan_task(self) -> Task:
        return Task(
            config=self.tasks_config['security_scan_task'],
            agent=self.security_scanner(),
            # Runs independently — only needs the diff, which is in the task description.
            # No context dependencies so it can run right after scouting.
            context=[self.scouting_task()],
            verbose=True,
        )

    @task
    def simulation_task(self) -> Task:
        return Task(
            config=self.tasks_config['simulation_task'],
            agent=self.simulation_engineer(),
            context=[
                self.scouting_task(),
                self.extraction_task(),
                self.review_task(),
                self.security_scan_task(),
            ],
            verbose=True,
        )

    @task
    def verification_task(self) -> Task:
        return Task(
            config=self.tasks_config['verification_task'],
            agent=self.verifier(),
            context=[
                self.scouting_task(),
                self.extraction_task(),
                self.review_task(),
                self.security_scan_task(),
                self.simulation_task(),
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
                self.security_scan_task(),   # decider sees raw scan results directly
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
                self.scouting_task(),
                self.extraction_task(),
                self.review_task(),
                self.security_scan_task(),   # runs after scout, before simulation
                self.simulation_task(),
                self.verification_task(),
                self.decision_task(),
            ],
            process=Process.sequential,
            llm=self.llm_groq,
            verbose=True,
        )