import os
from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, continue without it
    pass

# --- Configuration ---
# Make sure to set your API key as an environment variable
# for example: export GOOGLE_API_KEY="YOUR_API_KEY"
# genai.configure() # Uncomment if running locally

# Initialize the Generative AI client
# In many environments like Google Colab, the client is automatically configured.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
client = genai.Client(api_key=GEMINI_API_KEY)

# Define the model to use
model_name = "gemini-2.5-flash"

# Define the prompt for the model
prompt = ["Explain the theory of relativity in three simple paragraphs."]

# Configure the generation parameters
generation_config = {
    # Controls the randomness of the output. Value is between 0.0 and 2.0.
    # Higher values (e.g., 1.0) make the output more random and creative.
    # Lower values (e.g., 0.2) make it more deterministic and focused.
    "temperature": 0.9,
    
    # The maximum cumulative probability of tokens to consider when sampling.
    # The model considers only the tokens whose cumulative probability is above this threshold.
    # A common value is 0.95.
    "topP": 0.95,
    
    # The maximum number of tokens to consider when sampling.
    # The model will only consider the top_k most probable tokens.
    # A common value is 40.
    "topK": 40,
}

# --- API Call ---
# Make the API call to generate content
print(f"Generating content with model: {model_name}...")
response = client.models.generate_content(
    model=model_name,
    contents=prompt,
    config=types.GenerateContentConfig(
        temperature=0.1,
        topP=0.95,
        topK=40
    )
)

# --- Print Response ---
# Print the generated text from the response
print("\n--- Model Response ---")
print(response.text)
print("--------------------")