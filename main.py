from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv 
import os
import httpx
import requests
from init_azure import get_agents, make_message, get_message_list, create_thread, run_agent
from contextlib import asynccontextmanager
from util import remove_source, extract_json, get_today_date
from cal_com_methods import try_to_make_an_appointment
from supabase import Client, create_client
import time
import asyncio
import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

load_dotenv()

API_KEY_360 = os.getenv("API_KEY_360")
WEBHOOK_360_URL = os.getenv("WEBHOOK_360_URL")
WEBHOOK_RENDER_URL = os.getenv("WEBHOOK_RENDER_URL")
real_estaid_agent, summary_agent, summary_thread = get_agents()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

conversations = {} 
conversation_data = {}
threads_without_summaries = {}

async def set_up_a_360_webhook():
    url = WEBHOOK_360_URL

    payload = {
        "url": WEBHOOK_RENDER_URL,
    }
    headers = {
        "D360-API-KEY": API_KEY_360,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    print("Status:", response.status_code)
    print("Response:", response.json())

    return Response(status_code=200)


# summary_update_time = 600
summary_update_time = 35

async def update_thread_summaries():
    while True:
        print("executing update thread")

        # Limit the number of threads to check so that it doesn't take up a lot of time

        for thread_id, last_message in threads_without_summaries.items():
            print("without summaries for loop")
            if time.time() - last_message > 30:
                make_summary(thread_id)
                threads_without_summaries.pop(thread_id, None)
                print("popped a thread from without summaries")
        # making a list so that the changes are not made during the iteration
        summaries = (
            supabase.table("real_estaid_summaries")
            .select("*")
            .eq("agent_id", summary_agent.id)
            .execute()).data
        
        for summary in summaries:
            print("supabase for loop")
            last_time_updated = summary["last_time_updated"]
            if time.time() - last_time_updated > summary_update_time:
                length = len(get_message_list(summary["thread_id"]))
                if length > summary["length"]:
                    make_summary(summary["thread_id"])

        await asyncio.sleep(15)
        


@asynccontextmanager
async def lifespan(app: FastAPI):
    # await set_up_a_360_webhook()

    # task = await asyncio.create_task(save_finished_threads())
    task = asyncio.create_task(update_thread_summaries())
    yield

    # cleanup on shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)
# app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

headers={"D360-API-KEY": API_KEY_360, "Content-Type": "application/json"}


@app.get("/health")
async def root():
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home():
    return "<h1>AI-D Chatbot API is running! </h1><p>Use POST /chat to talk to the bot.</p>"

@app.post("/formspree")
async def send_template_message(request: Request):
    data = await request.json()
    
    if "submission" in data:
        user_data = data["submission"]

    first_name, last_name, email, phone_number = user_data["firstName"], user_data["lastName"], user_data["email"], user_data["phone"]

    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,  
        "type": "template",
        "template": {
            "name": "start_message",  
            "language": {"code": "nl"},  
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": first_name}  # variable substitution
                    ]
                }
            ]
        }
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://waba-v2.360dialog.io/messages",
            headers=headers,
            json=payload
        )
        print(response.status_code, response.text)


    phone_number = phone_number.replace("+", "")
    thread_id = create_thread().id
    conversations[phone_number] = {"thread_id": thread_id, "first_name": first_name}
    print(conversations[phone_number]["first_name"])

    today = get_today_date()
    sys_msg = (f"System message: Vandaag is {today[0]}, {today[1]}, {today[2]}. Gebruik deze datum altijd als referentie\n\n"
    f"User: Mijn voornaam is {first_name} en mijn achternaam is {last_name}.\n Mijn email is {email} en mijn telefoonnummer is {phone_number}")

    make_message(thread_id, "assistant", sys_msg)

    threads_without_summaries[thread_id] = time.time()

    return Response(status_code=200)

        
async def send_message_to_user(phone, message):
    payload = {
        "to": f"{phone}",
        "type": "text",
        "language": "English",
        "policy": "test",
        "code": "en",
        "name": "assistant_response",
        "text": {
            "body": message
        },
        "messaging_product": "whatsapp"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://waba-v2.360dialog.io/messages",
            headers=headers,
            json=payload
        )

    return Response(status_code=200)


