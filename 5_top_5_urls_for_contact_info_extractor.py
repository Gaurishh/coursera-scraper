import os
import json
import requests
import time
import csv
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# Import the new Google Gen AI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    print("WARNING: google-genai package not installed. Install with: pip install google-genai")
    GENAI_AVAILABLE = False

# --- Configuration ---
INPUT_CSV = "2_leads_classified.csv"
INPUT_DIR = "websites"
OUTPUT_DIR = "top_5_urls_for_contact_info"
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
MAX_WORKERS = 1  # Number of concurrent threads for processing
MAX_CONSECUTIVE_ERRORS = 5  # Stop trying after 5 consecutive URL validation failures

# Initialize the Gen AI client
if GENAI_AVAILABLE and API_KEY != "YOUR_API_KEY_HERE":
    try:
        client = genai.Client(api_key=API_KEY)
        print("✅ Successfully initialized Gemini 2.5 Flash client")
    except Exception as e:
        print(f"❌ Failed to initialize Gemini client: {e}")
        GENAI_AVAILABLE = False
else:
    print("⚠️  Gemini client not available - will use fallback methods only")

# --- LLM Master Prompts for Different Course Types ---
# Programming Course Master Prompt
PROGRAMMING_MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure and contact information discovery for technology companies. Your task is to identify the most informative URLs from a given list that will help a sales team find contact information, key personnel, and communication channels for programming course sales.

Primary Goal:
Select the most informative URLs from the list below that are most likely to contain contact information, key personnel details, or communication channels relevant to programming course sales. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain:
- Contact information (phone numbers, email addresses, physical addresses)
- Key personnel (CTO, technical directors, IT managers, decision makers)
- Communication channels (contact forms, inquiry pages, support)
- Company/organization details (about us, leadership, team)
- Technical departments (IT, software development, engineering)
- Training or education departments
- Business development or partnership information

IMPORTANT: If any URLs contain "/contact" or "/contact-us" in their path, prioritize these URLs as they are most likely to contain direct contact information.

This information will be used for programming course sales outreach and lead generation. Use your own expert judgment to determine the most relevant URLs from the list.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

# Sales Course Master Prompt
SALES_MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure and contact information discovery for business organizations. Your task is to identify the most informative URLs from a given list that will help a sales team find contact information, key personnel, and communication channels for sales course sales.

Primary Goal:
Select the most informative URLs from the list below that are most likely to contain contact information, key personnel details, or communication channels relevant to sales course sales. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain:
- Contact information (phone numbers, email addresses, physical addresses)
- Key personnel (sales managers, business development directors, marketing managers, decision makers)
- Communication channels (contact forms, inquiry pages, support)
- Company/organization details (about us, leadership, team)
- Business departments (sales, marketing, business development)
- Training or HR departments
- Business development or partnership information

IMPORTANT: If any URLs contain "/contact" or "/contact-us" in their path, prioritize these URLs as they are most likely to contain direct contact information.

This information will be used for sales course sales outreach and lead generation. Use your own expert judgment to determine the most relevant URLs from the list.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

