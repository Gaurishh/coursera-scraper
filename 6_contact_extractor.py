import os
import json
import requests
import time
import pandas as pd
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import constants
from constants import (
    GEMINI_API_KEY, FINAL_GATHERER_INPUT_CSV,
    FINAL_GATHERER_CONTACT_URLS_DIR, FINAL_GATHERER_OUTPUT_DIR,
    FINAL_GATHERER_MAX_WORKERS, DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_MAX_RETRIES, PROGRAMMING_CONTACT_EXTRACTION_PROMPT_TEMPLATE,
    SALES_CONTACT_EXTRACTION_PROMPT_TEMPLATE
)

# Import LLM utilities
from llm_utils import call_gemini_with_params, parse_llm_response

# --- LLM Master Prompts for Contact Information Extraction ---
# (Prompt templates are now imported from constants.py and selected based on course type)

# --- Helper Functions ---

def get_domain_filename(url):
    """Generates a clean filename from a URL."""
    try:
        domain = urlparse(url).netloc
        if not domain:
            print(f"WARN: Could not extract domain from URL: {url}")
            return None
        return domain.replace('www.', '') + '.txt'
    except Exception as e:
        print(f"ERROR: Error parsing URL {url}: {e}")
        return None

def scrape_and_format_content(url_list):
    """
    Scrapes a list of URLs and formats their text content.
    Returns a single formatted string.
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    full_content = []

    for url in url_list:
        try:
            response = requests.get(url, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()
            
            text = soup.get_text(separator='\n', strip=True)
            
            full_content.append(f"{url}\n{text}\n\n----\n")
        except requests.RequestException as e:
            print(f"WARN: Could not scrape {url}. Error: {e}")
            full_content.append(f"{url}\n[Could not retrieve content]\n\n----\n")
    
    return "".join(full_content)

# --- Main Processing Logic ---

def process_single_lead(lead):
    """
    Takes a lead (dict), finds its contact URL file, scrapes content, calls LLM, and saves the result.
    """
    website_url = lead.get('Website')
    course_type = lead.get('Course')

    if not website_url:
        return None

    filename = get_domain_filename(website_url)
    if not filename:
        return None

    # Check if the contact URL file exists
    contact_url_filepath = os.path.join(FINAL_GATHERER_CONTACT_URLS_DIR, filename)
    if not os.path.exists(contact_url_filepath):
        print(f"WARN: Contact URL file not found for {website_url}. Skipping.")
        return None

    try:
        with open(contact_url_filepath, 'r', encoding='utf-8') as f:
            contact_urls = [line.strip() for line in f if line.strip()]
    except IOError as e:
        print(f"ERROR: Could not read contact URL file {contact_url_filepath}: {e}")
        return None

    if not contact_urls:
        print(f"WARN: No contact URLs found for {website_url}. Skipping.")
        return None

    formatted_content = scrape_and_format_content(contact_urls)
    
    if not formatted_content.strip():
        print(f"WARN: No content scraped for {website_url}. Skipping.")
        return None

    # Select appropriate prompt template based on course type
    if course_type == "Programming":
        prompt_template = PROGRAMMING_CONTACT_EXTRACTION_PROMPT_TEMPLATE
    elif course_type == "Sales":
        prompt_template = SALES_CONTACT_EXTRACTION_PROMPT_TEMPLATE
    else:
        # Default to programming if course type is not recognized
        prompt_template = PROGRAMMING_CONTACT_EXTRACTION_PROMPT_TEMPLATE
        print(f"WARN: Unknown course type '{course_type}' for {website_url}. Using programming prompt template.")
    
    prompt = prompt_template.format(
        website_content=formatted_content
    )

    # Use enhanced LLM call
    response_text, error_details = call_gemini_with_params(
        prompt=prompt,
        task_type="contact_extraction",
        max_retries=DEFAULT_MAX_RETRIES
    )
    
    if error_details:
        print(f"❌ LLM call failed for {website_url}: {error_details}")
        return None
    
    # Parse the response
    data, parse_error = parse_llm_response(response_text, "json")
    
    if parse_error:
        print(f"❌ Response parsing failed for {website_url}: {parse_error}")
        return None
    
    # Extract contacts from response
    contacts = data.get('contacts', [])
    
    # Create output filename
    domain = urlparse(website_url).netloc.replace('www.', '')
    output_filename = f"{domain}.json"
    output_filepath = os.path.join(FINAL_GATHERER_OUTPUT_DIR, output_filename)
    
    # Save the contact information to JSON file
    with open(output_filepath, 'w', encoding='utf-8') as f:
        json.dump(contacts, f, indent=2, ensure_ascii=False)
    
    print(f"✅ SUCCESS: Extracted {len(contacts)} contacts for {website_url} ({course_type})")
    return {
        'website': website_url,
        'course': course_type,
        'contacts_found': len(contacts),
        'output_file': output_filename
    }


def gather_contact_information():
    """
    Main function to orchestrate the contact information gathering process.
    """
    # Start timing
    start_time = time.time()
    
    if not os.path.exists(FINAL_GATHERER_INPUT_CSV):
        print(f"ERROR: Input CSV file '{FINAL_GATHERER_INPUT_CSV}' not found.")
        return
    
    if not os.path.exists(FINAL_GATHERER_CONTACT_URLS_DIR):
        print(f"ERROR: Contact URLs directory '{FINAL_GATHERER_CONTACT_URLS_DIR}' not found.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(FINAL_GATHERER_OUTPUT_DIR):
        print(f"INFO: Output directory '{FINAL_GATHERER_OUTPUT_DIR}' not found. Creating it.")
        os.makedirs(FINAL_GATHERER_OUTPUT_DIR)

    try:
        leads_df = pd.read_csv(FINAL_GATHERER_INPUT_CSV)
        leads_to_process = leads_df.to_dict('records')
    except Exception as e:
        print(f"ERROR: Could not read CSV file '{FINAL_GATHERER_INPUT_CSV}'. Error: {e}")
        return
    
    all_results = []
    
    print(f"--- Starting Contact Information Extraction for {len(leads_to_process)} Leads ---")
    print(f"🧵 Using 3 workers for multithreaded processing")
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_lead = {executor.submit(process_single_lead, lead): lead for lead in leads_to_process}
        
        for i, future in enumerate(as_completed(future_to_lead), 1):
            lead = future_to_lead[future]
            try:
                result = future.result()
                if result:
                    all_results.append(result)
                    print(f"✅ [{i}/{len(leads_to_process)}] Success: {lead.get('Website', 'Unknown')} - {result.get('contacts_found', 0)} contacts")
                else:
                    print(f"❌ [{i}/{len(leads_to_process)}] Failed: {lead.get('Website', 'Unknown')}")
            except Exception as e:
                print(f"❌ [{i}/{len(leads_to_process)}] Exception for {lead.get('Website', 'Unknown')}: {e}")

    if not all_results:
        print("--- No leads were successfully processed. ---")
        return
        
    # Calculate and display total execution time
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Display summary statistics
    total_contacts = sum(result['contacts_found'] for result in all_results)
    programming_leads = sum(1 for result in all_results if result['course'].lower() == 'programming')
    sales_leads = sum(1 for result in all_results if result['course'].lower() == 'sales')
    
    print("\n--- Multithreaded Contact Information Extraction Complete ---")
    print(f"Successfully processed {len(all_results)} leads.")
    print(f"Total contacts extracted: {total_contacts}")
    print(f"Programming course leads: {programming_leads}")
    print(f"Sales course leads: {sales_leads}")
    print(f"Contact information saved in '{FINAL_GATHERER_OUTPUT_DIR}/' directory")
    print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")
    
    if len(all_results) > 0:
        avg_contacts = total_contacts / len(all_results)
        print(f"📈 Average contacts per lead: {avg_contacts:.1f}")

# --- Execution ---
if __name__ == "__main__":
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please set your Gemini API key as an environment variable (GEMINI_API_KEY).")
    else:
        gather_contact_information()
