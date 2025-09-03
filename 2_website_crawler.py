import os
import csv
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time
from collections import deque
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import constants
from constants import (
    WEBSITE_CRAWLER_INPUT_CSV, WEBSITE_CRAWLER_OUTPUT_DIR, WEBSITE_CRAWLER_MAX_WORKERS,
    MAX_WEBSITES_LIMIT, MAX_URLS_PER_WEBSITE, MAX_CONSECUTIVE_FAILURES,
    WEBSITE_CRAWLER_TIMEOUT, WEBSITE_CRAWLER_DELAY, MAX_BACKOFF_TIME,
    ALLOWED_WEB_EXTENSIONS, SKIP_URL_PATTERNS
)

# Global domain blacklist to prevent retrying problematic domains across threads
failed_domains = set()
domain_lock = threading.Lock()

def normalize_url_for_storage(url):
    """
    Normalize URL for storage by removing protocol and www prefix.
    This ensures that https://www.example.com/page, http://www.example.com/page, 
    and http://example.com/page are all treated as the same URL.
    
    Args:
        url (str): URL to normalize
        
    Returns:
        str: Normalized URL without protocol and www prefix
    """
    parsed = urlparse(url)
    
    # Remove www. prefix from domain
    domain = parsed.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Build normalized URL: domain + path + query (no scheme, no www)
    normalized = domain + parsed.path
    if parsed.query:
        normalized += '?' + parsed.query
    
    return normalized

def crawl_website_iterative(start_url):
    """
    Optimized iterative crawler with connection pooling and better performance.
    Includes domain failure tracking to stop crawling problematic websites.
    """
    base_netloc = urlparse(start_url).netloc
    
    # Normalize domain by removing 'www.' prefix for comparison
    def normalize_domain(domain):
        """Remove www. prefix for domain comparison"""
        if domain.startswith('www.'):
            return domain[4:]
        return domain
    
    base_domain_normalized = normalize_domain(base_netloc)
    
    # Check if this domain has already failed in other threads
    with domain_lock:
        if base_netloc in failed_domains:
            print(f"🚫 Skipping {base_netloc} - domain already marked as failed")
            return set()
    
    # Use session for connection pooling - major performance improvement
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    # A queue to hold all the URLs to be crawled
    urls_to_crawl = deque([start_url])
    # A set to keep track of all URLs found to prevent duplicates and re-crawling
    found_urls = {start_url}
    # A set to track normalized URLs to prevent protocol/www duplicates
    normalized_urls = {normalize_url_for_storage(start_url)}
    
    # Safety limit to prevent infinite loops
    max_urls = MAX_URLS_PER_WEBSITE
    
    # Track connection failures for this domain
    consecutive_failures = 0
    
    # Continue as long as there are URLs in the queue and we haven't hit the limit
    while urls_to_crawl and len(found_urls) < max_urls and consecutive_failures < MAX_CONSECUTIVE_FAILURES:
        # Get the next URL from the left of the queue
        current_url = urls_to_crawl.popleft()
        print(f"Crawling: {current_url} (Found: {len(found_urls)})")

        try:
            # Use session for connection reuse - much faster than individual requests
            response = session.get(current_url, timeout=WEBSITE_CRAWLER_TIMEOUT)
            response.raise_for_status()
            
            # Reset failure counter on successful request
            consecutive_failures = 0
            
        except (requests.exceptions.RequestException, requests.exceptions.HTTPError) as e:
            consecutive_failures += 1
            print(f"Could not retrieve or access {current_url}: {e}")
            
            # Check if we should stop crawling this domain
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"🛑 Stopping crawl for {base_netloc} due to {consecutive_failures} consecutive connection failures")
                # Add domain to global blacklist
                with domain_lock:
                    failed_domains.add(base_netloc)
                break
                
            # Add exponential backoff for temporary failures
            if consecutive_failures > 1:
                backoff_time = min(2 ** consecutive_failures, MAX_BACKOFF_TIME)
                print(f"⏳ Waiting {backoff_time} seconds before retrying...")
                time.sleep(backoff_time)
            
            continue # Skip to the next URL in the queue

        # Parse HTML more efficiently
        soup = BeautifulSoup(response.text, 'html.parser')  # Use text instead of content for better performance

        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Early filtering - skip problematic URLs before processing
            if any(skip in href.lower() for skip in SKIP_URL_PATTERNS):
                continue
                
            # Build URL more efficiently
            full_url = urljoin(current_url, href)
            parsed_url = urlparse(full_url)
            
            # Skip external URLs early - use normalized domain comparison
            link_domain_normalized = normalize_domain(parsed_url.netloc)
            if link_domain_normalized != base_domain_normalized:
                continue
                
            # Skip files with extensions (but allow common web page extensions)
            file_ext = os.path.splitext(parsed_url.path)[1].lower()
            if file_ext and file_ext not in ALLOWED_WEB_EXTENSIONS:
                continue
                
            # Remove fragment for comparison - more efficient than _replace()
            clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
            if parsed_url.query:
                clean_url += f"?{parsed_url.query}"

            # Normalize URL for duplicate checking
            normalized_url = normalize_url_for_storage(clean_url)
            
            # Check if the normalized URL has already been found (prevents protocol/www duplicates)
            if normalized_url not in normalized_urls:
                found_urls.add(clean_url)
                normalized_urls.add(normalized_url)
                urls_to_crawl.append(clean_url)
        
        # Small delay to be respectful to the server
        time.sleep(WEBSITE_CRAWLER_DELAY)
        
    # Warn if we hit the limit or stopped due to failures
    if len(found_urls) >= max_urls:
        print(f"⚠️  WARNING: Hit maximum URL limit ({max_urls}). There may be more routes on this website.")
    elif consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        print(f"⚠️  WARNING: Stopped crawling due to {consecutive_failures} consecutive connection failures.")
                
    return found_urls