# --- Gemini 2.5 Pro API Function ---
def generate_content_with_gemini(prompt, max_retries=3):
    """
    Generate content using Gemini 2.5 Pro with retry logic.
    
    Args:
        prompt (str): The prompt to send to Gemini
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        str: Generated content or None if failed
    """
    if not GENAI_AVAILABLE:
        return None
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,  # Lower temperature for more consistent results
                    max_output_tokens=800,  # Shorter responses for URL selection
                    top_p=0.7,  # More focused responses
                    top_k=20  # Limit vocabulary for better consistency
                )
            )
            return response.text
            
        except Exception as e:
            print(f"⚠️  Gemini API attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                print(f"❌ All Gemini API attempts failed for prompt")
                return None

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
    Prioritizes URLs containing '/contact' or '/contact-us' to ensure they are always selected.
    
    Args:
        urls (list): List of URLs to prioritize
        
    Returns:
        tuple: (contact_urls, non_contact_urls)
    """
    contact_urls = []
    non_contact_urls = []
    
    for url in urls:
        url_lower = url.lower()
        if '/contact' in url_lower or '/contact-us' in url_lower:
            contact_urls.append(url)
        else:
            non_contact_urls.append(url)
    
    return contact_urls, non_contact_urls

# --- URL Validation Function ---
def validate_url_content(url, timeout=10):
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

def get_all_urls_deterministic_programming(url_list):
    """
    Selects ALL URLs based on a deterministic keyword scoring system for programming course contact information.
    Returns a list of URLs sorted by priority (highest score first).
    Used as a prioritized queue for fallback URL selection.
    """
    print("INFO: Creating prioritized URL queue based on keyword scoring for programming course.")
    
    # Keywords with assigned scores. Higher is better for programming course contact information.
    keyword_scores = {
        # Tier 1: Direct Contact Information (Score 10)
        'contact': 10, 'contact-us': 10, 'contactus': 10, 'get-in-touch': 10,
        'reach-us': 10, 'connect': 10, 'inquiry': 10, 'enquiry': 10,
        
        # Tier 2: Technical Leadership & Personnel (Score 9)
        'leadership': 9, 'team': 9, 'directors': 9, 'management': 9,
        'founders': 9, 'ceo': 9, 'founder': 9, 'executives': 9,
        'cto': 9, 'technical-director': 9, 'it-manager': 9,
        
        # Tier 3: Technical Departments (Score 8)
        'about': 8, 'about-us': 8, 'aboutus': 8, 'who-we-are': 8,
        'company': 8, 'organization': 8, 'profile': 8,
        'it': 8, 'software': 8, 'development': 8, 'engineering': 8,
        'technology': 8, 'tech': 8,
        
        # Tier 4: Training & Education (Score 7)
        'training': 7, 'education': 7, 'learning': 7, 'courses': 7,
        'academy': 7, 'institute': 7, 'university': 7,
        
        # Tier 5: Business Development (Score 6)
        'partnership': 6, 'partnerships': 6, 'collaborate': 6,
        'business-development': 6, 'sales': 6, 'marketing': 6,
        
        # Tier 6: Support & Services (Score 5)
        'support': 5, 'help': 5, 'services': 5, 'solutions': 5,
        'consulting': 5, 'advisory': 5,
        
        # Tier 7: Career & Opportunities (Score 4)
        'career': 4, 'careers': 4, 'jobs': 4, 'opportunities': 4,
        'join-us': 4, 'work-with-us': 4,
        
        # Tier 8: General Information (Score 2)
        'news': 2, 'blog': 2, 'events': 2, 'gallery': 2,
        
        # Tier 9: Low Priority (Score 1)
        'privacy': 1, 'terms': 1, 'sitemap': 1, 'alumni': 1
    }
    
    scored_urls = []
    for url in url_list:
        score = 0
        # Check for keywords in the URL path
        for keyword, value in keyword_scores.items():
            if keyword in url.lower():
                score += value
        
        # Give a small bonus to the root URL if present
        if url.endswith(('.com/', '.in/', '.org/', '.ac.in/')):
             score += 2

        scored_urls.append((url, score))
        
    # Sort URLs by score in descending order
    scored_urls.sort(key=lambda x: x[1], reverse=True)
    
    # Return ALL URLs sorted by priority (not just top 5)
    return [url for url, score in scored_urls]

def get_all_urls_deterministic_sales(url_list):
    """
    Selects ALL URLs based on a deterministic keyword scoring system for sales course contact information.
    Returns a list of URLs sorted by priority (highest score first).
    Used as a prioritized queue for fallback URL selection.
    """
    print("INFO: Creating prioritized URL queue based on keyword scoring for sales course.")
    
    # Keywords with assigned scores. Higher is better for sales course contact information.
    keyword_scores = {
        # Tier 1: Direct Contact Information (Score 10)
        'contact': 10, 'contact-us': 10, 'contactus': 10, 'get-in-touch': 10,
        'reach-us': 10, 'connect': 10, 'inquiry': 10, 'enquiry': 10,
        
        # Tier 2: Business Leadership & Personnel (Score 9)
        'leadership': 9, 'team': 9, 'directors': 9, 'management': 9,
        'founders': 9, 'ceo': 9, 'founder': 9, 'executives': 9,
        'sales-manager': 9, 'business-director': 9, 'marketing-manager': 9,
        
        # Tier 3: Business Departments (Score 8)
        'about': 8, 'about-us': 8, 'aboutus': 8, 'who-we-are': 8,
        'company': 8, 'organization': 8, 'profile': 8,
        'sales': 8, 'marketing': 8, 'business': 8, 'commercial': 8,
        
        # Tier 4: Training & HR (Score 7)
        'training': 7, 'education': 7, 'learning': 7, 'courses': 7,
        'hr': 7, 'human-resources': 7, 'personnel': 7,
        'academy': 7, 'institute': 7, 'university': 7,
        
        # Tier 5: Business Development (Score 6)
        'partnership': 6, 'partnerships': 6, 'collaborate': 6,
        'business-development': 6, 'b2b': 6, 'enterprise': 6,
        
        # Tier 6: Support & Services (Score 5)
        'support': 5, 'help': 5, 'services': 5, 'solutions': 5,
        'consulting': 5, 'advisory': 5,
        
        # Tier 7: Career & Opportunities (Score 4)
        'career': 4, 'careers': 4, 'jobs': 4, 'opportunities': 4,
        'join-us': 4, 'work-with-us': 4,
        
        # Tier 8: General Information (Score 2)
        'news': 2, 'blog': 2, 'events': 2, 'gallery': 2,
        
        # Tier 9: Low Priority (Score 1)
        'privacy': 1, 'terms': 1, 'sitemap': 1, 'alumni': 1
    }
    
    scored_urls = []
    for url in url_list:
        score = 0
        # Check for keywords in the URL path
        for keyword, value in keyword_scores.items():
            if keyword in url.lower():
                score += value
        
        # Give a small bonus to the root URL if present
        if url.endswith(('.com/', '.in/', '.org/', '.ac.in/')):
             score += 2

        scored_urls.append((url, score))
        
    # Sort URLs by score in descending order
    scored_urls.sort(key=lambda x: x[1], reverse=True)
    
    # Return ALL URLs sorted by priority (not just top 5)
    return [url for url, score in scored_urls]

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
    input_filepath = os.path.join(INPUT_DIR, website_filename)
    output_filepath = os.path.join(OUTPUT_DIR, website_filename)
    
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
            top_urls = get_all_urls_deterministic_programming(non_contact_urls)
        elif course_type.lower() == 'sales':
            top_urls = get_all_urls_deterministic_sales(non_contact_urls)
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
            if GENAI_AVAILABLE:
                print(f"🤖 Attempting LLM selection for {remaining_slots} remaining slots...")
                response_text = generate_content_with_gemini(prompt)
                
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
                            print(f"✅ SUCCESS: Gemini 2.5 Flash selected {len(llm_selected_urls)} non-contact URLs for {website_url} ({course_type})")
                        else:
                            raise ValueError("Gemini response did not contain a valid list of URLs.")

                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"⚠️  WARN: Gemini response parsing failed for {website_url} ({course_type}). Error: {e}")
                        llm_success = False
                else:
                    print(f"⚠️  WARN: No response from Gemini API for {website_url} ({course_type})")
                    llm_success = False
            else:
                print(f"⚠️  WARN: Gemini API not available for {website_url} ({course_type})")
                llm_success = False
            
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
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                    break
                
                # Find next valid URL from the queue
                replacement_found = False
                while top_urls and not replacement_found and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
                    next_url = top_urls.pop(0)  # Pop from the front of the queue
                    if next_url not in final_urls:  # Make sure we don't duplicate
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
                            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                                print(f"  🛑 STOPPING: {consecutive_errors} consecutive errors reached. Website may be unreachable.")
                                break
                
                if not replacement_found and consecutive_errors < MAX_CONSECUTIVE_ERRORS:
                    print(f"  ⚠️  No valid replacement found for {url}")
                elif consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
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
    if not os.path.exists(INPUT_CSV):
        print(f"❌ ERROR: Input CSV file '{INPUT_CSV}' not found.")
        return

    # Check if websites directory exists
    if not os.path.exists(INPUT_DIR):
        print(f"❌ ERROR: Input directory '{INPUT_DIR}' not found.")
        return

    # Create output directory if it doesn't exist
    if not os.path.exists(OUTPUT_DIR):
        print(f"📁 INFO: Output directory '{OUTPUT_DIR}' not found. Creating it.")
        os.makedirs(OUTPUT_DIR)

    # Read leads from CSV
    leads = []
    try:
        with open(INPUT_CSV, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                if 'Website' in row and 'Course' in row and row['Website'].strip():
                    leads.append({
                        'Website': row['Website'].strip(),
                        'Course': row['Course'].strip()
                    })
    except Exception as e:
        print(f"❌ ERROR: Could not read CSV file '{INPUT_CSV}'. Error: {e}")
        return

    if not leads:
        print(f"❌ No valid leads found in '{INPUT_CSV}'.")
        return

    # Count leads by type
    programming_leads = sum(1 for lead in leads if lead['Course'].lower() == 'programming')
    sales_leads = sum(1 for lead in leads if lead['Course'].lower() == 'sales')

    print(f"🚀 Starting Multithreaded Contact Info URL Extractor")
    print("=" * 60)
    print(f"📊 Total leads to process: {len(leads)}")
    print(f"💻 Programming course leads: {programming_leads}")
    print(f"💼 Sales course leads: {sales_leads}")
    print(f"🧵 Max concurrent workers: {MAX_WORKERS}")
    print(f"🛑 Max consecutive errors: {MAX_CONSECUTIVE_ERRORS}")
    print(f"📁 Input CSV: {INPUT_CSV}")
    print(f"📁 Websites directory: {INPUT_DIR}")
    print(f"📁 Output directory: {OUTPUT_DIR}")
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
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
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
    print(f"📁 Results saved in: {OUTPUT_DIR}/")
    
    if successful_processes > 0:
        avg_urls = total_urls_processed / successful_processes
        print(f"📈 Average URLs per Lead: {avg_urls:.1f}")
    
    print("=" * 60)

# --- Execution ---
if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        print("❌ ERROR: Please set your Gemini API key as an environment variable (GEMINI_API_KEY).")
        print("   You can set it with: $env:GEMINI_API_KEY='your_api_key_here'")
        print("   Or install the package with: pip install google-genai")
    elif not GENAI_AVAILABLE:
        print("⚠️  WARNING: google-genai package not available. Install with: pip install google-genai")
        print("   The script will run with deterministic fallback only.")
        process_leads()
    else:
        print("🚀 Starting with Gemini 2.5 Flash integration...")
        process_leads()