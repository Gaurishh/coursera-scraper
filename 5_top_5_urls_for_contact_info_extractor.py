import os
import json
import requests
import time
import csv
import threading
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Import constants
from constants import (
    GEMINI_API_KEY, GEMINI_API_URL, CONTACT_INFO_INPUT_CSV, CONTACT_INFO_INPUT_DIR,
    CONTACT_INFO_OUTPUT_DIR, CONTACT_INFO_ERROR_LOG_FILE, CONTACT_INFO_MAX_WORKERS,
    CONTACT_INFO_MAX_CONSECUTIVE_ERRORS, DEFAULT_REQUEST_TIMEOUT, API_REQUEST_TIMEOUT,
    DEFAULT_MAX_RETRIES, PROGRAMMING_MASTER_PROMPT_TEMPLATE, SALES_MASTER_PROMPT_TEMPLATE,
    PROGRAMMING_KEYWORD_SCORES, SALES_KEYWORD_SCORES
)

# Thread lock for error logging
error_log_lock = threading.Lock()

def log_llm_failure(website_url, course_type, error_details):
    """
    Log LLM failure details to the error log file.
    
    Args:
        website_url (str): The website URL that failed
        course_type (str): The course type (programming/sales)
        error_details (dict): Dictionary containing error information
    """
    with error_log_lock:
        # Load existing error log or create new one
        if os.path.exists(CONTACT_INFO_ERROR_LOG_FILE):
            try:
                with open(CONTACT_INFO_ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
                    error_log = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                error_log = {"failures": []}
        else:
            error_log = {"failures": []}
        
        # Add new failure entry
        failure_entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "website_url": website_url,
            "course_type": course_type,
            "error_details": error_details
        }
        
        error_log["failures"].append(failure_entry)
        
        # Save updated error log
        try:
            with open(CONTACT_INFO_ERROR_LOG_FILE, 'w', encoding='utf-8') as f:
                json.dump(error_log, f, indent=2, ensure_ascii=False)
            print(f"📝 Logged LLM failure for {website_url} to {CONTACT_INFO_ERROR_LOG_FILE}")
        except Exception as e:
            print(f"⚠️  Failed to write error log: {e}")

# --- LLM Master Prompts for Different Course Types ---
# (Prompt templates are now imported from constants.py)