def process_single_website(row, output_dir):
    """
    Process a single website - thread-safe function for multithreading.
    
    Args:
        row (dict): CSV row containing website information
        output_dir (str): Directory to save output files
        
    Returns:
        tuple: (success, company_name, routes_count, error_message)
    """
    url = row.get('Website')
    company_name = row.get('Institution Name', 'Unknown')
    
    if not url or url.strip() == '' or url.lower() == 'n/a':
        return (False, company_name, 0, "No valid website URL")
    
    # Ensure URL has protocol
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        print(f"🕷️  Starting crawl for {company_name}: {url}")
        
        # Crawl the website
        all_routes = crawl_website_iterative(url)
        
        # Generate filename
        base_netloc = urlparse(url).netloc
        filename = base_netloc.replace('www.', '') + '.txt'
        filepath = os.path.join(output_dir, filename)
        
        # Save results (thread-safe file writing) - store normalized URLs
        with open(filepath, 'w', encoding='utf-8') as f:
            # Convert to normalized URLs and sort them
            normalized_routes = [normalize_url_for_storage(route) for route in all_routes]
            for route in sorted(normalized_routes):
                f.write(f"{route}\n")
        
        print(f"✅ Completed {company_name}: {len(all_routes)} routes → {filepath}")
        return (True, company_name, len(all_routes), None)
        
    except Exception as e:
        error_msg = f"Error processing {company_name}: {e}"
        print(f"❌ {error_msg}")
        return (False, company_name, 0, error_msg)

