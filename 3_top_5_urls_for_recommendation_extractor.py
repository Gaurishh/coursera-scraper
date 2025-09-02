import os
import json
import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# No additional imports needed - using requests for REST API

# --- Configuration ---
INPUT_DIR = "websites"
OUTPUT_DIR = "top_5_urls_for_recommendation"
API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE") # Recommended: Use environment variables
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro-preview-06-05:generateContent?key={API_KEY}"
MAX_WORKERS = 6  # Number of concurrent threads for processing
MAX_CONSECUTIVE_ERRORS = 5  # Stop trying after 5 consecutive URL validation failures

# --- LLM Master Prompt ---
# This detailed prompt guides the LLM to make a reliable and informed decision.
MASTER_PROMPT_TEMPLATE = """
Persona:
You are an expert data analyst specializing in website structure. Your task is to identify the most informative URLs from a given list that will help a sales team understand an institution's focus.

Primary Goal:
Select the most informative URLs from the list below that will help a sales team understand an institution's focus. Choose up to 5 URLs (or all available URLs if there are fewer than 5) that are most likely to contain information about the institution's core purpose, courses offered, industry partnerships, or team structure. This information will be used to recommend either a 'Programming' course or a 'Sales' course. Use your own expert judgment to determine the most relevant URLs from the list.

IMPORTANT: If any URLs contain "/about" or "/about-us" in their path, prioritize these URLs as they are most likely to contain information about the institution's core purpose and focus.

List of URLs to Analyze:
{url_list_json}

Required Output Format:
Your response MUST be a valid JSON object and nothing else. The JSON object should contain a single key, 'selected_urls', with a list of the most relevant URLs you have chosen (up to 5, or all available if fewer than 5).
Example: {{"selected_urls": ["url_1", "url_2", "url_3"]}}
"""

# --- Gemini 2.5 Pro API Function ---
def generate_content_with_gemini(prompt, max_retries=3):
    """
    Generate content using Gemini 2.5 Pro with retry logic via REST API.
    
    Args:
        prompt (str): The prompt to send to Gemini
        max_retries (int): Maximum number of retry attempts
        
    Returns:
        str: Generated content or None if failed
    """
    if API_KEY == "YOUR_API_KEY_HERE":
        return None
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, json=payload, timeout=60)
            response.raise_for_status()
            
            # Extract text from response
            response_text = response.json()['candidates'][0]['content']['parts'][0]['text']
            return response_text
            
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

# --- About URL Prioritization Function ---
def prioritize_about_urls(urls):
    """
    Prioritizes URLs containing exactly '/about' or '/about-us' to ensure they are always selected.
    
    Args:
        urls (list): List of URLs to prioritize
        
    Returns:
        tuple: (about_urls, non_about_urls)
    """
    about_urls = []
    non_about_urls = []
    
    for url in urls:
        url_lower = url.lower()
        # Check for exact matches: '/about' or '/about-us' (not just containing these strings)
        if url_lower.endswith('/about') or url_lower.endswith('/about-us') or '/about/' in url_lower or '/about-us/' in url_lower:
            about_urls.append(url)
        else:
            non_about_urls.append(url)
    
    return about_urls, non_about_urls

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

