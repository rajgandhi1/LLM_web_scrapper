import json
import requests
from app.streamlit_web_scraper_chat import StreamlitWebScraperChat
from src.scrapers.playwright_scraper import ScraperConfig
from typing import List, Dict, Optional
import csv

def query_model(prompt, model_name="llama3.1:8b"):
    """
    Query the Ollama server with a prompt and return the response.

    Args:
        prompt (str): The prompt to send to the model.
        model_name (str): The name of the model to use.

    Returns:
        str: The model's response.
    """
    url = "http://127.0.0.1:11434/api/generate"
    headers = {"Content-Type": "application/json"}
    payload = {"prompt": prompt, "model": model_name}

    try:
        response = requests.post(url, headers=headers, json=payload, stream=True)
        response.raise_for_status()

        # Process streamed JSON objects
        full_response = ""
        for line in response.iter_lines():
            if line:  # Skip empty lines
                try:
                    json_data = json.loads(line)
                    if "response" in json_data:
                        full_response += json_data["response"]
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON line: {e}")

        return full_response

    except requests.RequestException as e:
        return f"Error querying the model: {e}"

def scrape_and_query(url, question):
    """
    Scrape a website and query the extracted data.

    Args:
        url (str): The URL of the website to scrape.
        question (str): The question to ask about the scraped data.

    Returns:
        str: The response to the query.
    """
    # Scraper configuration
    scraper_config = ScraperConfig(
        use_current_browser=False,  # Adjust as needed
        headless=True,
        max_retries=3,
        delay_after_load=5,
        debug=True,
        wait_for='domcontentloaded'
    )

    # Initialize the web scraper
    web_scraper_chat = StreamlitWebScraperChat(model_name="llama3.1:8b", scraper_config=scraper_config)

    # Step 1: Scrape the website
    print(f"Scraping URL: {url}")
    scraped_data = web_scraper_chat.process_message(url)

    if "Error" in scraped_data:
        print(f"Error during scraping: {scraped_data}")
        return scraped_data

    print("Scraping completed.")

    # Step 2: Combine scraped data with the query
    combined_query = f"The following data was extracted from the website:\n\n{scraped_data}\n\n{question}"
    print(f"Querying data: {combined_query}")
    
    query_response = query_model(combined_query)

    if "Error" in query_response:
        print(f"Error during query: {query_response}")
        return query_response

    print("Query completed.")

    return query_response

def construct_product_url(brand: str, product: str, variant: str = "") -> str:
    # Define URL patterns for specific brands
    brand_url_patterns = {
        "laneige": lambda product, variant: f"https://us.laneige.com/products/{product.lower().replace(' ', '-')}" if not variant else f"https://us.laneige.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "paula's choice": lambda product, variant: f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-')}" if not variant else f"https://www.paulaschoice.in/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "farmacy": lambda product, variant: f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-')}" if not variant else f"https://www.farmacybeauty.com/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "byoma": lambda product, variant: f"https://byoma.com/product/{product.lower().replace(' ', '-')}" if not variant else f"https://byoma.com/product/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "minimalist": lambda product, variant: f"https://beminimalist.co/products/{product.lower().replace(' ', '-')}" if not variant else f"https://beminimalist.co/products/{product.lower().replace(' ', '-')}/{variant.lower().replace(' ', '-')}",
        "i'm from": lambda product, variant: f"https://beautybarn.in/product/{product.lower().replace(' ', '-')}",
        "haruharu wonder": lambda product, variant: f"https://www.haruharuindia.com/product/{product.lower().replace(' ', '-')}",
        "numbuzin": lambda product, variant: f"https://numbuzinus.com/collections/all-products/products/{product.lower().replace(' ', '-')}",
        "skin 1004": lambda product, variant: f"https://skin1004.com/products/{product.lower().replace(' ', '-')}",
        "beauty of joseon": lambda product, variant: f"https://beautyofjoseon.com/products/{product.lower().replace(' ', '-')}",
        "cosrx": lambda product, variant: f"https://www.cosrx.com/products/{product.lower().replace(' ', '-')}",
        "isntree": lambda product, variant: f"https://beautybarn.in/product/{product.lower().replace(' ', '-')}",
        "by wishtrend": lambda product, variant: f"https://bywishtrend.com/products/{product.lower().replace(' ', '-')}",
        "one thing": lambda product, variant: f"https://limese.com/products/{product.lower().replace(' ', '-')}",
        "innisfree": lambda product, variant: f"https://us.innisfree.com/products/{product.lower().replace(' ', '-')}",
        "the face shop": lambda product, variant: f"https://thefaceshop.in/products/{product.lower().replace(' ', '-')}",
        "tirtir": lambda product, variant: f"https://tirtir.us/products/{product.lower().replace(' ', '-')}",
        "simple": lambda product, variant: f"https://www.simpleskincare.in/products/{product.lower().replace(' ', '-')}",
        "foxtale": lambda product, variant: f"https://foxtale.in/products/{product.lower().replace(' ', '-')}",
        "first aid beauty": lambda product, variant: f"https://www.firstaidbeauty.com/products/{product.lower().replace(' ', '-')}",
        "fae beauty": lambda product, variant: f"https://www.faebeauty.in/products/{product.lower().replace(' ', '-')}",
        "d'you": lambda product, variant: f"https://www.dyou.co/products/{product.lower().replace(' ', '-')}",
        "inde wild": lambda product, variant: f"https://www.indewild.com/products/{product.lower().replace(' ', '-')}",
        "klairs": lambda product, variant: f"https://www.klairscosmetics.com/product/{product.lower().replace(' ', '-')}",
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

    query_question = (
        "Extract the following product details in the specified format: "
        "brand_name, product_name, variant_name, ingredients, images, "
        "marketing_claims, has_complete_ingredients, source_url. "
        "If any detail is not available, mark it as 'N/A'. "
        "Provide the output in exactly this format with no additional information."
    )

    results = []
    for product in products:
        result = scrape_and_query(product['url'], query_question)
        results.append(result)
        print(f"Processed: {product['brand_name']} - {product['product_name']}")

    print("\nResult:")
    print(results)

    with open(r"C:\\Users\\Deva_pg\\Downloads\\honestly\\crawled_products2.json", "w") as output_file:
        json.dump(results, output_file, indent=4)
    print("Result saved to output.json.")

