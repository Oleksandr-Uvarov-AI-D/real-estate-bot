from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv 
import os
import httpx
import requests
from init_azure import get_agents, make_message, get_message_list, create_thread, run_agent
from contextlib import asynccontextmanager
from util import remove_source, extract_json, get_today_date
from cal_com_methods import try_to_make_an_appointment
from supabase import Client, create_client
from fastapi import BackgroundTasks
import time
import asyncio
import hashlib
import json
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
submissions = {}

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


async def delete_old_conversations():
    # conversation_TTL = 86400 * 30
    conversation_TTL = 100
    while True:
        # print("conversation ttl executed")
        for phone_number in list(conversations.keys()):
            last_message_time = conversations[phone_number]["last_message"]
            if time.time() - last_message_time > conversation_TTL:
                print("Deleting a phone number", phone_number, "from the database.")
                conversations.pop(phone_number, None)
                print("Checking that the deletion is successful:", conversations.get(phone_number, None))
        # await asyncio.sleep(86400)
        await asyncio.sleep(60)

async def update_thread_summaries():
    # summary_update_time = 7200
    summary_update_time = 60
    while True:
        # print("summary update executed")
        try:
            # Turning into list to prevent "dictionary changed size during iteration error"
            for thread_id, last_message in list(threads_without_summaries.items()):
                # print("without summaries for loop")
                if time.time() - last_message > 75:
                # if time.time() - last_message > 60:
                    length = len(get_message_list(thread_id))
                    if length > 2:
                        print("making summary for message list: ")
                        print(get_message_list(thread_id))

                        await make_summary(thread_id)
                        threads_without_summaries.pop(thread_id, None)
                        print("popped a thread from without summaries")

            summaries = (
                supabase.table("real_estaid_summaries")
                .select("*")
                .execute()).data
            
            count = 0 
            for summary in summaries:
                count += 1
                last_time_updated = summary["last_time_updated"]
                if time.time() - last_time_updated > summary_update_time:
                    # print("if successful", time.time() - last_time_updated)
                    thread_id = summary.get("thread_id", None)
                    if thread_id == None:
                        print("thread_id is none for summary", summary)
                        print("summary count (None condition)", count)
                    else:
                        print("thead_id is not None ", thread_id)
                        length = len(get_message_list(summary["thread_id"]))
                        print("summary length successful")
                    # print(get_message_list(summary["thread_id"]))
                    if length > summary["length"]:
                        print("length is greater than summary length", length, summary["length"])
                        # print("making summary for message list: ")
                        # print(get_message_list(summary["thread_id"]))
                        await make_summary(summary["thread_id"])
            
            print("summary count", count)

            # print("update thread summaries after second for loop")

            await asyncio.sleep(30)

        except Exception as loop_event:
            import traceback
            print(f"Error in update_thread_summaries loop:\n{traceback.format_exc()}")
            await asyncio.sleep(30)
        


@asynccontextmanager
async def lifespan(app: FastAPI):
    update_thread = asyncio.create_task(update_thread_summaries())
    delete_old_convs = asyncio.create_task(delete_old_conversations())
    tasks = [update_thread, delete_old_convs]

    yield

    # cleanup on shutdown
    for task in tasks:
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

headers={"D360-API-KEY": API_KEY_360, "Content-Type": "application/json"}


@app.get("/health")
async def root():
    return {"status": "ok"}

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def home():
    return "<h1>AI-D Chatbot API is running! </h1><p>Use POST /chat to talk to the bot.</p>"

@app.post("/formspree")
async def receive_user_submission(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    
    print(data)
    user_data = data["submission"]

    key_fields = {k: user_data[k] for k in ["firstName", "lastName", "email", "phone"]}
    submission_hash = hashlib.sha256(json.dumps(key_fields, sort_keys=True).encode()).hexdigest()

    if submission_hash in submissions:
        time_now = time.time()
        if time_now - submissions[submission_hash] < 300:
            return Response(status_code=200)
    
    submissions[submission_hash] = time.time()


    first_name, last_name, email, phone_number = user_data["firstName"], user_data["lastName"], user_data["email"], user_data["phone"]

    background_tasks.add_task(handle_formspree_submission, first_name, last_name, email, phone_number)
    return Response(status_code=200)



async def handle_formspree_submission(first_name, last_name, email, phone_number):
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
                        {"type": "text", "text": first_name}  # variable substitution for the template on 360dialog.
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

    response_text = extract_json(response.text)
    phone_number = response_text["contacts"][0]["wa_id"]
    thread_id = create_thread().id
    conversations[phone_number] = {"thread_id": thread_id, "first_name": first_name, "last_message": time.time()}

    today = get_today_date()
    sys_msg = f"System message: Vandaag is {today[0]}, {today[1]}, {today[2]}. Gebruik deze datum altijd als referentie\nUser: Mijn voornaam is {first_name} en mijn achternaam is {last_name}. Mijn email is {email} en mijn telefoonnummer is {phone_number}"
    make_message(thread_id, "user", sys_msg)
    run_agent(thread_id, real_estaid_agent.id)

    insert_message = (
        supabase.table("real_estaid_messages")
        .insert({"message_id": None, "message": sys_msg, "thread_id": thread_id, "role": "assistant", "agent_id": real_estaid_agent.id})
        .execute()
        )

    # user_data = f"User: Mijn voornaam is {first_name} en mijn achternaam is {last_name}. Mijn email is {email} en mijn telefoonnummer is {phone_number}"
    # make_message(thread_id, "user", user_data)
    # run_agent(thread_id, real_estaid_agent.id)


    threads_without_summaries[thread_id] = time.time()

        
async def send_message_to_user(phone, message):
    # print("send message to user is executed with message", message)
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
            json=payload,
            timeout=30.0
        )

    return Response(status_code=200)


