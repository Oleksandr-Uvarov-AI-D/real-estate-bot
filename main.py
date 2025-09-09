from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from dotenv import load_dotenv 
import os
import httpx

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
    
    user_data = data["submission"]
    first_name, last_name, email, phone = user_data["firstName"], user_data["lastName"], user_data["email"], user_data["phone"]

    print(first_name, last_name, email, phone)

    payload = {"first_name": first_name, "last_name": last_name, "email": email, "phone": phone}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://waba.360dialog.io/v1/messages",
            headers= {f"D360-API-KEY: {API_KEY_360}", "Content-Type: application/json"},
            json=payload
            
        )
    return {"message": "Webhook received"}