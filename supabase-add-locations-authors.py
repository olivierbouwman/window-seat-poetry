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
        "You are analyzing information about a poet to identify geographic locations where the poet was born, lived, worked, or explicitly wrote about.\n"
        "You may also use general knowledge you have about the poet to infer relevant locations, even if those locations do not explicitly appear in the provided poet information.\n\n"

        "Rules:\n"
        "* Output: Return only a JSON array of strings.\n"
        "* Specificity: Each location must be precise enough to geocode (e.g., city, town, state, named rivers, lakes, mountains, parks, or landmarks).\n"
        "* Relevant locations only: Do not include places merely mentioned in passing or unrelated to the poet’s personal history or creative work.\n"
        "* Invalid locations: Do not include country names or generic geographic terms such as \"the coast\", \"the mountains\", or \"the countryside\".\n"
        "* If no valid locations are found, return exactly: [\"N/A\"].\n"
        "* Do not include explanations, comments, markdown formatting, or additional text—only the JSON array.\n\n"

        "Example outputs:\n"
        "[\"Portland, OR, US\"]\n"
        "[\"Columbia River, US\", \"Sahara Desert, Africa\"]\n"
        "[\"N/A\"]\n\n"

        "Poet Information to Analyze:\n"
        f"Poet Name: {title}\n"
        f"{text}"
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

# --- Update an author record with location associations ---
def update_author_with_locations(cur, author_id, location_descriptions):
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
                # Link the author and location in the join table
                cur.execute("""
                    INSERT INTO author_locations (author_id, location_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (author_id, location_id))
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
                # Link the author and location in the join table
                cur.execute("""
                    INSERT INTO author_locations (author_id, location_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING;
                """, (author_id, location_id))
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
        # Link the author and location in the join table
        cur.execute("""
            INSERT INTO author_locations (author_id, location_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING;
        """, (author_id, location_id))

# --- Fetch one author at a time that has an audio_url and no location association ---
def fetch_next_author(cur):
    cur.execute("""
        SELECT DISTINCT a.id, a.title, a.birth_year, a.death_year, 
                        a.bio_foundation, a.bio_gale, a.bio_poetry, a.bio_pol
        FROM authors a
        JOIN poems p ON a.id = p.author_id
        WHERE p.audio_url IS NOT NULL
          AND a.id NOT IN (SELECT DISTINCT author_id FROM author_locations)
        LIMIT 1;
    """)
    return cur.fetchone()

def main():
    load_dotenv()
    conn = connect_db()
    cur = conn.cursor()

    # Process all authors instead of one at a time.
    while True:
        author_record = fetch_next_author(cur)
        if not author_record:
            print("No more authors to process.")
            break

        author_id, title, birth_year, death_year, bio_foundation, bio_gale, bio_poetry, bio_pol = author_record
        print(f"\nProcessing author id {author_id}: {title}")
        
        prompt_lines = []
        if any([birth_year, death_year, bio_foundation, bio_gale, bio_poetry, bio_pol]):
            prompt_lines.append("Poet Information:")
        if birth_year is not None and str(birth_year).lower() != "none":
            prompt_lines.append(f"Birth Year: {birth_year}")
        if death_year is not None and str(death_year).lower() != "none":
            prompt_lines.append(f"Death Year: {death_year}")
        if bio_foundation and str(bio_foundation).lower() != "none":
            prompt_lines.append(f"Bio (Foundation): {bio_foundation}")
        if bio_gale and str(bio_gale).lower() != "none":
            prompt_lines.append(f"Bio (Gale): {bio_gale}")
        if bio_poetry and str(bio_poetry).lower() != "none":
            prompt_lines.append(f"Bio (Poetry): {bio_poetry}")
        if bio_pol and str(bio_pol).lower() != "none":
            prompt_lines.append(f"Bio (Pol): {bio_pol}")
        prompt_text = "\n".join(prompt_lines)
        
        try:
            location_descriptions = get_location_descriptions(title, prompt_text)
        except Exception as e:
            print(f"Error obtaining location info for author {author_id}: {e}")
            location_descriptions = []

        if location_descriptions:
            print(f"Found locations for author {author_id}: {location_descriptions}")
            update_author_with_locations(cur, author_id, location_descriptions)
            conn.commit()
            print(f"Updated author {author_id} with location associations: {location_descriptions}")
        else:
            print(f"No location descriptions found for author {author_id}.")

    cur.close()
    conn.close()
    print("Enrichment complete.")

if __name__ == "__main__":
    main()

