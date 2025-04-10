import os
import json
import glob
import psycopg2
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Initialize the GenAI client using your API key
def init_genai_client():
    load_dotenv()
    return genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))

def get_location_descriptions(title, text):
    """
    Use the google-genai package to call Google's generative model to extract location descriptions.
    The prompt instructs the model to output a JSON array of location strings.
    """
    client = init_genai_client()

    prompt = (
        "You are analyzing a poem to identify specific geographic locations. "
        "Return a JSON array of strings, where each string is a location that is either explicitly mentioned, strongly implied, or clearly associated with the content of the poem. "
        "You may use general world knowledge to infer settings from context, such as ecological or cultural clues (e.g., polar bears → Arctic).\n\n"

        "The locations must be specific enough to geocode. For example:\n"
        "- Valid: cities, states, regions, named rivers, mountains, parks, or landmarks.\n"
        "- Not valid: country names or generic regions such as “the coast”, “the mountains”, “the tropics”, or “the countryside”.\n\n"

        "If no valid location can be determined, return a JSON array containing a single string: 'N/A'.\n\n"

        "Return **only** the JSON array—no explanation, comments, markdown, or additional text.\n\n"

        "Example outputs:\n"
        "['Portland, OR, US']\n"
        "['Columbia River, US', 'Sahara Desert, Africa']\n"
        "['N/A']\n\n"

        f"Title: {title}\n"
        f"Text: {text}"
    )

    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type='application/json',
            response_schema={
                'type': 'array',
                'items': {
                    'type': 'string'
                }
            },
        )
    )
    print("Raw model response:\n", response.text)
    try:
        cleaned_text = response.text.strip().strip("```json").strip("```")
        location_list = json.loads(cleaned_text)
        if isinstance(location_list, list):
            return location_list
        else:
            print("Model returned non-list JSON:", location_list)
            return []
    except json.JSONDecodeError as e:
        print(f"Error parsing GenAI response: {e}")
        return []

# --- Google Geocoding API call ---
def geocode_location(description):
    load_dotenv()
    google_api_key = os.environ.get("GOOGLE_API_KEY")
    if not google_api_key:
        raise Exception("GOOGLE_API_KEY not set in environment.")
    endpoint = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": description,
        "key": google_api_key
    }
    response = requests.get(endpoint, params=params)
    data = response.json()
    if data["status"] == "OK" and data["results"]:
        location = data["results"][0]["geometry"]["location"]
        return location["lat"], location["lng"]
    else:
        raise Exception(f"Geocoding error for '{description}': {data.get('status')}")

# --- Database Connection ---
def connect_db():
    load_dotenv()
    conn_str = os.environ.get("SUPABASE_DB_URL")
    if not conn_str:
         raise Exception("SUPABASE_DB_URL not set.")
    return psycopg2.connect(conn_str)

# --- Update a poem record with location associations ---
def update_poem_with_locations(cur, poem_id, location_descriptions):
    for desc in location_descriptions:
        # Check if this location already exists
        cur.execute("SELECT id FROM locations WHERE location_description = %s", (desc,))
        result = cur.fetchone()
        if result:
            location_id = result[0]
        else:
            if desc == "N/A":
                cur.execute(
                    """
                    INSERT INTO locations (location_description)
                    VALUES (%s)
                    ON CONFLICT (location_description) DO NOTHING
                    RETURNING id;
                    """, (desc,)
                )
                row = cur.fetchone()
                if row:
                    location_id = row[0]
                else:
                    cur.execute("SELECT id FROM locations WHERE location_description = %s", (desc,))
                    location_id = cur.fetchone()[0]
                # Link the poem and location in the join table
                cur.execute("""
                    INSERT INTO poem_locations (poem_id, location_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (poem_id, location_id))
                continue  # Skip geocoding
            try:
                lat, lon = geocode_location(desc)
            except Exception as e:
                print(f"Geocoding failed for '{desc}': {e}")
                # Insert without geometry if it doesn't already exist
                cur.execute(
                    """
                    INSERT INTO locations (location_description)
                    VALUES (%s)
                    ON CONFLICT (location_description) DO NOTHING
                    RETURNING id;
                    """, (desc,)
                )
                row = cur.fetchone()
                if row:
                    location_id = row[0]
                else:
                    cur.execute("SELECT id FROM locations WHERE location_description = %s", (desc,))
                    location_id = cur.fetchone()[0]
                # Link the poem and location in the join table
                cur.execute("""
                    INSERT INTO poem_locations (poem_id, location_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (poem_id, location_id))
                continue  # Move to next location
            cur.execute(
                """
                INSERT INTO locations (location_description, geom)
                VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s),4326)::geography)
                ON CONFLICT (location_description) DO NOTHING
                RETURNING id;
                """, (desc, lon, lat)
            )
            row = cur.fetchone()
            if row:
                location_id = row[0]
            else:
                cur.execute("SELECT id FROM locations WHERE location_description = %s", (desc,))
                location_id = cur.fetchone()[0]
        # Link the poem and location in the join table
        cur.execute("""
            INSERT INTO poem_locations (poem_id, location_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING;
        """, (poem_id, location_id))

# --- Fetch one poem at a time that has an audio_url and no location association ---
def fetch_next_poem(cur):
    cur.execute("""
        SELECT id, title, body
        FROM poems
        WHERE audio_url IS NOT NULL
          AND id NOT IN (SELECT DISTINCT poem_id FROM poem_locations)
        LIMIT 1;
    """)
    return cur.fetchone()

def main():
    load_dotenv()
    conn = connect_db()
    cur = conn.cursor()

    while True:
        poem_record = fetch_next_poem(cur)
        if not poem_record:
            print("No more poems to process.")
            break

        poem_id, title, body = poem_record
        print(f"\nProcessing poem id {poem_id}: {title}")
        try:
            location_descriptions = get_location_descriptions(title, body)
        except Exception as e:
            print(f"Error obtaining location info for poem {poem_id}: {e}")
            location_descriptions = []

        if location_descriptions:
            print(f"Found locations for poem {poem_id}: {location_descriptions}")
            update_poem_with_locations(cur, poem_id, location_descriptions)
            conn.commit()
            print(f"Updated poem {poem_id} with location associations.")
        else:
            print(f"No location descriptions found for poem {poem_id}.")

    cur.close()
    conn.close()
    print("Enrichment complete.")

if __name__ == "__main__":
    main()