# --- Gemini 2.5 Flash API Function ---
def generate_content_with_gemini(prompt, max_retries=DEFAULT_MAX_RETRIES):
    """
    Generate content using Gemini 2.5 Pro with retry logic via REST API.
    
    Args:
        prompt (str): The prompt to send to Gemini
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        tuple: (response_text, error_details) where response_text is the generated content or None if failed,
               and error_details is a dict with error information if all retries failed
    """
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        return None, {"error": "API key not configured", "attempts": 0}
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    errors = []
    
    for attempt in range(max_retries):
        try:
            response = requests.post(GEMINI_API_URL, json=payload, timeout=API_REQUEST_TIMEOUT)
            response.raise_for_status()
            
            # Extract text from response
            response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            return response_text, None
            
        except Exception as e:
            error_info = {
                "attempt": attempt + 1,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }
            errors.append(error_info)
            print(f"⚠️  Gemini API attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"❌ All Gemini API attempts failed for prompt")
                error_details = {
                    "total_attempts": max_retries,
                    "errors": errors,
                    "final_error": errors[-1] if errors else None
                }
                return None, error_details

# --- URL Normalization Function ---
def normalize_url_for_processing(url):
    """
    Normalize URL for processing by adding https://www. prefix if not present.
    This ensures URLs from the website crawler (which stores normalized URLs like 'domain.com/path')
    are converted back to full URLs for processing.
    
    Args:
        url (str): URL to normalize (may be in format 'domain.com/path' or full URL)
        
    Returns:
        str: Full URL with https://www. prefix
    """
    # If URL already has protocol, return as is
    if url.startswith(('http://', 'https://')):
        return url
    
    # Add https://www. prefix to normalized URLs
    return f"https://www.{url}"

# --- Contact URL Prioritization Function ---
def prioritize_contact_urls(urls):
    """
    Prioritizes URLs containing exactly '/contact' or '/contact-us' to ensure they are always selected.
    
    Args:
        urls (list): List of URLs to prioritize
        
    Returns:
        tuple: (contact_urls, non_contact_urls)
    """
    contact_urls = []
    non_contact_urls = []
    
    for url in urls:
        url_lower = url.lower()
        # Check for exact matches: '/contact' or '/contact-us' (not just containing these strings)
        if url_lower.endswith('/contact') or url_lower.endswith('/contact-us') or '/contact/' in url_lower or '/contact-us/' in url_lower:
            contact_urls.append(url)
        else:
            non_contact_urls.append(url)
    
    return contact_urls, non_contact_urls

# --- URL Validation Function ---
def validate_url_content(url, timeout=DEFAULT_REQUEST_TIMEOUT):
    """
    Validates if a URL returns valid HTML content.
    
    Args:
        url (str): URL to validate
        timeout (int): Request timeout in seconds
        
    Returns:
        bool: True if URL returns valid HTML content, False otherwise
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        # Check if response is HTML
        content_type = response.headers.get('content-type', '').lower()
        if 'text/html' in content_type:
            # Check if content is not empty and has reasonable length
            content = response.text.strip()
            if len(content) > 100:  # Minimum content length threshold
                return True
        
        return False
        
    except Exception as e:
        print(f"WARN: URL validation failed for {url}: {e}")
        return False

# --- Fallback Functions (Guardrails) ---
# These run if the LLM fails, ensuring the script never crashes.
# (Keyword scores are now imported from constants.py)


def get_prioritized_urls(url_list, keyword_scores):
    """
    Scores and sorts URLs based on a refined keyword matching algorithm.

    This improved algorithm features:
    1.  **Tokenization**: URLs are split by common delimiters for more accurate word matching.
    2.  **Max Score Logic**: A URL's score is based on the highest-value keyword it contains,
        not a sum, preventing misleading scores from many low-value keywords.
    3.  **Positional Weighting**: Keywords found earlier in the URL path are given slightly
        more weight, reflecting their higher importance.
    4.  **Negative Keywords**: Specific keywords can heavily penalize a URL's score.
    5.  **Specificity Priority**: Longer keywords (e.g., 'contact-us') are checked before
        shorter ones (e.g., 'contact') to ensure the most specific term is matched.

    Args:
        url_list (list): A list of URL strings to be sorted.
        keyword_scores (dict): A dictionary mapping keywords to their scores (positive or negative).

    Returns:
        list: A new list of URLs sorted by relevancy in descending order.
    """
    scored_urls = []

    # Sort keywords by length, descending, to prioritize more specific matches first.
    # e.g., 'contact-us' will be checked before 'contact'.
    sorted_keywords = sorted(keyword_scores.keys(), key=len, reverse=True)

    for url in url_list:
        max_score = 0
        is_penalized = False

        # Use urlparse for robust path extraction
        parsed_url = urlparse(url)
        path = parsed_url.path

        # Create a clean, tokenizable string from the URL path
        # Replaces common delimiters with spaces for easy word matching
        clean_path = re.sub(r'[\/_-]', ' ', path).lower()
        tokens = clean_path.split()

        # Find the highest-scoring keyword in the tokens
        highest_keyword_score = 0
        keyword_pos = float('inf')

        for token in tokens:
            if token in keyword_scores:
                score = keyword_scores[token]
                if score > highest_keyword_score:
                    highest_keyword_score = score
                    try:
                        keyword_pos = tokens.index(token)
                    except ValueError:
                        keyword_pos = float('inf')
                
                # If a negative keyword is found, penalize heavily and stop processing
                if score < 0:
                    max_score = score
                    is_penalized = True
                    break
        
        if is_penalized:
            scored_urls.append((url, max_score))
            continue

        # Calculate score with positional weighting
        # A keyword at the start of the path is more valuable.
        # We use a decay factor of 0.95 for each position.
        if highest_keyword_score > 0 and keyword_pos != float('inf'):
            positional_decay = 0.95 ** keyword_pos
            max_score = highest_keyword_score * positional_decay
        
        # Give a small bonus to the root URL if present
        if not path or path == '/':
            max_score += 1

        scored_urls.append((url, max_score))

    # Sort URLs by the final score in descending order
    scored_urls.sort(key=lambda x: x[1], reverse=True)

    # Return only the URL strings from the sorted list
    return [url for url, score in scored_urls]

# --- Wrapper Functions (to maintain original interface) ---

def get_all_urls_deterministic_programming(url_list):
    """Wrapper function to sort URLs for a programming context."""
    print("INFO: Using improved algorithm for programming course URLs.")
    return get_prioritized_urls(url_list, PROGRAMMING_KEYWORD_SCORES)


def get_all_urls_deterministic_sales(url_list):
    """Wrapper function to sort URLs for a sales context."""
    print("INFO: Using improved algorithm for sales course URLs.")
    return get_prioritized_urls(url_list, SALES_KEYWORD_SCORES)

# --- Helper Functions ---
def get_domain_from_url(url):
    """Extract domain from URL for filename generation"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.replace('www.', '')
    return domain

def get_website_filename(website_url):
    """Generate filename for website based on URL"""
    domain = get_domain_from_url(website_url)
    return f"{domain}.txt"

# --- Processing Function ---
def process_single_lead(lead_data):
    """
    Process a single lead from CSV.
    Uses contact URL prioritization first, then LLM selection, with deterministic queue as backup.
    Validates each selected URL and replaces invalid ones from the queue.
    
    Args:
        lead_data (dict): Dictionary containing 'Website' and 'Course' keys
        
    Returns:
        tuple: (success, website_url, urls_processed, error_message)
    """
    website_url = lead_data['Website']
    course_type = lead_data['Course']
    
    # Generate filename for the website
    website_filename = get_website_filename(website_url)
    input_filepath = os.path.join(CONTACT_INFO_INPUT_DIR, website_filename)
    output_filepath = os.path.join(CONTACT_INFO_OUTPUT_DIR, website_filename)
    
    try:
        # Check if website file exists
        if not os.path.exists(input_filepath):
            return (False, website_url, 0, f"Website file not found: {website_filename}")
        
        # Read URLs from file and normalize them
        with open(input_filepath, 'r', encoding='utf-8') as f:
            raw_urls = [line.strip() for line in f if line.strip()]
        
        if not raw_urls:
            return (False, website_url, 0, "No URLs found in file")
        
        # Normalize URLs for processing (add https://www. if not present)
        urls = [normalize_url_for_processing(url) for url in raw_urls]
        print(f"📝 Normalized {len(urls)} URLs for processing from {website_filename}")
        
        # Step 1: Prioritize contact URLs first
        contact_urls, non_contact_urls = prioritize_contact_urls(urls)
        if contact_urls:
            print(f"🎯 Found {len(contact_urls)} contact URLs: {contact_urls}")
        else:
            print(f"⚠️  No contact URLs found in {len(urls)} total URLs")
        
        # Step 2: Create prioritized URL queue for non-contact URLs
        if course_type.lower() == 'programming':
            top_urls = get_prioritized_urls(non_contact_urls, PROGRAMMING_KEYWORD_SCORES)
        elif course_type.lower() == 'sales':
            top_urls = get_prioritized_urls(non_contact_urls, SALES_KEYWORD_SCORES)
        else:
            return (False, website_url, 0, f"Unknown course type: {course_type}")
            
        print(f"📋 Created prioritized queue with {len(top_urls)} non-contact URLs for {website_url} ({course_type})")
        
        # Step 3: Build final URL selection starting with contact URLs
        final_selected_urls = []
        contact_urls_added = 0
        
        # First, add all contact URLs (up to 5 total)
        for contact_url in contact_urls:
            if len(final_selected_urls) < 5:
                final_selected_urls.append(contact_url)
                contact_urls_added += 1
        
        # Step 4: Use LLM to select remaining URLs from non-contact URLs
        remaining_slots = 5 - len(final_selected_urls)
        if remaining_slots > 0 and non_contact_urls:
            if course_type.lower() == 'programming':
                prompt_template = PROGRAMMING_MASTER_PROMPT_TEMPLATE
            else:
                prompt_template = SALES_MASTER_PROMPT_TEMPLATE
                
            prompt = prompt_template.format(url_list_json=json.dumps(non_contact_urls))
            llm_selected_urls = []
            llm_success = False
            
            # Try Gemini 2.5 Pro first
            print(f"🤖 Attempting LLM selection for {remaining_slots} remaining slots...")
            response_text, error_details = generate_content_with_gemini(prompt)
            
            if response_text:
                print(f"📝 LLM response received, parsing...")
                try:
                    # Clean the response text (remove markdown code blocks if present)
                    if response_text.startswith('```json'):
                        response_text = response_text[7:]  # Remove ```json
                    if response_text.endswith('```'):
                        response_text = response_text[:-3]  # Remove ```
                    response_text = response_text.strip()
                    
                    data = json.loads(response_text)

                    if isinstance(data.get('selected_urls'), list) and len(data['selected_urls']) > 0:
                        llm_selected_urls = data['selected_urls']
                        # Limit to remaining slots
                        llm_selected_urls = llm_selected_urls[:remaining_slots]
                        llm_success = True
                        print(f"✅ SUCCESS: Gemini 2.5 Pro selected {len(llm_selected_urls)} non-contact URLs for {website_url} ({course_type})")
                    else:
                        raise ValueError("Gemini response did not contain a valid list of URLs.")

                except (json.JSONDecodeError, ValueError) as e:
                    print(f"⚠️  WARN: Gemini response parsing failed for {website_url} ({course_type}). Error: {e}")
                    llm_success = False
            else:
                print(f"⚠️  WARN: No response from Gemini API for {website_url} ({course_type})")
                llm_success = False
                
                # Log the LLM failure if we have error details
                if error_details:
                    log_llm_failure(website_url, course_type, error_details)
            
            # Fallback to deterministic selection if Gemini failed or not available
            if not llm_success:
                print(f"🔄 Using top {remaining_slots} from prioritized queue for {website_url} ({course_type})")
                llm_selected_urls = top_urls[:remaining_slots]
                # Remove these URLs from the queue
                top_urls = top_urls[remaining_slots:]
            
            # Add LLM/fallback selected URLs to final selection
            for url in llm_selected_urls:
                if len(final_selected_urls) < 5 and url not in final_selected_urls:
                    final_selected_urls.append(url)
        
        # If we still need more URLs, get them from the queue
        while len(final_selected_urls) < 5 and top_urls:
            next_url = top_urls.pop(0)
            if next_url not in final_selected_urls:
                final_selected_urls.append(next_url)
        
        if contact_urls_added > 0:
            print(f"🎯 PRIORITIZED: Added {contact_urls_added} contact URLs to final selection")
        
        # Step 5: Validate each URL and replace invalid ones with next from queue
        final_urls = []
        consecutive_errors = 0
        
        print(f"🔍 Validating and finalizing {len(final_selected_urls)} URLs for {website_url} ({course_type})")
        
        for i, url in enumerate(final_selected_urls):
            print(f"  Testing URL {i+1}/{len(final_selected_urls)}: {url}")
            
            if validate_url_content(url):
                final_urls.append(url)
                print(f"  ✅ Valid: {url}")
                consecutive_errors = 0  # Reset error counter on success
            else:
                print(f"  ❌ Invalid: {url}")
                consecutive_errors += 1
                
                # Check if we've hit the consecutive error limit
                if consecutive_errors >= CONTACT_INFO_MAX_CONSECUTIVE_ERRORS:
                    print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                    break
                
                # Find next valid URL from the queue
                replacement_found = False
                while top_urls and not replacement_found and consecutive_errors < CONTACT_INFO_MAX_CONSECUTIVE_ERRORS:
                    next_url = top_urls.pop(0)  # Pop from the front of the queue
                    # Check against both final_urls and final_selected_urls to prevent duplicates
                    if next_url not in final_urls and next_url not in final_selected_urls:
                        print(f"  🔄 Trying replacement: {next_url}")
                        if validate_url_content(next_url):
                            final_urls.append(next_url)
                            print(f"  ✅ Valid replacement: {next_url}")
                            replacement_found = True
                            consecutive_errors = 0  # Reset error counter on success
                        else:
                            print(f"  ❌ Invalid replacement: {next_url}")
                            consecutive_errors += 1
                            
                            # Check consecutive errors again
                            if consecutive_errors >= CONTACT_INFO_MAX_CONSECUTIVE_ERRORS:
                                print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                                break
                
                if not replacement_found and consecutive_errors < CONTACT_INFO_MAX_CONSECUTIVE_ERRORS:
                    print(f"  ⚠️  No valid replacement found for {url}")
                elif consecutive_errors >= CONTACT_INFO_MAX_CONSECUTIVE_ERRORS:
                    break
        
        # Step 6: Save the results
        if final_urls:
            with open(output_filepath, 'w', encoding='utf-8') as f:
                for url in final_urls:
                    f.write(url + '\n')
            print(f"💾 Saved {len(final_urls)} valid URLs to {website_filename} ({course_type})")
            print(f"📊 Summary for {website_url} ({course_type}): {len(final_urls)} final URLs")
            return (True, website_url, len(final_urls), None)
        else:
            error_msg = f"No valid URLs found for {website_url} ({course_type})"
            print(f"❌ {error_msg}")
            return (False, website_url, 0, error_msg)
            
    except Exception as e:
        error_msg = f"Error processing {website_url} ({course_type}): {e}"
        print(f"❌ {error_msg}")
        return (False, website_url, 0, error_msg)

# --- Main Logic ---
def process_leads():
    """
    Main function to process leads from CSV using multithreading for contact information extraction.
    """
    # Check if CSV file exists
    if not os.path.exists(CONTACT_INFO_INPUT_CSV):
        print(f"❌ ERROR: Input CSV file '{CONTACT_INFO_INPUT_CSV}' not found.")
        return

    # Check if websites directory exists
    if not os.path.exists(CONTACT_INFO_INPUT_DIR):
        print(f"❌ ERROR: Input directory '{CONTACT_INFO_INPUT_DIR}' not found.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(CONTACT_INFO_OUTPUT_DIR):
        print(f"📁 INFO: Output directory '{CONTACT_INFO_OUTPUT_DIR}' not found. Creating it.")
        os.makedirs(CONTACT_INFO_OUTPUT_DIR)

    # Read leads from CSV
    leads = []
    try:
        with open(CONTACT_INFO_INPUT_CSV, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if 'Website' in row and 'Course' in row and row['Website'].strip():
                    leads.append({
                        'Website': row['Website'].strip(),
                        'Course': row['Course'].strip()
                    })
    except Exception as e:
        print(f"❌ ERROR: Could not read CSV file '{CONTACT_INFO_INPUT_CSV}'. Error: {e}")
        return

    if not leads:
        print(f"❌ No valid leads found in '{CONTACT_INFO_INPUT_CSV}'.")
        return

    # Count leads by type
    programming_leads = sum(1 for lead in leads if lead['Course'].lower() == 'programming')
    sales_leads = sum(1 for lead in leads if lead['Course'].lower() == 'sales')

    print(f"🚀 Starting Multithreaded Contact Info URL Extractor")
    print("=" * 60)
    print(f"📊 Total leads to process: {len(leads)}")
    print(f"💻 Programming course leads: {programming_leads}")
    print(f"💼 Sales course leads: {sales_leads}")
    print(f"🧵 Max concurrent workers: {CONTACT_INFO_MAX_WORKERS}")
    print(f"🛑 Max consecutive errors: {CONTACT_INFO_MAX_CONSECUTIVE_ERRORS}")
    print(f"📁 Input CSV: {CONTACT_INFO_INPUT_CSV}")
    print(f"📁 Websites directory: {CONTACT_INFO_INPUT_DIR}")
    print(f"📁 Output directory: {CONTACT_INFO_OUTPUT_DIR}")
    print("=" * 60)

    # Process leads using multithreading
    start_time = time.time()
    successful_processes = 0
    total_urls_processed = 0
    programming_success = 0
    sales_success = 0
    
    # Thread-safe counters
    lock = threading.Lock()
    
    def update_counters(success, urls_count, course_type):
        nonlocal successful_processes, total_urls_processed, programming_success, sales_success
        with lock:
            if success:
                successful_processes += 1
                total_urls_processed += urls_count
                if course_type.lower() == 'programming':
                    programming_success += 1
                elif course_type.lower() == 'sales':
                    sales_success += 1
    
    # Use ThreadPoolExecutor for concurrent processing
    with ThreadPoolExecutor(max_workers=CONTACT_INFO_MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_lead = {
            executor.submit(process_single_lead, lead): lead 
            for lead in leads
        }
        
        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_lead), 1):
            lead = future_to_lead[future]
            try:
                success, website_url, urls_count, error_msg = future.result()
                
                if success:
                    update_counters(True, urls_count, lead['Course'])
                    print(f"✅ [{i}/{len(leads)}] Success: {website_url} - {urls_count} URLs extracted")
                else:
                    print(f"❌ [{i}/{len(leads)}] Failed: {website_url} ({lead['Course']}) - {error_msg}")
                    
            except Exception as e:
                print(f"❌ [{i}/{len(leads)}] Exception for {lead['Website']} ({lead['Course']}): {e}")
    
    # Calculate execution time
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Display summary
    print("\n" + "=" * 60)
    print("🎉 MULTITHREADED CONTACT INFO EXTRACTION COMPLETE!")
    print("=" * 60)
    print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")
    print(f"📊 Total Leads Processed: {len(leads)}")
    print(f"✅ Successful Processes: {successful_processes}")
    print(f"❌ Failed Processes: {len(leads) - successful_processes}")
    print(f"💻 Programming Success: {programming_success}/{programming_leads}")
    print(f"💼 Sales Success: {sales_success}/{sales_leads}")
    print(f"🔗 Total URLs Processed: {total_urls_processed}")
    print(f"📁 Results saved in: {CONTACT_INFO_OUTPUT_DIR}/")
    
    if successful_processes > 0:
        avg_urls = total_urls_processed / successful_processes
        print(f"📈 Average URLs per Lead: {avg_urls:.1f}")
    
    print("=" * 60)

# --- Execution ---
if __name__ == "__main__":
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please set your Gemini API key in the script or as an environment variable (GEMINI_API_KEY).")
    else:
        process_leads()