def retry_single_route_websites(output_dir):
    """
    Find and retry websites that only have 1 route.
    
    Args:
        output_dir (str): Directory containing website files
        
    Returns:
        dict: Summary of retry results
    """
    print("🔍 Scanning for single route websites...")
    
    # Find all single route files
    single_route_files = []
    for filename in os.listdir(output_dir):
        if filename.endswith('.txt'):
            filepath = os.path.join(output_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    routes = [line.strip() for line in f.readlines() if line.strip()]
                
                if len(routes) == 1:
                    # Extract URL from the route
                    url = routes[0]
                    single_route_files.append((filename, url))
            except Exception as e:
                print(f"⚠️  Error reading {filename}: {e}")
    
    if not single_route_files:
        print("✅ No single route websites found - all good!")
        return {
            'retried': 0,
            'successful': 0,
            'failed': 0,
            'additional_routes': 0
        }
    
    print(f"🔄 Found {len(single_route_files)} single route websites to retry")
    
    # Retry each single route website
    retry_results = {
        'retried': len(single_route_files),
        'successful': 0,
        'failed': 0,
        'additional_routes': 0
    }
    
    for i, (filename, url) in enumerate(single_route_files, 1):
        print(f"\n[{i:2d}/{len(single_route_files)}] Retrying: {filename}")
        print(f"URL: {url}")
        print("-" * 50)
        
        try:
            # Get original route count
            original_routes = 1
            
            # Retry crawling
            new_routes = crawl_website_iterative(url)
            
            # Generate filename
            base_netloc = urlparse(url).netloc
            new_filename = base_netloc.replace('www.', '') + '.txt'
            filepath = os.path.join(output_dir, new_filename)
            
            # Save results - store normalized URLs
            with open(filepath, 'w', encoding='utf-8') as f:
                # Convert to normalized URLs and sort them
                normalized_routes = [normalize_url_for_storage(route) for route in new_routes]
                for route in sorted(normalized_routes):
                    f.write(f"{route}\n")
            
            new_route_count = len(new_routes)
            additional_routes = new_route_count - original_routes
            
            if new_route_count > 1:
                retry_results['successful'] += 1
                retry_results['additional_routes'] += additional_routes
                print(f"✅ SUCCESS: Found {new_route_count} routes (+{additional_routes})")
                print(f"   First 3 routes:")
                for j, route in enumerate(list(new_routes)[:3], 1):
                    print(f"     {j}. {route}")
            else:
                retry_results['failed'] += 1
                print(f"❌ STILL FAILED: Only {new_route_count} route found")
                
        except Exception as e:
            retry_results['failed'] += 1
            print(f"❌ ERROR: {e}")
    
    return retry_results

def main():
    """
    Main function with multithreaded website crawling.
    """
    csv_filename = WEBSITE_CRAWLER_INPUT_CSV
    output_dir = WEBSITE_CRAWLER_OUTPUT_DIR
    
    # Configuration
    max_workers = WEBSITE_CRAWLER_MAX_WORKERS
    max_websites = MAX_WEBSITES_LIMIT
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("🚀 Starting Multithreaded Website Crawler")
    print("=" * 60)
    print(f"📊 Max Workers: {max_workers}")
    print(f"📁 Output Directory: {output_dir}")
    print("=" * 60)

    try:
        # Read all websites from CSV
        websites_to_process = []
        with open(csv_filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                websites_to_process.append(row)
                if max_websites and len(websites_to_process) >= max_websites:
                    break
        
        print(f"📋 Found {len(websites_to_process)} websites to process")
        
        # Process websites with multithreading
        start_time = time.time()
        successful_crawls = 0
        total_routes = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_website = {
                executor.submit(process_single_website, row, output_dir): row 
                for row in websites_to_process
            }
            
            # Process completed tasks
            for future in as_completed(future_to_website):
                row = future_to_website[future]
                try:
                    success, company_name, routes_count, error_msg = future.result()
                    
                    if success:
                        successful_crawls += 1
                        total_routes += routes_count
                    else:
                        print(f"⚠️  Failed: {company_name} - {error_msg}")
                        
                except Exception as e:
                    company_name = row.get('Institution Name', 'Unknown')
                    print(f"❌ Exception for {company_name}: {e}")
        
        # Calculate execution time
        end_time = time.time()
        execution_time = end_time - start_time
        
        # Display summary
        print("\n" + "=" * 60)
        print("🎉 MULTITHREADED CRAWLING COMPLETE!")
        print("=" * 60)
        print(f"⏱️  Total Execution Time: {execution_time:.2f} seconds")
        print(f"📊 Websites Processed: {len(websites_to_process)}")
        print(f"✅ Successful Crawls: {successful_crawls}")
        print(f"❌ Failed Crawls: {len(websites_to_process) - successful_crawls}")
        print(f"🔗 Total Routes Discovered: {total_routes}")
        print(f"📁 Results saved in: {output_dir}/")
        
        if successful_crawls > 0:
            avg_routes = total_routes / successful_crawls
            print(f"📈 Average Routes per Website: {avg_routes:.1f}")
        
        # Display failed domains summary
        with domain_lock:
            if failed_domains:
                print(f"\n🚫 Domains with connection issues ({len(failed_domains)}):")
                for domain in sorted(failed_domains):
                    print(f"   • {domain}")
        
        # Retry single route websites
        print(f"\n🔄 RETRYING SINGLE ROUTE WEBSITES")
        print("=" * 60)
        retry_results = retry_single_route_websites(output_dir)
        
        if retry_results['retried'] > 0:
            print(f"\n📊 RETRY SUMMARY:")
            print(f"   🔄 Websites retried: {retry_results['retried']}")
            print(f"   ✅ Successful retries: {retry_results['successful']}")
            print(f"   ❌ Still failed: {retry_results['failed']}")
            print(f"   🔗 Additional routes found: {retry_results['additional_routes']}")
            
            # Update final totals
            total_routes += retry_results['additional_routes']
            successful_crawls += retry_results['successful']
            
            print(f"\n📈 FINAL TOTALS (including retries):")
            print(f"   ✅ Total Successful Crawls: {successful_crawls}")
            print(f"   🔗 Total Routes Discovered: {total_routes}")
            if successful_crawls > 0:
                avg_routes = total_routes / successful_crawls
                print(f"   📊 Average Routes per Website: {avg_routes:.1f}")
        
        print("=" * 60)

    except FileNotFoundError:
        print(f"❌ Error: The file '{csv_filename}' was not found.")
    except Exception as e:
        print(f"❌ A general error occurred: {e}")

if __name__ == '__main__':
    main()