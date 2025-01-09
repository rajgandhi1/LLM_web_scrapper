import json
import pandas as pd
from typing import Dict, List, Tuple
import ast
from difflib import SequenceMatcher
import re

SYNONYM_MAP = {
    'ethanol': 'alcohol',
    'niacinamide (50,000 ppm)': 'niacinamide',
    # Add more synonyms as needed
}

def normalize_ingredient_name(ingredient: str) -> str:
    """
    Normalize individual ingredient names to handle special cases.
    """
    ingredient = ingredient.lower().strip()
    
    # Handle number formatting
    ingredient = re.sub(r'(\d+)\s*,\s*(\d+)', r'\1,\2', ingredient)
    ingredient = re.sub(r'(\d+)\s+(\d+)', r'\1,\2', ingredient)
    
    # Synonym mapping
    ingredient = SYNONYM_MAP.get(ingredient, ingredient)
    
    # Standardize water-related names
    if ingredient in ['water', 'aqua', 'water / aqua / eau', 'aqua (water)', 'water (aqua)']:
        return 'water'
    
    # Handle parenthetical clarifications
    ingredient = re.sub(r'\s*\([^)]*\)', '', ingredient)
    
    # Standardize spacing
    ingredient = re.sub(r'\s+', ' ', ingredient).strip()
    
    return ingredient

def normalize_ingredients(ingredients: str) -> List[str]:
    """
    Normalize ingredients list by removing variations in formatting
    and splitting into individual ingredients.
    """
    if not ingredients or ingredients == 'N/A':
        return []
    
    # Initial split on commas and various separators
    ingredients = ingredients.replace(' / ', ', ').replace(' /', ', ').replace('/ ', ', ')
    ingredients_list = [ing.strip() for ing in ingredients.split(',')]
    
    # Normalize each ingredient
    normalized_ingredients = []
    for ing in ingredients_list:
        if ing.strip():
            normalized = normalize_ingredient_name(ing)
            if normalized:  # Only add if normalization returned a valid result
                normalized_ingredients.append(normalized)
    
    # Remove duplicates while preserving order
    seen = set()
    normalized_ingredients = [
        ing for ing in normalized_ingredients 
        if not (ing in seen or seen.add(ing))
    ]
    
    return normalized_ingredients

def parse_ground_truth(ing_data: str) -> List[str]:
    """
    Parse the ground truth ingredient data from the CSV format.
    """
    try:
        # Convert string representation of dictionary to actual dictionary
        data = ast.literal_eval(ing_data)
        
        # Extract ingredient names from the nested structure
        if isinstance(data, dict) and 'ing_con_rank' in data:
            return [ing.lower() for ing in data['ing_con_rank'].keys()]
        return []
    except:
        return []

def is_partial_match(ingredient1: str, ingredient2: str, threshold: float = 0.8) -> bool:
    """
    Check if two ingredient names are a partial match based on a similarity threshold.
    """
    return SequenceMatcher(None, ingredient1, ingredient2).ratio() >= threshold

def calculate_similarity(list1: List[str], list2: List[str]) -> float:
    """
    Calculate similarity ratio between two ingredient lists with improved matching.
    """
    if not list1 or not list2:
        return 0.0
    
    # Normalize all ingredients in both lists
    list1 = [normalize_ingredient_name(ing) for ing in list1]
    list2 = [normalize_ingredient_name(ing) for ing in list2]
    
    # Match ingredients between lists
    matched = 0
    for ing1 in list1:
        for ing2 in list2:
            if is_partial_match(ing1, ing2) or ing1 == ing2:
                matched += 1
                break
    
    # Calculate similarity as the proportion of matched ingredients
    total_ingredients = max(len(list1), len(list2))
    return matched / total_ingredients if total_ingredients > 0 else 0.0

def read_csv_with_encoding(file_path: str) -> pd.DataFrame:
    """
    Try to read CSV file with different encodings.
    """
    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
    
    for encoding in encodings:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except Exception as e:
            print(f"Error reading file with {encoding} encoding: {str(e)}")
            continue
    
    raise ValueError("Could not read the CSV file with any of the attempted encodings")

