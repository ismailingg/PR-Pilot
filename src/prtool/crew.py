from crewai import Agent, Crew, Process, Task
from prtool.tools.custom_tool import Read_PR_Diff, ReadLocalPRBody, ReadLocalIssue, FormatReviewComment
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding, ProjectContext
from crewai import LLM
#from langchain_ollama import OllamaLLM

@CrewBase
class PrToolCrew():
    llm = LLM(model="ollama/qwen2.5-coder:7b-instruct-q5_K_M", base_url="http://localhost:11434")
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'
    @agent
    def scout(self)->Agent:
        return Agent(
            config = self.agents_config['scout'],
            tools = [Read_PR_Diff()],
            llm=self.llm,
            verbose = True
        )
    @agent
    def intent_extractor(self)->Agent:
        return Agent(
            config = self.agents_config['intent_extractor'],
            tools = [ReadLocalPRBody(), ReadLocalIssue()],
            llm=self.llm,
            verbose = True
        )
    @agent
    def diff_reviewer(self)->Agent:
        return Agent(
            config = self.agents_config['diff_reviewer'],
            tools = [Read_PR_Diff()],
            llm=self.llm,
            verbose = True
        )
    @agent
    def verifier(self)->Agent:
        return Agent(
            config = self.agents_config['verifier'],
            llm=self.llm,
            verbose = True
        )
    @agent
    def decider(self)->Agent:
        return Agent(
            config = self.agents_config['decider'],
            llm=self.llm,
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
            llm=self.llm,
            verbose = True
        )
