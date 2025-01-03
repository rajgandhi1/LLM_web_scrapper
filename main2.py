import json
import requests
from app.streamlit_web_scraper_chat import StreamlitWebScraperChat
from src.scrapers.playwright_scraper import ScraperConfig
from typing import List, Dict, Optional
import csv

# def query_model(prompt, model_name="llama3.1:8b"):
#     """
#     Query the Ollama server with a prompt and return the response.

#     Args:
#         prompt (str): The prompt to send to the model.
#         model_name (str): The name of the model to use.

#     Returns:
#         str: The model's response.
#     """
#     url = "http://127.0.0.1:11434/api/generate"
#     headers = {"Content-Type": "application/json"}
#     payload = {"prompt": prompt, "model": model_name}

#     try:
#         response = requests.post(url, headers=headers, json=payload, stream=True)
#         response.raise_for_status()

#         # Process streamed JSON objects
#         full_response = ""
#         for line in response.iter_lines():
#             if line:  # Skip empty lines
#                 try:
#                     json_data = json.loads(line)
#                     if "response" in json_data:
#                         full_response += json_data["response"]
#                 except json.JSONDecodeError as e:
#                     print(f"Error decoding JSON line: {e}")

#         return full_response

#     except requests.RequestException as e:
#         return f"Error querying the model: {e}"

def query_model(prompt, model_name="gpt-4o-mini"):
    """
    Query OpenAI's GPT-4 model with a prompt and return the response.
    """
    import openai
    import os

    # Get API key from environment variable
    openai.api_key = os.getenv('OPENAI_API_KEY')

    try:
        response = openai.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts and formats product information. Always respond with valid JSON containing the requested fields."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent output
            max_tokens=1000
        )
        
        if response and response.choices:
            return response.choices[0].message.content.strip()
        else:
            print("No response received from OpenAI")
            return "{}"  # Return empty JSON string instead of None

    except Exception as e:
        print(f"Error querying the model: {e}")
        return "{}"  # Return empty JSON string instead of None

def scrape_and_query(url, question):
    scraper_config = ScraperConfig(
        use_current_browser=False,
        headless=True,
        max_retries=3,
        delay_after_load=5,
        debug=True,
        wait_for='domcontentloaded'
    )

    web_scraper_chat = StreamlitWebScraperChat(model_name="gpt-4o-mini", scraper_config=scraper_config)
    
    print(f"Scraping URL: {url}")
    scraped_data = web_scraper_chat.process_message(url)

    if "Error" in scraped_data:
        return {"Error": scraped_data}

    print("Scraped data:", scraped_data[:200])  # Debug print

    combined_query = f"""
    From this product page content, extract ONLY the ingredients list:

    {scraped_data}

    Return ONLY the comma-separated list of ingredients, with no additional text or formatting.
    """
    ingredients_response = query_model(combined_query)
    print("Ingredients response:", ingredients_response[:200])  # Debug print

    if "Error" in ingredients_response:
        return {"Error": ingredients_response}

    return ingredients_response

def format_product_data(ingredients: str, product_info: Dict) -> Dict:
    # Clean up ingredients string
    cleaned_ingredients = ingredients.strip()
    
    # Handle JSON formatted response
    try:
        if cleaned_ingredients.startswith('```json'):
            # Remove JSON code block markers
            cleaned_ingredients = cleaned_ingredients.replace('```json', '').replace('```', '')
            # Parse JSON
            ingredients_json = json.loads(cleaned_ingredients)
            cleaned_ingredients = ingredients_json.get('ingredients', 'N/A')
    except:
        pass
    
    # Remove any "ingredients:" prefix and clean whitespace
    if "ingredients:" in cleaned_ingredients.lower():
        cleaned_ingredients = cleaned_ingredients.split("ingredients:", 1)[1]
    cleaned_ingredients = cleaned_ingredients.strip()

    return {
        "Product_Name": product_info.get('product_name', 'N/A'),
        "Brand_Name": product_info.get('brand_name', 'N/A'),
        "Variant_Name": product_info.get('variant_name', 'N/A'),
        "Ingredients_List": cleaned_ingredients if cleaned_ingredients else 'N/A'
    }

