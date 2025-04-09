import os
import json
import glob
import psycopg2
from dotenv import load_dotenv

def connect_db():
    from dotenv import load_dotenv
    load_dotenv()

    conn_str = os.environ.get("SUPABASE_DB_URL")
    if not conn_str:
         raise Exception("Database connection information not available")
    return psycopg2.connect(conn_str)

def insert_author(cur, author):
    # Map JSON field names to our table's columns.
    sql = """
        INSERT INTO authors (
            id,
            title,
            url,
            birth_year,
            death_year,
            bio_foundation,
            bio_gale,
            bio_poetry,
            bio_pol
        )
        VALUES (
            %(id)s,
            %(title)s,
            %(url)s,
            %(birth_year)s,
            %(death_year)s,
            %(bio_foundation)s,
            %(bio_gale)s,
            %(bio_poetry)s,
            %(bio_pol)s
        )
        ON CONFLICT (id) DO NOTHING;
    """
    data = {
        "id": author.get("id"),
        "title": author.get("title"),
        "url": author.get("url"),
        "birth_year": author.get("birthYear"),
        "death_year": author.get("deathYear"),
        "bio_foundation": author.get("foundationBio"),
        "bio_gale": author.get("galeBio"),
        "bio_poetry": author.get("poetryBio"),
        "bio_pol": author.get("polBio")
    }
    cur.execute(sql, data)

def process_file(filepath, cur):
    print(f"Processing file: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        entries = data.get("data", {}).get("entries", [])
        for author in entries:
            insert_author(cur, author)

def main():
    # Adjust this glob pattern to match the location of your 6 JSON files with author data.
    json_files_path = "authors/*.json"  # <-- Replace with your actual path
    files = glob.glob(json_files_path)
    if not files:
        print("No JSON files found. Check your file path.")
        return

    conn = connect_db()
    cur = conn.cursor()

    # Process each file and commit after each file.
    for filepath in files:
        process_file(filepath, cur)
        conn.commit()
        print(f"Finished processing: {filepath}")

    cur.close()
    conn.close()
    print("Authors import complete.")

if __name__ == "__main__":
    main()