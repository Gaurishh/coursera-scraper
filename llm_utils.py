#!/usr/bin/env python3
"""
LLM utility module for the Coursera Scraper project.
This module provides enhanced Gemini API calls with task-specific parameters.
"""

import os
import time
from google import genai
from google.genai import types
from constants import GEMINI_API_KEY, LLM_GENERATION_CONFIGS, DEFAULT_MAX_RETRIES

def get_gemini_client():
    """Initialize and return a Gemini client."""
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        raise ValueError("GEMINI_API_KEY not configured. Please set your API key in environment variables.")
    
    return genai.Client(api_key=GEMINI_API_KEY)

def call_gemini_with_params(prompt, task_type, max_retries=DEFAULT_MAX_RETRIES):
    """
    Enhanced Gemini API call with task-specific parameters.
    
    Args:
        prompt (str): The prompt to send
        task_type (str): One of 'url_selection', 'classification', 'contact_extraction'
        max_retries (int): Maximum retry attempts
        
    Returns:
        tuple: (response_text, error_details)
    """
    if task_type not in LLM_GENERATION_CONFIGS:
        raise ValueError(f"Invalid task_type: {task_type}. Must be one of: {list(LLM_GENERATION_CONFIGS.keys())}")
    
    config = LLM_GENERATION_CONFIGS[task_type]
    
    for attempt in range(max_retries):
        try:
            client = get_gemini_client()
            
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=types.GenerateContentConfig(
                    temperature=config["temperature"],
                    topP=config["topP"],
                    topK=config["topK"]
                )
            )
            
            return response.text, None
            
        except Exception as e:
            error_details = {
                "error": str(e),
                "attempt": attempt + 1,
                "max_retries": max_retries,
                "task_type": task_type,
                "config": config
            }
            
            print(f"⚠️  Gemini API attempt {attempt + 1} failed: {e}")
            
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"   Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"   Max retries ({max_retries}) reached. Giving up.")
    
    return None, error_details

def parse_llm_response(response_text, expected_format="json"):
    """
    Parse LLM response with error handling.
    
    Args:
        response_text (str): Raw response from LLM
        expected_format (str): Expected format ("json", "text")
        
    Returns:
        tuple: (parsed_data, error_details)
    """
    if not response_text:
        return None, {"error": "Empty response from LLM"}
    
    if expected_format == "json":
        try:
            import json
            
            # Clean the response text first
            cleaned_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]  # Remove ```json
            elif cleaned_text.startswith('```'):
                cleaned_text = cleaned_text[3:]   # Remove ```
            
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]  # Remove trailing ```
            
            cleaned_text = cleaned_text.strip()
            
            # Try to find JSON in the cleaned response
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                json_str = cleaned_text[start_idx:end_idx]
                return json.loads(json_str), None
            else:
                return None, {"error": "No valid JSON found in response", "response": response_text[:200] + "..." if len(response_text) > 200 else response_text}
                
        except json.JSONDecodeError as e:
            return None, {"error": f"JSON parsing failed: {e}", "response": response_text[:200] + "..." if len(response_text) > 200 else response_text}
    
    return response_text, None