# --- Fallback Function (Guardrail) ---
# This runs if the LLM fails, ensuring the script never crashes.
def get_all_urls_deterministic(url_list):
    """
    Selects ALL URLs based on a deterministic keyword scoring system.
    Returns a list of URLs sorted by priority (highest score first).
    Used as a prioritized queue for fallback URL selection.
    """
    print("INFO: Creating prioritized URL queue based on keyword scoring.")
    
    # Keywords with assigned scores. Higher is better.
    keyword_scores = {
        # Tier 1: Core Offerings & High-Value Departments (Score 10)
        'courses': 10, 'curriculum': 10, 'academics': 10, 'syllabus': 10,
        'solutions': 10, 'services': 10, 'products': 10,
        'computer-science': 10, 'b-tech': 10, 'mca': 10, 
        'mba': 10, 'bba': 10, 'marketing': 10, 'sales': 10,

        # Tier 2: People, Outcomes & Identity (Score 8)
        'departments': 8, 'faculty': 8, 'training': 8, 
        'placements': 8, 'career-services': 8,
        'about': 7, 'who-we-are': 7,

        # Tier 3: Recent Activities & Broader Context (Score 6)
        'news': 6, 'events': 6, 'blog': 6,
        'team': 5, 'leadership': 5,
        
        # Tier 4: General/Administrative (Score 3)
        'admissions': 3, 'jobs': 3,
        
        # Tier 5: Noise (Score 1)
        'contact': 1, 'gallery': 1, 'alumni': 1
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
             score += 3

        scored_urls.append((url, score))
        
    # Sort URLs by score in descending order
    scored_urls.sort(key=lambda x: x[1], reverse=True)
    
    # Return ALL URLs sorted by priority (not just top 5)
    return [url for url, score in scored_urls]

# --- Processing Function ---
def process_single_website(filename):
    """
    Process a single website file.
    Uses about URL prioritization first, then LLM selection, with deterministic queue as backup.
    Validates each selected URL and replaces invalid ones from the queue.
    
    Args:
        filename (str): Name of the website file to process
        
    Returns:
        tuple: (success, filename, urls_processed, error_message)
    """
    input_filepath = os.path.join(INPUT_DIR, filename)
    output_filepath = os.path.join(OUTPUT_DIR, filename)
    
    try:
        # Read URLs from file and normalize them
        with open(input_filepath, 'r', encoding='utf-8') as f:
            raw_urls = [line.strip() for line in f if line.strip()]
        
        if not raw_urls:
            return (False, filename, 0, "No URLs found in file")
            
        # Normalize URLs for processing (add https://www. if not present)
        urls = [normalize_url_for_processing(url) for url in raw_urls]
        print(f"📝 Normalized {len(urls)} URLs for processing from {filename}")
        
        # Step 1: Prioritize about URLs first
        about_urls, non_about_urls = prioritize_about_urls(urls)
        if about_urls:
            print(f"🎯 Found {len(about_urls)} about URLs: {about_urls}")
        else:
            print(f"⚠️  No about URLs found in {len(urls)} total URLs")
        
        # Step 2: Create prioritized URL queue for non-about URLs
        top_urls = get_all_urls_deterministic(non_about_urls)
        print(f"📋 Created prioritized queue with {len(top_urls)} non-about URLs for {filename}")
        
        # Step 3: Build final URL selection starting with about URLs
        final_selected_urls = []
        about_urls_added = 0
        
        # First, add all about URLs (up to 5 total)
        for about_url in about_urls:
            if len(final_selected_urls) < 5:
                final_selected_urls.append(about_url)
                about_urls_added += 1
        
        # Step 4: Use LLM to select remaining URLs from non-about URLs
        remaining_slots = 5 - len(final_selected_urls)
        if remaining_slots > 0 and non_about_urls:
            prompt = MASTER_PROMPT_TEMPLATE.format(url_list_json=json.dumps(non_about_urls))
            llm_selected_urls = []
            llm_success = False
            
            # Try Gemini 2.5 Pro first
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
                        print(f"✅ SUCCESS: Gemini 2.5 Pro selected {len(llm_selected_urls)} non-about URLs for {filename}")
                    else:
                        raise ValueError("Gemini response did not contain a valid list of URLs.")

                except (json.JSONDecodeError, ValueError) as e:
                    print(f"⚠️  WARN: Gemini response parsing failed for {filename}. Error: {e}")
                    llm_success = False
            else:
                print(f"⚠️  WARN: No response from Gemini API for {filename}")
                llm_success = False
            
            # Fallback to deterministic selection if Gemini failed or not available
            if not llm_success:
                print(f"🔄 Using top {remaining_slots} from prioritized queue for {filename}")
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
        
        if about_urls_added > 0:
            print(f"🎯 PRIORITIZED: Added {about_urls_added} about URLs to final selection")
        
        # Step 5: Validate each URL and replace invalid ones with next from queue
        final_urls = []
        consecutive_errors = 0
        
        print(f"🔍 Validating and finalizing {len(final_selected_urls)} URLs for {filename}")
        
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
            print(f"💾 Saved {len(final_urls)} valid URLs to {filename}")
            print(f"📊 Summary for {filename}: {len(final_urls)} final URLs")
            return (True, filename, len(final_urls), None)
        else:
            error_msg = f"No valid URLs found for {filename}"
            print(f"❌ {error_msg}")
            return (False, filename, 0, error_msg)
            
    except Exception as e:
        error_msg = f"Error processing {filename}: {e}"
        print(f"❌ {error_msg}")
        return (False, filename, 0, error_msg)

# --- Main Logic ---
def process_websites():
    """
    Main function to process websites using multithreading.
    """
    if not os.path.exists(INPUT_DIR):
        print(f"❌ ERROR: Input directory '{INPUT_DIR}' not found.")
        return

    if not os.path.exists(OUTPUT_DIR):
        print(f"📁 INFO: Output directory '{OUTPUT_DIR}' not found. Creating it.")
        os.makedirs(OUTPUT_DIR)

    website_files = [f for f in os.listdir(INPUT_DIR) if f.endswith('.txt')]
    
    if not website_files:
        print(f"❌ No website files found in '{INPUT_DIR}' directory.")
        return

    print(f"🚀 Starting Multithreaded URL Recommendation Extractor")
    print("=" * 60)
    print(f"📊 Total websites to process: {len(website_files)}")
    print(f"🧵 Max concurrent workers: {MAX_WORKERS}")
    print(f"🛑 Max consecutive errors: {MAX_CONSECUTIVE_ERRORS}")
    print(f"📁 Input directory: {INPUT_DIR}")
    print(f"📁 Output directory: {OUTPUT_DIR}")
    print("=" * 60)

        # Process websites using multithreading
    start_time = time.time()
    successful_processes = 0
    total_urls_processed = 0
    
    # Thread-safe counters
    lock = threading.Lock()
    
    def update_counters(success, urls_count):
        nonlocal successful_processes, total_urls_processed
        with lock:
            if success:
                successful_processes += 1
                total_urls_processed += urls_count
    
    # Use ThreadPoolExecutor for concurrent processing
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Submit all tasks
        future_to_filename = {
            executor.submit(process_single_website, filename): filename 
            for filename in website_files
        }
        
        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_filename), 1):
            filename = future_to_filename[future]
            try:
                success, processed_filename, urls_count, error_msg = future.result()
                
                if success:
                    update_counters(True, urls_count)
                    print(f"✅ [{i}/{len(website_files)}] Success: {processed_filename} - {urls_count} URLs extracted")
                else:
                    print(f"❌ [{i}/{len(website_files)}] Failed: {processed_filename} - {error_msg}")
                    
            except Exception as e:
                print(f"❌ [{i}/{len(website_files)}] Exception for {filename}: {e}")
    
    # Calculate execution time
    end_time = time.time()
    execution_time = end_time - start_time
    
    # Display summary
    print("\n" + "=" * 60)
    print("🎉 MULTITHREADED PROCESSING COMPLETE!")
    print("=" * 60)
    print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")
    print(f"📊 Websites Processed: {len(website_files)}")
    print(f"✅ Successful Processes: {successful_processes}")
    print(f"❌ Failed Processes: {len(website_files) - successful_processes}")
    print(f"🔗 Total URLs Processed: {total_urls_processed}")
    print(f"📁 Results saved in: {OUTPUT_DIR}/")
    
    if successful_processes > 0:
        avg_urls = total_urls_processed / successful_processes
        print(f"📈 Average URLs per Website: {avg_urls:.1f}")
    
    print("=" * 60)

# --- Execution ---
if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY_HERE":
        print("ERROR: Please set your Gemini API key in the script or as an environment variable (GEMINI_API_KEY).")
    else:
        process_websites()
