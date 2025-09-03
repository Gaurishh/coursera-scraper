import os
import json
import requests
import time
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import constants
from constants import (
    GEMINI_API_KEY, GEMINI_API_URL, CLASSIFICATION_INITIAL_LEADS_FILE,
    CLASSIFICATION_WEBSITES_DIR, CLASSIFICATION_URL_FILES_DIR, CLASSIFICATION_OUTPUT_FILE,
    CLASSIFICATION_MAX_WORKERS, DEFAULT_REQUEST_TIMEOUT, LONG_API_REQUEST_TIMEOUT,
    DEFAULT_MAX_RETRIES, CLASSIFICATION_PROMPT_TEMPLATE
)

# --- LLM Master Prompt ---
# (Prompt template is now imported from constants.py)

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
    Takes a lead (dict), finds its URL file, scrapes content, calls LLM, and returns the result.
    """
    website_url = lead.get('Website')
    institution_type = lead.get('Institution Type')

    if not website_url or not institution_type:
        return None

    filename = get_domain_filename(website_url)
    if not filename:
        return None

    # First, check if the source file with all URLs exists in the 'websites' folder.
    source_url_filepath = os.path.join(CLASSIFICATION_WEBSITES_DIR, filename)
    if not os.path.exists(source_url_filepath):
        print(f"WARN: Source URL file not found in '{CLASSIFICATION_WEBSITES_DIR}' for {website_url}. Skipping.")
        return None

    url_filepath = os.path.join(CLASSIFICATION_URL_FILES_DIR, filename)
    if not os.path.exists(url_filepath):
        print(f"WARN: Top 5 URL file not found for {website_url}. Skipping.")
        return None

    try:
        with open(url_filepath, 'r', encoding='utf-8') as f:
            top_5_urls = [line.strip() for line in f if line.strip()]
    except IOError as e:
        print(f"ERROR: Could not read URL file {url_filepath}: {e}")
        return None # File read error

    if not top_5_urls:
        return None # No URLs to process

    formatted_content = scrape_and_format_content(top_5_urls)
    
    if not formatted_content.strip():
        return None # No content scraped

    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
        institution_type=institution_type,
        website_content=formatted_content
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    # Retry mechanism for LLM calls
    max_retries = DEFAULT_MAX_RETRIES
    for attempt in range(max_retries):
        try:
            print(f"🤖 LLM attempt {attempt + 1}/{max_retries} for {website_url}")
            response = requests.post(GEMINI_API_URL, json=payload, timeout=LONG_API_REQUEST_TIMEOUT)
            response.raise_for_status()
            response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            
            # Clean response text and parse JSON
            if response_text.startswith('```json'):
                response_text = response_text[7:]  # Remove ```json
            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove ```
            response_text = response_text.strip()
            
            data = json.loads(response_text)
            
            print(f"✅ SUCCESS: Analyzed {website_url}")
            return {
                'Website': website_url,
                'Institution Type': institution_type,
                'Location': lead.get('Location', 'N/A'),
                'Phone': lead.get('Phone', 'N/A'),
                'Course': data.get('recommended_course', 'N/A'),
                'Score': data.get('confidence_score', 0),
                'Reasoning': data.get('reasoning', '')
            }

        except requests.RequestException as e:
            print(f"⚠️  API request failed for {website_url} (attempt {attempt + 1}/{max_retries}). Error: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff: wait 2^attempt seconds before retrying
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} API attempts failed for {website_url}")
                return None
                
        except (KeyError, IndexError) as e:
            print(f"⚠️  Invalid API response structure for {website_url} (attempt {attempt + 1}/{max_retries}). Error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed due to invalid response structure for {website_url}")
                return None
                
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parsing failed for {website_url} (attempt {attempt + 1}/{max_retries}). Response: {response_text[:200] if 'response_text' in locals() else 'No response'}... Error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed due to JSON parsing error for {website_url}")
                return None
                
        except ValueError as e:
            print(f"⚠️  Data validation failed for {website_url} (attempt {attempt + 1}/{max_retries}). Error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed due to data validation error for {website_url}")
                return None
                
        except Exception as e:
            print(f"⚠️  Unexpected error for {website_url} (attempt {attempt + 1}/{max_retries}). Error: {e}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"⏳ Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
            else:
                print(f"❌ All {max_retries} attempts failed due to unexpected error for {website_url}")
                return None


def generate_classifications():
    """
    Main function to orchestrate the lead classification process.
    """
    # Start timing
    start_time = time.time()
    
    if not os.path.exists(CLASSIFICATION_INITIAL_LEADS_FILE):
        print(f"ERROR: Initial leads file '{CLASSIFICATION_INITIAL_LEADS_FILE}' not found.")
        return
    
    if not os.path.exists(CLASSIFICATION_URL_FILES_DIR):
        print(f"ERROR: URL files directory '{CLASSIFICATION_URL_FILES_DIR}' not found.")
        return

    try:
        leads_df = pd.read_csv(CLASSIFICATION_INITIAL_LEADS_FILE)
        leads_to_process = leads_df.to_dict('records')
    except Exception as e:
        print(f"ERROR: Could not read CSV file '{CLASSIFICATION_INITIAL_LEADS_FILE}'. Error: {e}")
        return
    
    all_results = []
    
    print(f"--- Starting Analysis for {len(leads_to_process)} Leads ---")
    
    with ThreadPoolExecutor(max_workers=CLASSIFICATION_MAX_WORKERS) as executor:
        future_to_lead = {executor.submit(process_single_lead, lead): lead for lead in leads_to_process}
        
        for future in as_completed(future_to_lead):
            result = future.result()
            if result:
                all_results.append(result)

    if not all_results:
        print("--- No leads were successfully processed. ---")
        return
        
    # Create and save the final DataFrame
    try:
        results_df = pd.DataFrame(all_results)
        results_df.to_csv(CLASSIFICATION_OUTPUT_FILE, index=False)
    except Exception as e:
        print(f"ERROR: Could not save results to '{CLASSIFICATION_OUTPUT_FILE}'. Error: {e}")
        return

    # Calculate and display total execution time
    end_time = time.time()
    execution_time = end_time - start_time
    
    print("\n--- Processing Complete ---")
    print(f"Successfully processed and classified {len(results_df)} leads.")
    print(f"Results saved to '{CLASSIFICATION_OUTPUT_FILE}'")
    print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")

# --- Execution ---
if __name__ == "__main__":
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please set your Gemini API key as an environment variable (GEMINI_API_KEY).")
    else:
        generate_classifications()

