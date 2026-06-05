from crewai import Agent, Crew, Process, Task
from prtool.tools.semgrep_tool import SemgrepScanTool
from prtool.tools.merge_sim_tool import MergeSimTool
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding
from crewai import LLM
import os

@CrewBase
class PrToolCrew():

    _groq_model       = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
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
    tasks_config  = 'config/tasks.yaml'

    # ------------------------------------------------------------------
    # Agents — 6 total
    # Removed: scout (replaced by _detect_tech_stack() in api.py)
    #          simulation_engineer (overlapped with diff_reviewer/verifier)
    # Added:   merge_sim_engineer (git merge simulation)
    # ------------------------------------------------------------------

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
            max_iter=2,
            max_retry_limit=1,
            verbose=True,
        )

    @agent
    def merge_sim_engineer(self) -> Agent:
        return Agent(
            config=self.agents_config['merge_sim_engineer'],
            llm=self.llm_groq,
            tools=[MergeSimTool()],
            max_iter=2,
            max_retry_limit=1,
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
            llm=self.llm_groq,
            verbose=True,
        )