@app.post("/webhooks/whatsapp")
async def send_message_to_render(request: Request):
    response = await request.json()
    
    entry = response["entry"]
    changes = entry[0]["changes"]
    value = changes[0]["value"]
    if "messages" in value:
        user_message = value["messages"][0]["text"]["body"]
        phone_number = value["contacts"][0]["wa_id"]
        message_id = value["messages"][0]["id"]

        # Making sure the same message is not processed
        # (360 dialog sometimes sends POST requests to the webhook with a previously processed message)
        message_list = (
            supabase.table("real_estaid_messages")
            .select("*")
            .eq("message_id", message_id)
            .execute()
            ).data
        
        if len(message_list) != 0:
            print("skip")
            return Response(status_code=200)
        
        if phone_number not in conversations:
            thread_id = create_thread().id
            conversations[phone_number] = {"thread_id":  thread_id}
            threads_without_summaries[thread_id] = time.time()
            # Send a first message (phone number wasn't in conversations, which means a user has just started a conversation)
            # That is, the user started this conversation by contacting the bot directly without sending a form.
            today = get_today_date()
            sys_msg = f"System message: Vandaag is {today[0]}, {today[1]}, {today[2]}. Gebruik deze datum altijd als referentie."
            make_message(thread_id, "user", sys_msg)

            run_agent(thread_id, real_estaid_agent.id)
        else:
            thread_id = conversations[phone_number]["thread_id"]        

        insert_data = (
            supabase.table("real_estaid_messages")
            .insert({"message_id": message_id, "message": user_message, "thread_id": thread_id, "role": "user"})
            .execute()
            )
        
        await send_message_to_ai(thread_id, phone_number, user_message)

        
    else:
        print("no message")
        return Response(status_code=200)

    return Response(status_code=200)


async def send_message_to_ai(thread_id, phone_number, message):
    print("Sending message to AI with message: ", message)
    make_message(thread_id, "user", message)
    
    run_agent(thread_id, real_estaid_agent.id)

    messages = get_message_list(thread_id)

    for message in reversed(messages):
        if message.role == "assistant" and message.text_messages:
            message_to_insert = message.text_messages[-1].text.value
            break

    try:
        message_to_insert = extract_json(message_to_insert)

        data = try_to_make_an_appointment({"thread_id": thread_id, "message": message_to_insert})

        message_to_insert = data["message"]

    except ValueError:
        message_to_insert = remove_source(message_to_insert)


    insert_message = (
    supabase.table("real_estaid_messages")
    .insert({"message_id": None, "message": message_to_insert, "thread_id": thread_id, "role": "assistant"})
    .execute()
    )


    await send_message_to_user(phone_number, message_to_insert)

    return Response(status_code=200)


def make_summary(thread_id):
    # Get a conversation in JSON format
    message_list = (
        supabase.table("real_estaid_messages")
        .select("role, message")
        .eq("thread_id", thread_id)
        .execute()
        ).data

    conversation = "".join(f"{message['role']}: {message['message']}\n" for message in message_list)

    # Preventing from storing an empty conversation (when the user started a dialogue but didn't send anything)
    if conversation != "":

        # Make a message with conversation as value (summary agent)
        make_message(summary_thread.id, "user", conversation)

        # Pass the message onto summary agent
        run = run_agent(summary_thread.id, summary_agent.id)

        messages = get_message_list(summary_thread)
        length = len(messages)
    
        for message in reversed(messages):
             if message.role == "assistant" and message.text_messages:
                message_to_insert = message.text_messages[-1].text.value
                break
             
        message_to_insert = extract_json(message_to_insert)
        message_to_insert["thread_id"] = thread_id
        message_to_insert["length"] = length
        message_to_insert["last_time_updated"] = int(time.time())
        message_to_insert["agent_id"] = summary_agent.id

        insert_message = (
        supabase.table("real_estaid_summaries")
        .upsert({message_to_insert})
        .execute()
        )

        print(insert_message)


        
# summaries
    # update them once in a while 
        # need to check if there are new messages (length of the messages list?)

# Prompt

# make response shorter