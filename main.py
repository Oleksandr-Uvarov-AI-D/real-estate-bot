from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv 
import os
import httpx
import requests
from init_azure import get_agent, make_message, get_message_list, create_thread, run_agent
from contextlib import asynccontextmanager
from util import remove_source
from supabase import Client, create_client
import time
import asyncio

load_dotenv()

API_KEY_360 = os.getenv("API_KEY_360")
WEBHOOK_360_URL = os.getenv("WEBHOOK_360_URL")
WEBHOOK_RENDER_URL = os.getenv("WEBHOOK_RENDER_URL")
real_estaid_agent = get_agent()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

conversations = {} 

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

    return response

@asynccontextmanager
async def lifespan(app: FastAPI):
    await set_up_a_360_webhook()

    task = asyncio.create_task(save_finished_threads())
    yield

    # cleanup on shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

time_limit_user_message = 30 # 86400

async def save_finished_threads():
    while True:
        # Limit the number of threads to check so that it doesn't take up a lot of time
        threads_to_check = 4
        # making a list so that the changes are not made during the iteration
        numbers_to_remove = []

        for phone_number in conversations.keys():
            if threads_to_check == 0:
                break

            last_message_time = conversations[phone_number]["last_message_time"]

            time_now = time.time()
            if time_now - last_message_time > time_limit_user_message:
                numbers_to_remove.append(phone_number)

                send_message_to_user(phone_number, "voorbij")

                # make_summary(thread_id)

        threads_to_check -= 1
        for phone_number in numbers_to_remove:
            conversations.pop(phone_number, None)

        await asyncio.sleep(30) # 600


@app.get("/health")
async def root():
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home():
    return "<h1>AI-D Chatbot API is running! </h1><p>Use POST /chat to talk to the bot.</p>"

@app.get("/chat", response_class=HTMLResponse)
def home_chat():
    return "<h1>AI-D Chatbot API is running! </h1><p>Use POST /chat to talk to the bot.</p>"

@app.post("/formspree")
async def send_template_message(request: Request):
    data = await request.json()
    
    # for testing
    if "submission" in data:
        user_data = data["submission"]
    else:
        user_data = data
    first_name, last_name, email, phone = user_data["firstName"], user_data["lastName"], user_data["email"], user_data["phone"]

    await send_message_to_user(phone, f"Hello {first_name}")

    return {"message": "Webhook received"}


async def send_message_to_user(phone, message):
    headers={"D360-API-KEY": API_KEY_360, "Content-Type": "application/json"}

    payload = {
        "to": f"{phone}",
        "type": "text",
        "language": "English",
        "policy": "test",
        "code": "en",
        "name": "Hello",
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


@app.post("/webhooks/whatsapp")
async def send_message_to_render(request: Request):
    response = await request.json()

    entry = response["entry"]
    print(entry)
    changes = entry[0]["changes"]
    print(changes)
    value = changes[0]["value"]
    if "messages" in value:
        user_message = value["messages"][0]["text"]["body"]
        phone_number = value["contacts"][0]["wa_id"]
        message_id = value["messages"][0]["id"]

        message_list = (
        supabase.table("real_estaid_messages")
        .select("*")
        .eq("message_id", message_id)
        .execute()
        ).data

        print(message_list)

        if phone_number not in conversations:
            thread_id = create_thread().id
            conversations[phone_number] = {"thread_id": thread_id, "last_message_time": time.time(), "processed_messages": set()}
        else:
            conversations[phone_number]["last_message_time"] = time.time()
            thread_id = conversations[phone_number]["thread_id"]
        
        if message_id in conversations[phone_number]["processed_messages"]:
            print("skip")
            return
        else:
            conversations[phone_number]["processed_messages"].add(message_id)
        
        print(user_message)
        print(phone_number)

        insert_data = (
            supabase.table("real_estaid_messages")
            .insert({"message_id": message_id, "message": user_message, "bot_message": False})
            .execute()
            )
        

        message_list = (
        supabase.table("real_estaid_messages")
        .select("*")
        .eq("message_id", message_id)
        .execute()
        ).data

        print(message_list)

        await send_message_to_ai(thread_id, phone_number, user_message)
    else:
        print("no message")

    print(response)
    return response


async def send_message_to_ai(thread_id, phone_number, message):
    make_message(thread_id, "user", message)
    
    run_agent(thread_id, real_estaid_agent.id)

    messages = get_message_list(thread_id)

    for message in reversed(messages):
        if message.role == "assistant" and message.text_messages:
            message_to_insert = message.text_messages[-1].text.value
            break

    message_to_insert = remove_source(message_to_insert)

    response = (
    supabase.table("real_estaid_messages")
    .insert({"message_id": None, "message": message_to_insert, "bot_message": True})
    .execute()
    )


    await send_message_to_user(phone_number, message_to_insert)




# make sure AI knows what day it is today
# make sure thread is removed after 24 hours since last user's response (can test for much less time)
    # store the time when the thread was created



# Prompt

# make response shorter