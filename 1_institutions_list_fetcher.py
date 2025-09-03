import requests
import time
import os
import json
import csv

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Import constants
from constants import (
    GOOGLE_PLACES_API_KEY, GOOGLE_PLACES_DETAILS_URL, GOOGLE_PLACES_TEXT_SEARCH_URL,
    PLACE_DETAILS_FIELDS, GOOGLE_PLACES_RATE_LIMIT_DELAY, PAGINATION_DELAY,
    CITIES_TO_SEARCH, INSTITUTION_TYPES, MAX_PAGES_PER_QUERY,
    BANGALORE_KEYWORDS, DEFAULT_LOCATION, INITIAL_LEADS_OUTPUT_FILE,
    DEFAULT_REQUEST_TIMEOUT
)

def categorize_location(location_string):
    """
    Categorizes a location string based on keywords.
    
    Args:
        location_string (str): The location string to categorize
        
    Returns:
        str: "Bangalore" if the location contains Bangalore/Bengaluru/Karnataka keywords, otherwise "Delhi"
    """
    if not location_string or location_string == "N/A":
        return DEFAULT_LOCATION
    
    location_lower = location_string.lower()
    
    for keyword in BANGALORE_KEYWORDS:
        if keyword in location_lower:
            return "Bangalore"
    
    return DEFAULT_LOCATION

