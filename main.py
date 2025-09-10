from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv 
import os
import httpx
import requests
from init_azure import get_agent, make_message, get_message_list, create_thread, run_agent
from contextlib import asynccontextmanager

load_dotenv()

API_KEY_360 = os.getenv("API_KEY_360")
WEBHOOK_360_URL = os.getenv("WEBHOOK_360_URL")
WEBHOOK_RENDER_URL = os.getenv("WEBHOOK_RENDER_URL")
real_estaid_agent = get_agent()

conversations = {} 

def set_up_a_360_webhook():
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    await set_up_a_360_webhook()
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


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

    # print(first_name, last_name, email, phone)

    await send_message_to_user(phone, f"Hello {first_name}")

    # payload = {"first_name": first_name, "last_name": last_name, "email": email, "phone": phone}
        
    # print(response)
    # print(response.json())

    # print(await send_message())

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

        if phone_number not in conversations:
            thread_id = create_thread().id
            conversations[phone_number] = thread_id
        else:
            thread_id = conversations[phone_number]
        
        print(user_message)
        print(phone_number)

        await send_message_to_ai(thread_id, phone_number, user_message)
    else:
        print("no message")

    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         "https://www.example.com/webhook",
    #         headers= {
    #     "Authorization": API_KEY_360
    # })
    

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


    await send_message_to_user(phone_number, message_to_insert)

