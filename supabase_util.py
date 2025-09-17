from supabase import Client, create_client
import os
from dotenv import load_dotenv

load_dotenv()



url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def _check_if_summary_exists(table_name, thread_id):
    summary_data = supabase.table(table_name).select("*").eq("thread_id", thread_id).execute().data
    summary_exists = len(summary_data) != 0

    return (summary_exists, summary_data)


def toggle_dormant(table_name, thread_id, toggle_to):
    summary_exists, summary_data = _check_if_summary_exists(table_name, thread_id)

    if summary_exists:
        summary_id = summary_data[0]["id"]

        response = (
    supabase.table("real_estaid_summaries")
    .update({"dormant": toggle_to}) # dormant
    .eq("id", summary_id)
    .execute()) 

