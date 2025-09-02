#!/usr/bin/env python3
"""
Test script to demonstrate multithreading performance
"""

import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

def test_single_request(url):
    """Test a single HTTP request"""
    try:
        start_time = time.time()
        response = requests.get(url, timeout=5)
        end_time = time.time()
        return {
            'url': url,
            'status': response.status_code,
            'time': end_time - start_time,
            'success': True
        }
    except Exception as e:
        return {
            'url': url,
            'status': 'Error',
            'time': 0,
            'success': False,
            'error': str(e)
        }

def test_multithreading_performance():
    """Compare sequential vs multithreaded performance"""
    
    # Test URLs (using some from your CSV)
    test_urls = [
        "https://www.techasoft.com",
        "https://www.igeekstechnologies.com",
        "https://www.nitdelhi.ac.in",
        "https://www.google.com",
        "https://www.github.com"
    ]
    
    print("🧪 Testing Multithreading Performance")
    print("=" * 50)
    
    # Sequential test
    print("\n📊 Sequential Processing:")
    start_time = time.time()
    sequential_results = []
    for url in test_urls:
        result = test_single_request(url)
        sequential_results.append(result)
        print(f"  {result['url']}: {result['status']} ({result['time']:.2f}s)")
    
    sequential_time = time.time() - start_time
    print(f"⏱️  Sequential Total Time: {sequential_time:.2f} seconds")
    
    # Multithreaded test
    print("\n🚀 Multithreaded Processing:")
    start_time = time.time()
    multithreaded_results = []
    
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_url = {executor.submit(test_single_request, url): url for url in test_urls}
        
        for future in as_completed(future_to_url):
            result = future.result()
            multithreaded_results.append(result)
            print(f"  {result['url']}: {result['status']} ({result['time']:.2f}s)")
    
    multithreaded_time = time.time() - start_time
    print(f"⏱️  Multithreaded Total Time: {multithreaded_time:.2f} seconds")
    
    # Performance comparison
    print("\n📈 Performance Comparison:")
    print(f"  Sequential: {sequential_time:.2f}s")
    print(f"  Multithreaded: {multithreaded_time:.2f}s")
    
    if sequential_time > 0:
        speedup = sequential_time / multithreaded_time
        print(f"  🚀 Speedup: {speedup:.2f}x faster")
    
    print("=" * 50)

if __name__ == "__main__":
    test_multithreading_performance()
