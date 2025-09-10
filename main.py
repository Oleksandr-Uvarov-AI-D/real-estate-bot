from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv 
import os
import httpx
import requests

load_dotenv()

API_KEY_360 = os.getenv("API_KEY_360")


app = FastAPI()

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
async def send_form(request: Request):
    # hook_secret = request.headers.get("X-Hook-Secret")

    # if hook_secret:
    #     return JSONResponse(
    #         content={"message": "Webhook verifieed"},
    #         headers={"X-Hook-Secret": hook_secret},
    #         status_code=200
    #     )

    data = await request.json()
    
    # for testing
    if "submission" in data:
        user_data = data["submission"]
    else:
        user_data = data
    first_name, last_name, email, phone = user_data["firstName"], user_data["lastName"], user_data["email"], user_data["phone"]

    print(first_name, last_name, email, phone)

    headers={"D360-API-KEY": API_KEY_360, "Content-Type": "application/json"}

    payload = {"first_name": first_name, "last_name": last_name, "email": email, "phone": phone}
#     payload= {
#    "messaging_product": "whatsapp", 
#    "recipient_type": "individual", 
#    "to": "32488161192", 
#     # "to": "32456990051",
#    "type": "text", 
#     "text":  {
#         "body": "Hello, dear customer!"
#     }
#     }

    payload = {
        "to": f"{phone}",
        "type": "text",
        "language": "English",
        "policy": "test",
        "code": "en",
        "name": "Hello",
        "text": {
            "body": f"Hello {first_name}"
        },
        "messaging_product": "whatsapp"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://waba-v2.360dialog.io/messages",
            headers=headers,
            json=payload
        )
        
    print(response)
    print(response.json())


    # url = "https://waba-v2.360dialog.io/messages"
    url = "https://waba-v2.360dialog.io/v1/configs/webhook"
    api_key = API_KEY_360

    payload = {
        # "url": "http://127.0.0.1:8000/webhooks/whatsapp",
        "url": "https://real-estate-bot-4dxy.onrender.com/webhooks/whatsapp",
        # Optional: add headers for basic auth if needed
        # "headers": {
        #     "Authorization": "Basic base64encodedUSERPASS"
        # }
    }
    headers = {
        "D360-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    response = requests.post(url, json=payload, headers=headers)
    print("Status:", response.status_code)
    print("Response:", response.json())

    # print(await send_message())

    return {"message": "Webhook received"}


@app.post("webhooks/whatsapp")
async def send_message():

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://www.example.com/webhook",
            headers= {
        "Authorization": API_KEY_360
    })
        
    return response.json()