@app.post("/webhooks/whatsapp")
async def send_message_to_render(request: Request):
    response = await request.json()
    
    entry = response["entry"]
    changes = entry[0]["changes"]
    value = changes[0]["value"]
    if "messages" in value:
        text_in_messages = "text" in value["messages"][0]
        if not text_in_messages:
            print("text NOT in messages. value['messages'][0]:", value["messages"])
            return Response(status_code=200)

            
        user_message = value["messages"][0]["text"]["body"]
        phone_number = value["contacts"][0]["wa_id"]
        phone_number = phone_number.replace("+", "")
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
            # print("skip")
            return Response(status_code=200)
        
        if phone_number not in conversations:
            # print("phone number is NOT present in conversations")
            thread_id = create_thread().id
            conversations[phone_number] = {"thread_id":  thread_id}
            threads_without_summaries[thread_id] = time.time()
            # Send a first message (phone number wasn't in conversations, which means a user has just started a conversation)
            # That is, the user started this conversation by contacting the bot directly without sending a form.
            today = get_today_date()
            sys_msg = f"System message: Vandaag is {today[0]}, {today[1]}, {today[2]}. Gebruik deze datum altijd als referentie."
            make_message(thread_id, "user", sys_msg)

            run_agent(thread_id, real_estaid_agent.id)

            insert_message = (
            supabase.table("real_estaid_messages")
            .insert({"message_id": None, "message": sys_msg, "thread_id": thread_id, "role": "assistant", "agent_id": real_estaid_agent.id})
            .execute()
            )
        else:
            # print("phone number IS present in conversations")
            thread_id = conversations[phone_number]["thread_id"]    

        conversations[phone_number]["last_message"] = time.time()
           
        insert_data = (
            supabase.table("real_estaid_messages")
            .insert({"message_id": message_id, "message": user_message, "thread_id": thread_id, "role": "user", "agent_id": real_estaid_agent.id})
            .execute()
            )
        
        await send_message_to_ai(thread_id, phone_number, user_message)

        
    else:
        # print("no message")
        return Response(status_code=200)

    return Response(status_code=200)


async def send_message_to_ai(thread_id, phone_number, message):
    print(threads_without_summaries, "threads without summaries in send message")
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
    .insert({"message_id": None, "message": message_to_insert, "thread_id": thread_id, "role": "assistant", "agent_id": real_estaid_agent.id})
    .execute()
    )


    await send_message_to_user(phone_number, message_to_insert)

    return Response(status_code=200)


async def make_summary(thread_id):
    # print("executing make summary")
    # Get a conversation in JSON format
    # desc=True to get the last 100 messages
    message_list = (
        supabase.table("real_estaid_messages")
        .select("role, message")
        .eq("thread_id", thread_id)
        .order("id", desc=True)
        .limit(100)
        .execute()
        ).data
    
    # reversing the order because otherwise the first message is the latest
    # so this way the AI is making a summary of the last 100 messages in 
    # ascending order
    message_list = message_list[::-1]

    conversation = "".join(f"{message['role']}: {message['message']}\n" for message in message_list)

    # print("conversation: ", conversation)
    # print('conversation is not empty', conversation != "")
    # Preventing from storing an empty conversation (when the user started a dialogue but didn't send anything)
    if conversation != "":
        print("conversation not empty block start")

        # Make a message with conversation as value (summary agent)
        make_message(summary_thread.id, "user", conversation)
        print("make summary make message successful")

        # Pass the message onto summary agent
        run = run_agent(summary_thread.id, summary_agent.id)
        # print("make summary run successful")
        print(summary_thread.id, "summary thread id")


        messages_summary = get_message_list(summary_thread.id)
        messages_conversation = get_message_list(thread_id)
        length = len(messages_conversation)
    
        for message in reversed(messages_summary):
             if message.role == "assistant" and message.text_messages:
                message_to_insert = message.text_messages[-1].text.value
                break
                  
        message_to_insert = extract_json(message_to_insert)

        message_to_insert["thread_id"] = thread_id
        message_to_insert["length"] = length
        message_to_insert["last_time_updated"] = int(time.time())


        thread_msg = supabase.table("real_estaid_summaries").select("*").eq("thread_id", thread_id).execute().data
        # If not equal to 0, it means that the summary for this thread already exists
        # and it's going to be overwritten.
        if len(thread_msg) != 0:
            message_to_insert["id"] = thread_msg[0]["id"]


        insert_message = (
        supabase.table("real_estaid_summaries")
        .upsert(message_to_insert)
        .execute()
        )

        print(insert_message)

# Prompt

# make response shorter


# update the summary every two hours
# 30 days to remember the user
# add documentation to parse_date method: remember what parse_method does in the first place

# for some reason formspree post was executed multiple times for the same thing even though it's not called anywhere

# check if chatbot doesn't respond when it does'nt know if the appointment is successful
# check why sometimes summary[thread_id] is None