def construct_product_url(brand: str, product: str, variant: str = "") -> str:
    # Define URL patterns for specific brands
    brand_url_patterns = {
        "laneige": lambda product, variant: f"https://us.laneige.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://us.laneige.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "paula's choice": lambda product, variant: f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "farmacy": lambda product, variant: f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "byoma": lambda product, variant: f"https://byoma.com/product/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://byoma.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "minimalist": lambda product, variant: f"https://beminimalist.co/products/{product.lower().replace(' ', '-').replace('%', '')}" if not variant else f"https://beminimalist.co/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "i'm from": lambda product, variant: f"https://beautybarn.in/product/{product.lower().replace(' ', '-').replace('%', '')}",
        "haruharu wonder": lambda product, variant: f"https://www.haruharuindia.com/product/{product.lower().replace(' ', '-').replace('%', '')}",
        "numbuzin": lambda product, variant: f"https://numbuzinus.com/collections/all-products/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "skin 1004": lambda product, variant: f"https://skin1004.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "beauty of joseon": lambda product, variant: f"https://beautyofjoseon.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "cosrx": lambda product, variant: f"https://www.cosrx.com/products/{product.lower().replace(' ', '-')}.replace('%', '')",
        "isntree": lambda product, variant: f"https://beautybarn.in/product/isntree-{product.lower().replace(' ', '-').replace('%', '')}",
        "by wishtrend": lambda product, variant: f"https://bywishtrend.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "one thing": lambda product, variant: f"https://limese.com/products/one-thing-{product.lower().replace(' ', '-').replace('%', '')}",
        "innisfree": lambda product, variant: f"https://us.innisfree.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "the face shop": lambda product, variant: f"https://thefaceshop.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "tirtir": lambda product, variant: f"https://tirtir.us/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "simple": lambda product, variant: f"https://www.simpleskincare.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "foxtale": lambda product, variant: f"https://foxtale.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "first aid beauty": lambda product, variant: f"https://www.firstaidbeauty.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "fae beauty": lambda product, variant: f"https://www.faebeauty.in/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "d'you": lambda product, variant: f"https://www.dyou.co/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "inde wild": lambda product, variant: f"https://www.indewild.com/products/{product.lower().replace(' ', '-').replace('%', '')}",
        "klairs": lambda product, variant: f"https://www.klairscosmetics.com/product/{product.lower().replace(' ', '-').replace('%', '')}",
    }

    # Default URL format for brands not in the specific mapping
    default_url = lambda product, variant: f"https://{brand.lower().replace(' ', '')}.com/product/{product.lower().replace(' ', '-')}" if not variant else f"https://{brand.lower().replace(' ', '')}.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}/"

    # Use the brand-specific pattern or fallback to the default pattern
    url_generator = brand_url_patterns.get(brand.lower(), default_url)
    return url_generator(product, variant)

def read_product_csv(file_path: str) -> List[Dict]:
    products = []
    try:
        with open(file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                url = construct_product_url(
                    row['brand_name'],
                    row['product_name'],
                    row.get('variant_name', '')
                )
                products.append({**row, 'url': url})
        return products
    except Exception as e:
        raise Exception(f"Error reading CSV: {str(e)}")

if __name__ == "__main__":
    csv_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\Products_List2.csv"
    products = read_product_csv(csv_path)
    output_file_path = r"C:\\Users\\Deva_pg\\Downloads\\honestly\\crawled_products8.json"
    
    # Initialize the JSON file with an empty list
    with open(output_file_path, "w") as f:
        json.dump([], f)

    for product in products:
        raw_ingredients = scrape_and_query(product['url'], "")
        formatted_data = format_product_data(raw_ingredients, product)
        
        # Read existing data
        with open(output_file_path, "r") as f:
            existing_data = json.load(f)
        
        # Append new record
        existing_data.append(formatted_data)
        
        # Write updated data
        with open(output_file_path, "w") as f:
            json.dump(existing_data, f, indent=4)
            
        print(f"Processed and stored: {product['brand_name']} - {product['product_name']}")