def get_place_details(api_key, place_id):
    """
    Fetches detailed information for a specific place using the Place Details API.
    
    Args:
        api_key (str): Google Cloud Platform API key
        place_id (str): The place ID to get details for
        
    Returns:
        dict: Place details including website, phone, etc.
    """
    params = {
        "place_id": place_id,
        "key": api_key,
        "fields": PLACE_DETAILS_FIELDS
    }
    
    try:
        response = requests.get(GOOGLE_PLACES_DETAILS_URL, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()
        result = response.json()
        
        if result.get("status") == "OK":
            return result.get("result", {})
        else:
            print(f"WARN: Place Details API error for {place_id}: {result.get('status')}")
            return {}
            
    except Exception as e:
        print(f"WARN: Error fetching place details for {place_id}: {e}")
        return {}

def fetch_institutions(api_key, cities, institution_types):
    """
    Fetches a list of institutions from the Google Places API based on cities and types.

    Args:
        api_key (str): Your Google Cloud Platform API key with Places API enabled.
        cities (list): A list of city names to search in (e.g., ["Bangalore", "Delhi"]).
        institution_types (list): A list of types to search for (e.g., ["Corporates", "Schools"]).

    Returns:
        list: A list of tuples, where each tuple contains (Institution Name, Type, Website, Location, Phone).
    """
    base_url = GOOGLE_PLACES_TEXT_SEARCH_URL
    all_institutions = []
    
    # 1. More precise search queries targeted for Programming and Sales courses
    search_queries = {
        "Corporates": [
            # Queries for Programming course leads
            "Software companies in {}",
            # Queries for Sales course leads
            "Sales and marketing companies in {}",
        ],
        "Schools": [
            # Queries for Programming course leads
            "Engineering colleges in {}",
            # Queries for Sales course leads
            "Business schools in {}",
        ]
    }

    # 2. Using a set to track processed place IDs is an efficient way to handle duplicates
    processed_place_ids = set()

    for city in cities:
        for inst_type in institution_types:
            if inst_type in search_queries:
                for query_template in search_queries[inst_type]:
                    query = query_template.format(city)
                    print(f"INFO: Searching for '{query}'...")
                    
                    params = {
                        "query": query,
                        "key": api_key
                    }
                    
                    # Loop to handle pagination (limited to max pages)
                    page_count = 1  # Start with page 1
                    max_pages = MAX_PAGES_PER_QUERY
                    
                    while page_count <= max_pages:
                        try:
                            response = requests.get(base_url, params=params, timeout=DEFAULT_REQUEST_TIMEOUT)
                            response.raise_for_status()
                            results = response.json()
                        except requests.exceptions.RequestException as e:
                            print(f"ERROR: An HTTP request error occurred: {e}")
                            break
                        except json.JSONDecodeError:
                            print(f"ERROR: Failed to decode JSON from response.")
                            break

                        print(f"INFO: Processing page {page_count}...")
                        
                        for place in results.get("results", []):
                            place_id = place.get("place_id")
                            if place_id and place_id not in processed_place_ids:
                                try:
                                    name = place.get("name", "N/A")
                                    
                                    # Get detailed information including website
                                    print(f"INFO: Fetching details for {name}...")
                                    place_details = get_place_details(api_key, place_id)
                                    
                                    # Extract website and other details
                                    website = place_details.get("website", "")
                                    phone = place_details.get("formatted_phone_number", "N/A")
                                    
                                    # Only add institutions that have valid websites
                                    if website and website.strip() and website.lower() not in ['n/a', 'na', '']:
                                        # Categorize the location based on keywords
                                        raw_location = place.get("formatted_address", "N/A")
                                        categorized_location = categorize_location(raw_location)
                                        
                                        institution_data = (
                                            name, 
                                            inst_type, 
                                            website, 
                                            categorized_location,
                                            phone
                                        )
                                        all_institutions.append(institution_data)
                                        print(f"INFO: Added {name} with website: {website}")
                                    else:
                                        print(f"INFO: Skipped {name} - no valid website found")
                                    
                                    processed_place_ids.add(place_id)
                                    
                                    # Rate limiting - Google allows 100 requests per 100 seconds
                                    time.sleep(GOOGLE_PLACES_RATE_LIMIT_DELAY)
                                    
                                except Exception as e:
                                    print(f"WARN: Error processing place: {place.get('name', 'Unknown')}. Details: {e}")

                        next_page_token = results.get('next_page_token')
                        
                        if next_page_token and page_count < max_pages:
                            params['pagetoken'] = next_page_token
                            page_count += 1
                            print(f"INFO: Moving to page {page_count}...")
                            time.sleep(PAGINATION_DELAY) 
                        else:
                            if page_count >= max_pages:
                                print(f"INFO: Reached maximum page limit ({max_pages}) for query: {query}")
                            else:
                                print(f"INFO: No more pages available for query: {query} (found {page_count} pages)")
                            break
            else:
                print(f"WARN: No defined search queries for institution type: {inst_type}")

    return all_institutions

def save_to_csv(data, filename=INITIAL_LEADS_OUTPUT_FILE):
    """
    Saves the provided data to a CSV file.

    Args:
        data (list of tuples): The data to save.
        filename (str): The name of the output CSV file.
    """
    if not data:
        print("INFO: No data to save to CSV.")
        return
        
    try:
        # 'w' mode overwrites the file completely - no data accumulation
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            # Write header with new columns
            writer.writerow(['Institution Name', 'Institution Type', 'Website', 'Location', 'Phone'])
            # Write data rows
            writer.writerows(data)
        print(f"\nSUCCESS: Successfully saved {len(data)} leads with valid websites to {filename}")
    except IOError as e:
        print(f"ERROR: Could not write to file {filename}. Error: {e}")


# --- Main Execution ---
if __name__ == "__main__":
    # Start timing
    start_time = time.time()
    print("Starting Coursera Lead Generation Script...")
    print("=" * 60)
    
    if GOOGLE_PLACES_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please replace 'YOUR_API_KEY_HERE' with your actual Google Places API key or set the GOOGLE_PLACES_API_KEY environment variable.")
    else:
        cities_to_search = CITIES_TO_SEARCH
        types_to_search = INSTITUTION_TYPES
        
        discovered_leads = fetch_institutions(GOOGLE_PLACES_API_KEY, cities_to_search, types_to_search)
        
        # 3. Save the final output to a CSV file
        save_to_csv(discovered_leads)
        
        # Optional: Print a summary to the console
        if discovered_leads:
            print(f"\n--- Discovered {len(discovered_leads)} Leads with Valid Websites (Summary) ---")
            for lead in discovered_leads[:5]: # Print first 5 as a sample
                print(lead)
        else:
            print("\n--- No leads with valid websites found ---")
    
    # Calculate and display total execution time
    end_time = time.time()
    total_time = end_time - start_time
    
    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    
    # Format time display
    if total_time < 60:
        print(f"Total execution time: {total_time:.2f} seconds")
    elif total_time < 3600:
        minutes = int(total_time // 60)
        seconds = total_time % 60
        print(f"Total execution time: {minutes} minutes {seconds:.2f} seconds")
    else:
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        seconds = total_time % 60
        print(f"Total execution time: {hours} hours {minutes} minutes {seconds:.2f} seconds")
    
    print("Script completed successfully!")
    print("=" * 60)