def compare_ingredients(output_file: str, ground_truth_file: str, similarity_threshold: float = 0.9) -> Dict:
    """
    Compare ingredients between scraped data and ground truth data.
    """
    # Load the scraped data
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            scraped_data = json.load(f)
    except UnicodeDecodeError:
        with open(output_file, 'r', encoding='latin1') as f:
            scraped_data = json.load(f)
    
    # Load the ground truth data with proper encoding
    ground_truth_df = read_csv_with_encoding(ground_truth_file)
    
    # Rest of the function remains the same...
    results = {
        'total_products': len(scraped_data),
        'matched_products': 0,
        'partially_matched_products': 0,
        'mismatched_products': 0,
        'missing_ingredients': 0,
        'detailed_results': []
    }
    
    # Create a lookup dictionary for ground truth data
    ground_truth_dict = {}
    for _, row in ground_truth_df.iterrows():
        key = f"{row['Brand']}{row['Product Name']}".lower().replace(' ', '')
        ground_truth_dict[key] = parse_ground_truth(row['Ingredient name, concentration & rank'])
    
    # Compare each product
    for product in scraped_data:
        product_key = f"{product['Brand_Name']}{product['Product_Name']}".lower().replace(' ', '')
        
        scraped_ingredients = normalize_ingredients(product['Ingredients_List'])
        ground_truth_ingredients = ground_truth_dict.get(product_key, [])
        
        if not ground_truth_ingredients:
            results['missing_ingredients'] += 1
            continue
            
        similarity = calculate_similarity(scraped_ingredients, ground_truth_ingredients)
        
        result = {
            'product_name': f"{product['Brand_Name']} - {product['Product_Name']}",
            'similarity_score': similarity,
            'scraped_count': len(scraped_ingredients),
            'ground_truth_count': len(ground_truth_ingredients),
            'missing_from_scraped': [ing for ing in ground_truth_ingredients if ing not in scraped_ingredients],
            'extra_in_scraped': [ing for ing in scraped_ingredients if ing not in ground_truth_ingredients]
        }
        
        if similarity >= similarity_threshold:
            results['matched_products'] += 1
            result['match_status'] = 'MATCH'
        elif similarity >= 0.7:  # Partial match threshold
            results['partially_matched_products'] += 1
            result['match_status'] = 'PARTIAL'
        else:
            results['mismatched_products'] += 1
            result['match_status'] = 'MISMATCH'
            
        results['detailed_results'].append(result)
    
    # Calculate percentages
    total = results['total_products'] - results['missing_ingredients']
    results['match_percentage'] = (results['matched_products'] / total * 100) if total > 0 else 0
    results['partial_match_percentage'] = (results['partially_matched_products'] / total * 100) if total > 0 else 0
    results['mismatch_percentage'] = (results['mismatched_products'] / total * 100) if total > 0 else 0
    
    return results

def generate_report(results: Dict) -> str:
    """
    Generate a detailed report from the comparison results.
    """
    report = [
        "Ingredient Comparison Report",
        "=========================\n",
        f"Total Products Analyzed: {results['total_products']}",
        f"Products Missing from Ground Truth: {results['missing_ingredients']}\n",
        "Match Statistics:",
        f"- Full Matches: {results['matched_products']} ({results['match_percentage']:.1f}%)",
        f"- Partial Matches: {results['partially_matched_products']} ({results['partial_match_percentage']:.1f}%)",
        f"- Mismatches: {results['mismatched_products']} ({results['mismatch_percentage']:.1f}%)\n",
        "Detailed Results:",
        "----------------"
    ]
    
    # Sort detailed results by similarity score
    sorted_results = sorted(results['detailed_results'], 
                          key=lambda x: x['similarity_score'], 
                          reverse=True)
    
    for result in sorted_results:
        report.extend([
            f"\nProduct: {result['product_name']}",
            f"Match Status: {result['match_status']}",
            f"Similarity Score: {result['similarity_score']:.2f}",
            f"Ingredient Counts: Scraped={result['scraped_count']}, Ground Truth={result['ground_truth_count']}",
            "Missing Ingredients: " + (', '.join(result['missing_from_scraped']) if result['missing_from_scraped'] else 'None'),
            "Extra Ingredients: " + (', '.join(result['extra_in_scraped']) if result['extra_in_scraped'] else 'None'),
            ""
        ])
    
    return '\n'.join(report)

if __name__ == "__main__":
    # File paths
    output_file = r"C:\Users\Deva_pg\Downloads\honestly\crawled_products_ingredients_new_3.json"
    ground_truth_file = r"C:\Users\Deva_pg\Downloads\honestly\Ingredients_ground_truth.csv"
    report_file = r"C:\Users\Deva_pg\Downloads\honestly\Ingredients_comparision_report_3.txt"
    
    # Run comparison
    results = compare_ingredients(output_file, ground_truth_file)
    
    # Generate and save report
    report = generate_report(results)
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    # Save detailed results as JSON for further analysis
    with open('comparison_results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=4)
    
    print(f"Analysis complete. Results saved to {report_file} and comparison_results.json")