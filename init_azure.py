from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder
import os
from dotenv import load_dotenv
import asyncio

load_dotenv()



credential=DefaultAzureCredential()

project = AIProjectClient(
    credential=credential,
    endpoint=os.getenv("AI_D_PROJECT_ENDPOINT")
)

estaid_agent = project.agents.get_agent(os.getenv("REAL_ESTAID_AGENT_ID"))
summary_agent = project.agents.get_agent(os.getenv("AGENT_SUMMARY_ID"))
summary_agent_thread = project.agents.threads.create()

def get_agents():
    return estaid_agent, summary_agent, summary_agent_thread


def make_message(thread_id, role, input_message):
    message = project.agents.messages.create(
    thread_id=thread_id,
    role=role,
    content=input_message)
    # print("make message successful with message", input_message)


async def get_message_list(thread_id):
    runs = list(project.agents.runs.list(thread_id=thread_id))
    if len(list(runs)) != 0:
        latest_run = list(runs)[0]
        while True:
            latest_run = project.agents.runs.get(
                thread_id=thread_id,
                run_id=latest_run.id
            )
            # if latest_run.status in ("in_progress", "queued"):
            if latest_run.status != "completed":
                print(latest_run.status, "getmsg")
                await asyncio.sleep(0.5)
            else:
                break
    messages = list(project.agents.messages.list(
        thread_id=thread_id,
        order=ListSortOrder.ASCENDING
        ))
    
    return messages

def create_thread():
    return project.agents.threads.create()
    

async def run_agent(thread_id, agent_id):
    runs = list(project.agents.runs.list(thread_id=thread_id))
    if len(list(runs)) != 0:
        latest_run = list(runs)[0]
        while True:
            latest_run = project.agents.runs.get(
                thread_id=thread_id,
                run_id=latest_run.id
            )
            # if latest_run.status in ("in_progress", "queued"):
            if latest_run.status != "completed":
                print(latest_run.status, "runagent")
                await asyncio.sleep(0.5)
            else:
                break

    run = project.agents.runs.create_and_process(
        thread_id=thread_id,
        agent_id=agent_id
    )

    return run




# length = len(get_message_list(summary_agent_thread))