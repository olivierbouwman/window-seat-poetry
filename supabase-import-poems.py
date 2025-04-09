import os
import json
import glob
import psycopg2
from dotenv import load_dotenv

def connect_db():
    load_dotenv()
    conn_str = os.environ.get("SUPABASE_DB_URL")
    if not conn_str:
         raise Exception("Database connection information not available")
    return psycopg2.connect(conn_str)

def insert_poem(cur, poem):
    # Extract the primary author id (if available).
    author_id = None
    if poem.get("authors") and len(poem["authors"]) > 0:
        author_id = poem["authors"][0].get("id")

    # Extract the audio URL from the audioVersion field.
    audio_url = None
    if poem.get("audioVersion") and len(poem["audioVersion"]) > 0:
        av = poem["audioVersion"][0]
        if av.get("audioFile") and len(av["audioFile"]) > 0:
            audio_url = av["audioFile"][0].get("url")

    sql = """
        INSERT INTO poems (
            id,
            title,
            url,
            body,
            author_id,
            audio_url
        )
        VALUES (
            %(id)s,
            %(title)s,
            %(url)s,
            %(body)s,
            %(author_id)s,
            %(audio_url)s
        )
        ON CONFLICT (id) DO NOTHING;
    """
    data = {
        "id": poem.get("id"),
        "title": poem.get("title"),
        "url": poem.get("url"),
        "body": poem.get("body"),
        "author_id": author_id,
        "audio_url": audio_url
    }
    cur.execute(sql, data)

def process_file(filepath, cur):
    print(f"Processing file: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        entries = data.get("data", {}).get("entries", [])
        for poem in entries:
            insert_poem(cur, poem)

def main():
    # Adjust this glob pattern to match the location of your poem JSON files.
    json_files_path = "poems/*.json"  # <-- Change this to your actual path if needed.
    files = glob.glob(json_files_path)
    if not files:
        print("No JSON files found. Check your file path.")
        return

    conn = connect_db()
    cur = conn.cursor()

    for filepath in files:
        process_file(filepath, cur)
        conn.commit()  # Commit after processing each file.
        print(f"Finished processing: {filepath}")

    cur.close()
    conn.close()
    print("Poems import complete.")

if __name__ == "__main__":
    main()