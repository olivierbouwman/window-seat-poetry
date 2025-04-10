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
        "You are analyzing a poem to identify specific geographic locations.\n"
        "Return a JSON array of strings, where each string is a location that is either explicitly mentioned, strongly implied, or clearly associated with the content of the poem.\n"
        "You may use general world knowledge to infer settings from context, such as ecological or cultural clues (e.g., polar bears → Arctic).\n\n"

        "Rules:\n"
        "* Output: Return only a JSON array of strings.\n"
        "* Specificity: Each location must be precise enough to geocode (e.g., city, town, state, named rivers, lakes, mountains, parks, or landmarks).\n"
        "* Invalid locations: Do not include generic geographic terms such as \"the coast\", \"the mountains\", or \"the countryside\".\n"
        "* Country names:\n"
        "    * Always include country names when part of a city/state/country or landmark/region/country combination (e.g., \"Portland, OR, US\", \"Rocky Mountains, US\", \"Mount Hood, Oregon, US\").\n"
        "    * Include country names alone only if:\n"
        "        * The country is relatively small and specific (e.g., \"Luxembourg\", \"Iceland\").\n"
        "        * No more specific location within that country can be identified.\n"
        "* If no valid locations are found, return exactly: [\"N/A\"].\n"
        "* Do not include explanations, comments, markdown formatting, or additional text—only the JSON array.\n\n"

        "Example outputs:\n"
        "[\"Portland, OR, US\"]\n"
        "[\"Columbia River, US\", \"Sahara Desert, Africa\"]\n"
        "[\"N/A\"]\n\n"

        f"Title: {title}\n"
        f"Text: {text}"
    )
    print("Rendered prompt:\n", prompt)  # Debug: print the rendered prompt

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