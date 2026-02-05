from crewai import Agent, Crew, Process, Task
from prtool.tools.custom_tool import Read_PR_Diff, ReadLocalPRBody, ReadLocalIssue, FormatReviewComment
from crewai.project import CrewBase, agent, crew, task
from prtool.schemas import CodeReviewReport, ReviewVerdict, IntentSummary, CodeFinding

@CrewBase
class PrToolCrew():
    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'
    @agent
    def intent_etractor(self)->Agent:
        return Agent(
            config = self.agents_config['intent_extractor'],
            tools = [ReadLocalPRBody, ReadLocalIssue],
            verbose = True
        )
    @agent
    def diff_reviewer(self)->Agent:
        return Agent(
            config = self.agents_config['diff_reviewer'],
            tools = [Read_PR_Diff],
            verbose = True
        )
    @agent
    def verifier(self)->Agent:
        return Agent(
            config = self.agents_config['verifier'],
            verbose = True
        )
    @agent
    def decider(self)->Agent:
        return Agent(
            config = self.agents_config['decider'],
            verbose = True
        )
    @agent
    def scout(self)->Agent:
        return Agent(
            config = self.agents_config['scout'],
            tools = [Read_PR_Diff],
            verbose = True
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
            verbose = True
        )
    @task
    def verification_task(self)->Task:
        return Task(
            config = self.tasks_config['verification_task'],\
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
            verbose = True
        )
