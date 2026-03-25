from crewai import Agent, Crew, Process, Task
from prtool.tools.custom_tool import Read_PR_Diff, ReadLocalPRBody, ReadLocalIssue, FormatReviewComment
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding, ProjectContext
from crewai import LLM
import os
#from langchain_ollama import OllamaLLM

@CrewBase
class PrToolCrew():
    # Use separate providers to stay within each provider's free-tier RPM limits.
    # Your `.env` already contains the API keys; model ids are configurable too.
    _groq_model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    _cerebras_model = os.environ.get("CEREBRAS_MODEL", "llama3.1-8b")

    llm_groq = LLM(
        model=_groq_model,
        api_key=os.environ.get("GROQ_API_KEY"),
        # Groq provides an OpenAI-compatible endpoint.
        base_url="https://api.groq.com/openai/v1",
        temperature=0.2,
    )
    llm_cerebras = LLM(
        model=_cerebras_model,
        api_key=os.environ.get("CEREBRAS_API_KEY"),
        # Cerebras provides an OpenAI-compatible endpoint.
        base_url="https://api.cerebras.ai/v1",
        temperature=0.2,
    )
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'
    @agent
    def scout(self)->Agent:
        return Agent(
            config = self.agents_config['scout'],
            tools = [Read_PR_Diff()],
            llm=self.llm_cerebras,
            verbose = True
        )
    @agent
    def intent_extractor(self)->Agent:
        return Agent(
            config = self.agents_config['intent_extractor'],
            tools = [ReadLocalPRBody(), ReadLocalIssue()],
            llm=self.llm_groq,
            verbose = True
        )
    @agent
    def diff_reviewer(self)->Agent:
        return Agent(
            config = self.agents_config['diff_reviewer'],
            tools = [Read_PR_Diff()],
            llm=self.llm_groq,
            verbose = True
        )
    @agent
    def verifier(self)->Agent:
        return Agent(
            config = self.agents_config['verifier'],
            llm=self.llm_groq,
            verbose = True
        )
    @agent
    def decider(self)->Agent:
        return Agent(
            config = self.agents_config['decider'],
            llm=self.llm_groq,
            verbose = True
        )
    @task 
    def scouting_task(self)->Task:
        return Task(
            config = self.tasks_config['scouting_task'],
            output_pydantic = ProjectContext
        )
    @task
    def extraction_task(self)->Task:
        return Task(
            config = self.tasks_config['extraction_task'],
            verbose = True
        )
    @task
    def review_task(self)->Task:
        return Task(
            config = self.tasks_config['review_task'],
            context=[self.scouting_task()],
            verbose = True
        )
    @task
    def verification_task(self)->Task:
        return Task(
            config = self.tasks_config['verification_task'],
            context=[self.scouting_task(), self.extraction_task(), self.review_task()],
            output_pydantic = CodeReviewReport
        )
    @task
    def decision_task(self)->Task:
        return Task(
            config = self.tasks_config['decision_task'],
            output_pydantic = ReviewVerdict
        )

    @crew
    def crew(self)->Crew:
        return Crew(
            agents = self.agents,
            tasks = self.tasks,
            process = Process.sequential,
            llm=self.llm_groq,  # default; individual agents override this anyway
            verbose = True
        )
