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
real_estaid_agent, summary_agent, summary_agent_thread = get_agents()

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

    return Response(status_code=200)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # await set_up_a_360_webhook()

    # task = await asyncio.create_task(save_finished_threads())
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

headers={"D360-API-KEY": API_KEY_360, "Content-Type": "application/json"}


async def save_finished_threads():
    while True:
        # Limit the number of threads to check so that it doesn't take up a lot of time
        threads_to_check = 4
        # making a list so that the changes are not made during the iteration
        numbers_to_remove = []

        for phone_number in conversations.keys():
            print("cleaning up phone number ", phone_number)
            if threads_to_check == 0:
                break

            last_message_time = conversations[phone_number]["last_message_time"]

            time_now = time.time()
            if time_now - last_message_time > time_limit_user_message:
                print("phone number ran out of time", phone_number)
                numbers_to_remove.append(phone_number)
                await send_message_to_user(phone_number, "Het spijt ons, maar de tijd van het gesprek is voorbij. " +
                                "U kunt ons nogmaals contacteren als u een vraag hebt.")
            else:
                print("phone number didnt run out of time", phone_number)

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
    
    if "submission" in data:
        user_data = data["submission"]
    # for testing    
    else:
        user_data = data
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
        # return response.json()


    phone_number = phone_number.replace("+", "")
    conversations[phone_number] = {"thread_id": None, "last_message_time": None, "first_name": first_name}
    print(conversations[phone_number]["first_name"])
    return Response(status_code=200)


async def send_message_to_user(phone, message):
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
            conversations[phone_number] = {"thread_id":  None}


        if conversations[phone_number]["thread_id"] == None:
            thread_id = create_thread().id
            conversations[phone_number]["thread_id"] = thread_id
        else:
            thread_id = conversations[phone_number]["thread_id"]

        first_name = conversations[phone_number].get("first_name")
        await send_message_to_ai(thread_id, phone_number, user_message, first_name)



        conversations[phone_number]["last_message_time"] = time.time()

        insert_data = (
            supabase.table("real_estaid_messages")
            .insert({"message_id": message_id, "message": user_message, "thread_id": thread_id, "role": "user"})
            .execute()
            )
        
    else:
        print("no message")
        return Response(status_code=200)

    return Response(status_code=200)


async def send_message_to_ai(thread_id, phone_number, message, first_name=None):
    if first_name != None:
        today = get_today_date()

        sys_msg = f"System message: Vandaag is {today[0]}, {today[1]}. Gebruik deze datum altijd als referentie\n\n"
        greeting = f"User: Mijn naam is {first_name}\n"
        sys_msg += greeting
        sys_msg += message
        message = sys_msg
        
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




# 1. make sure AI knows what day it is today

# 2. make sure thread is removed after 24 hours since last user's response (can test for much less time)
    # store the time when the thread was created
    
    # right now a thread is closed after a specified time but a user doesn't get a final message

# 3. summaries


# make the bot know the name of the user
# connect cal.com


# Prompt

# make response shorter